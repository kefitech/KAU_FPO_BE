"""
Expert Booking API - P2-08
FPO-side:
  GET  /api/experts/{id}/availability/    - browse open slots for an expert
  POST /api/experts/{id}/book/            - submit a booking request
  POST /api/experts/bookings/{id}/cancel/ - FPO cancels a booking

Expert-side:
  POST /api/experts/me/availability/            - publish availability slots
  GET  /api/experts/me/bookings/                - list bookings for the expert
  POST /api/experts/me/bookings/{id}/confirm/   - confirm a pending request
  POST /api/experts/me/bookings/{id}/reject/    - reject with a reason
  POST /api/experts/me/bookings/{id}/reschedule/ - propose a new date/time
"""
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.core.utils.constants import UserRole, FPOStatus
from apps.core.utils.responses import StandardResponse
from apps.database.models.schemes import Expert
from apps.database.models.expert_booking import ExpertAvailability, ExpertTimeSlot, ExpertBooking, ExpertWeeklyDefault
from apps.database.models.fpo import FPO, FPOUserMembership
from apps.notifications.services import send_notification


class ExpertTimeSlotSerializer(serializers.ModelSerializer):
    start = serializers.TimeField(source='start_time', format='%H:%M')
    end = serializers.TimeField(source='end_time', format='%H:%M')
    confirmed_count = serializers.ReadOnlyField()
    is_booked = serializers.BooleanField(source='is_full', read_only=True)

    class Meta:
        model = ExpertTimeSlot
        fields = ['id', 'start', 'end', 'max_bookings', 'confirmed_count', 'is_booked']


class ExpertAvailabilitySerializer(serializers.ModelSerializer):
    time_slots = serializers.SerializerMethodField()

    class Meta:
        model = ExpertAvailability
        fields = ['id', 'date', 'time_slots']

    def get_time_slots(self, obj):
        qs = obj.time_slots.filter(is_deleted=False).order_by('start_time')
        return ExpertTimeSlotSerializer(qs, many=True).data


class TimeSlotInputSerializer(serializers.Serializer):
    start = serializers.CharField(max_length=10)
    end = serializers.CharField(max_length=10)
    max_bookings = serializers.IntegerField(min_value=1, default=1)


class SetAvailabilitySerializer(serializers.Serializer):
    date = serializers.DateField()
    time_slots = TimeSlotInputSerializer(many=True)


class BulkAvailabilitySerializer(serializers.Serializer):
    slots = SetAvailabilitySerializer(many=True)


class ExpertBookingSerializer(serializers.ModelSerializer):
    expert_name = serializers.SerializerMethodField()
    fpo_name = serializers.SerializerMethodField()
    fpo_email = serializers.SerializerMethodField()
    fpo_phone = serializers.SerializerMethodField()
    fpo_contact_name = serializers.SerializerMethodField()
    fpo_application_id = serializers.SerializerMethodField()
    fpo_location = serializers.SerializerMethodField()
    fpo_district = serializers.SerializerMethodField()
    fpo_registration_number = serializers.SerializerMethodField()
    fpo_total_members = serializers.SerializerMethodField()
    status_display = serializers.SerializerMethodField()

    class Meta:
        model = ExpertBooking
        fields = [
            'id', 'expert', 'expert_name', 'fpo', 'fpo_name', 'fpo_email', 'fpo_phone',
            'fpo_contact_name', 'fpo_application_id', 'fpo_location',
            'fpo_district', 'fpo_registration_number', 'fpo_total_members',
            'requested_date', 'requested_time',
            'topic', 'notes', 'status', 'status_display', 'cancellation_reason',
            'created_at', 'updated_at',
        ]

    def get_expert_name(self, obj):
        return obj.expert.name_en

    def get_fpo_name(self, obj):
        return obj.fpo.name

    def get_fpo_email(self, obj):
        return obj.fpo.primary_user.email if obj.fpo.primary_user else None

    def get_fpo_phone(self, obj):
        if obj.fpo.primary_user and hasattr(obj.fpo.primary_user, 'profile'):
            return obj.fpo.primary_user.profile.phone
        return None

    def get_fpo_contact_name(self, obj):
        if obj.fpo.primary_user:
            full_name = obj.fpo.primary_user.get_full_name()
            return full_name or obj.fpo.primary_user.username
        return None

    def get_fpo_application_id(self, obj):
        return obj.fpo.application_id

    def get_fpo_location(self, obj):
        parts = [p for p in [obj.fpo.block_taluk, obj.fpo.get_district_display() if obj.fpo.district else None] if p]
        return ', '.join(parts) if parts else None

    def get_fpo_district(self, obj):
        return obj.fpo.get_district_display() if obj.fpo.district else None

    def get_fpo_registration_number(self, obj):
        return obj.fpo.registration_number or None

    def get_fpo_total_members(self, obj):
        return obj.fpo.total_members

    def get_status_display(self, obj):
        return obj.get_status_display()


class CreateBookingSerializer(serializers.Serializer):
    requested_date = serializers.DateField()
    requested_time = serializers.TimeField()
    time_slot_id = serializers.IntegerField(required=False)
    topic = serializers.CharField(
        required=True,
        allow_blank=False,
        max_length=255,
        error_messages={
            'blank': 'Please enter a topic for this appointment.',
            'required': 'Please enter a topic for this appointment.',
        },
    )
    notes = serializers.CharField(required=False, allow_blank=True)
def _get_fpo(user):
    membership = FPOUserMembership.objects.filter(user=user, is_active=True).first()
    if membership:
        return membership.fpo
    return FPO.objects.filter(primary_user=user, is_deleted=False).first()





def _is_admin(user):
    return user.groups.filter(name__in=[UserRole.SUPER_ADMIN, UserRole.SUB_ADMIN]).exists()


def _can_manage_expert(user, expert):
    return _is_admin(user) or (expert.is_active and expert.user_id and expert.user_id == user.id)



class ExpertAvailabilityView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=['Expert Booking'], summary="Browse an expert's open slots")
    def get(self, request, pk):
        try:
            expert = Expert.objects.get(pk=pk, is_deleted=False, is_active=True)
        except Expert.DoesNotExist:
            return StandardResponse.error('Expert not found.', status_code=status.HTTP_404_NOT_FOUND)

        from datetime import date as date_cls
        from django.db.models import Count, Prefetch

        # 1 query for the dates + 1 query for all their slots (instead of 1 per date).
        avails = list(
            ExpertAvailability.objects.filter(
                expert=expert, is_deleted=False, date__gte=date_cls.today()
            )
            .order_by('date')
            .prefetch_related(
                Prefetch(
                    'time_slots',
                    queryset=ExpertTimeSlot.objects.filter(is_deleted=False).order_by('start_time'),
                    to_attr='active_slots',
                )
            )
        )

        # 1 query for confirmed-booking counts of every slot (instead of 1-2 per slot).
        slot_ids = [s.id for a in avails for s in a.active_slots]
        confirmed_counts = dict(
            ExpertBooking.objects.filter(
                time_slot_id__in=slot_ids,
                status=ExpertBooking.Status.CONFIRMED,
                is_deleted=False,
            )
            .values('time_slot_id')
            .annotate(n=Count('id'))
            .values_list('time_slot_id', 'n')
        )

        data = []
        for a in avails:
            slots = []
            for s in a.active_slots:
                count = confirmed_counts.get(s.id, 0)
                slots.append({
                    'id': s.id,
                    'start': s.start_time.strftime('%H:%M'),
                    'end': s.end_time.strftime('%H:%M'),
                    'max_bookings': s.max_bookings,
                    'confirmed_count': count,
                    'is_booked': count >= s.max_bookings,
                })
            data.append({'id': a.id, 'date': str(a.date), 'time_slots': slots})

        return StandardResponse.success(data=data)

class CreateBookingView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=['Expert Booking'], summary='Request a booking', request=CreateBookingSerializer)
    def post(self, request, pk):
        if not request.user.groups.filter(name=UserRole.FPO_MANAGER).exists():
            return StandardResponse.error('Only FPO members can book experts.', status_code=status.HTTP_403_FORBIDDEN)

        fpo = _get_fpo(request.user)
        if not fpo or fpo.status != FPOStatus.APPROVED:
            return StandardResponse.error('Your FPO must be approved to book experts.', status_code=status.HTTP_403_FORBIDDEN)

        if ExpertBooking.objects.filter(fpo=fpo, status=ExpertBooking.Status.PENDING, is_deleted=False).exists():
            return StandardResponse.error(
                'You already have a pending booking request. Please wait for it to be confirmed or rejected before requesting another.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        try:
            expert = Expert.objects.get(pk=pk, is_deleted=False, is_active=True)
        except Expert.DoesNotExist:
            return StandardResponse.error('Expert not found.', status_code=status.HTTP_404_NOT_FOUND)

        serializer = CreateBookingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        avail = ExpertAvailability.objects.filter(
            expert=expert, date=data['requested_date'], is_deleted=False
        ).first()
        if not avail:
            return StandardResponse.error('No availability found for that date.', status_code=status.HTTP_400_BAD_REQUEST)

        if data.get('time_slot_id'):
            slot = ExpertTimeSlot.objects.filter(
                id=data['time_slot_id'], availability=avail, is_deleted=False
            ).first()
        else:
            slot = ExpertTimeSlot.objects.filter(
                availability=avail, start_time=data['requested_time'], is_deleted=False
            ).first()
        if not slot:
            return StandardResponse.error('That time slot does not exist.', status_code=status.HTTP_400_BAD_REQUEST)
        if slot.is_full:
            return StandardResponse.error('That slot is already fully booked.', status_code=status.HTTP_400_BAD_REQUEST)

        booking = ExpertBooking.objects.create(
            expert=expert, fpo=fpo, time_slot=slot,
            requested_date=data['requested_date'], requested_time=data['requested_time'],
            topic=data['topic'], notes=data.get('notes', ''),
        )

        try:
            send_notification(
                user=request.user, code='expert_booking_requested', channel='email',
                context={'expert_name': expert.name_en, 'fpo_name': fpo.name, 'date': str(data['requested_date']), 'time': data['requested_time']},
                override_recipient=expert.email,
            )
        except Exception:
            pass

        return StandardResponse.success(
            data=ExpertBookingSerializer(booking).data,
            message='Booking request submitted. The expert will confirm shortly.',
            status_code=status.HTTP_201_CREATED,
        )


class CancelBookingView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=['Expert Booking'], summary='FPO cancels a booking')
    def post(self, request, pk):
        fpo = _get_fpo(request.user)
        booking = ExpertBooking.objects.filter(pk=pk, fpo=fpo, is_deleted=False).first()
        if not booking:
            return StandardResponse.error('Booking not found.', status_code=status.HTTP_404_NOT_FOUND)

        if booking.status not in (ExpertBooking.Status.PENDING, ExpertBooking.Status.CONFIRMED):
            return StandardResponse.error('This booking cannot be cancelled.', status_code=status.HTTP_400_BAD_REQUEST)

        reason = request.data.get('reason', '')
        booking.status = ExpertBooking.Status.CANCELLED
        booking.cancellation_reason = reason
        booking.save(update_fields=['status', 'cancellation_reason'])

        try:
            send_notification(
                user=request.user, code='expert_booking_cancelled', channel='email',
                context={'fpo_name': fpo.name, 'date': str(booking.requested_date), 'time': booking.requested_time, 'reason': reason},
                override_recipient=booking.expert.email,
            )
        except Exception:
            pass

        return StandardResponse.success(data=ExpertBookingSerializer(booking).data, message='Booking cancelled.')

class AdminSetAvailabilityView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=['Expert Booking - Admin'], summary="Set an expert's availability (bulk)", request=BulkAvailabilitySerializer)
    def post(self, request, pk):
        try:
            expert = Expert.objects.get(pk=pk, is_deleted=False)
        except Expert.DoesNotExist:
            return StandardResponse.error('Expert not found.', status_code=status.HTTP_404_NOT_FOUND)

        if not _can_manage_expert(request.user, expert):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)

        serializer = BulkAvailabilitySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        results = []
        cancelled_dates = []
        affected_bookings = []
        for slot_group in serializer.validated_data['slots']:
            avail, _ = ExpertAvailability.objects.get_or_create(
                expert=expert, date=slot_group['date'],
            )
            if not avail.is_custom:
                avail.is_custom = True
                avail.save(update_fields=['is_custom'])
            submitted = {(s['start'], s['end']) for s in slot_group['time_slots']}

            # Slots the expert has un-chosen are removed. If a slot still has a
            # confirmed booking on it, the booking is auto-cancelled first (so the
            # FPO isn't left holding a "confirmed" appointment the expert has
            # already blocked off), then the slot is removed as normal.
            candidates = avail.time_slots.filter(is_deleted=False)
            date_has_cancelled_booking = False
            for old_slot in candidates:
                key = (old_slot.start_time.strftime('%H:%M'), old_slot.end_time.strftime('%H:%M'))
                if key not in submitted:
                    if old_slot.confirmed_count > 0:
                        confirmed_bookings = ExpertBooking.objects.filter(
                            time_slot=old_slot,
                            status=ExpertBooking.Status.CONFIRMED,
                            is_deleted=False,
                        )
                        for booking in confirmed_bookings:
                            booking.status = ExpertBooking.Status.CANCELLED
                            booking.cancellation_reason = 'Expert marked this date as unavailable.'
                            booking.save(update_fields=['status', 'cancellation_reason'])
                            affected_bookings.append(booking)
                        date_has_cancelled_booking = True
                    old_slot.soft_delete(user=request.user)
            if date_has_cancelled_booking:
                cancelled_dates.append(str(slot_group['date']))

            for s in slot_group['time_slots']:
                ExpertTimeSlot.objects.update_or_create(
                    availability=avail, start_time=s['start'], end_time=s['end'],
                    defaults={
                        'max_bookings': s.get('max_bookings', 1),
                        'is_deleted': False,
                        'deleted_at': None,
                    },
                )
            results.append(avail)
        # Notify FPOs exactly once per call, after all slot_groups are processed.
        for booking in affected_bookings:
            if booking.fpo.primary_user:
                notify_context = {
                    'expert_name': expert.name_en,
                    'fpo_name': booking.fpo.name,
                    'date': str(booking.requested_date),
                    'time': booking.requested_time,
                    'reason': booking.cancellation_reason,
                }
                try:
                    send_notification(
                        user=booking.fpo.primary_user,
                        code='expert_cancelled_confirmed_booking',
                        channel='email',
                        context=notify_context,
                    )
                except Exception:
                    pass
                try:
                    send_notification(
                        user=booking.fpo.primary_user,
                        code='expert_cancelled_confirmed_booking',
                        channel='in_app',
                        context=notify_context,
                    )
                except Exception:
                    pass

        message = 'Availability updated.'
        if cancelled_dates:
            message = (
                'Availability updated. Confirmed bookings on '
                f"{', '.join(cancelled_dates)} were automatically cancelled because the "
                'expert marked those dates unavailable. Affected FPOs have been notified.'
            )

        return StandardResponse.success(
            data=ExpertAvailabilitySerializer(results, many=True).data,
            message=message,
        )

class ResetAvailabilityToDefaultView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=['Expert Booking - Admin'], summary='Reset a date back to the weekly default template')
    def post(self, request, pk, date):
        try:
            expert = Expert.objects.get(pk=pk, is_deleted=False)
        except Expert.DoesNotExist:
            return StandardResponse.error('Expert not found.', status_code=status.HTTP_404_NOT_FOUND)

        if not _can_manage_expert(request.user, expert):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)

        avail = ExpertAvailability.objects.filter(expert=expert, date=date, is_deleted=False).first()
        if not avail:
            return StandardResponse.error('No availability found for that date.', status_code=status.HTTP_404_NOT_FOUND)

        avail.is_custom = False
        avail.save(update_fields=['is_custom'])
        return StandardResponse.success(message='This date will now follow the weekly default schedule again.')
class WeeklyDefaultSlotSerializer(serializers.Serializer):
    weekday = serializers.IntegerField(min_value=0, max_value=6)
    start = serializers.CharField(max_length=10)
    end = serializers.CharField(max_length=10)
    max_bookings = serializers.IntegerField(min_value=1, default=1)


class BulkWeeklyDefaultsSerializer(serializers.Serializer):
    slots = WeeklyDefaultSlotSerializer(many=True)


class ExpertWeeklyDefaultsView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=['Expert Booking - Admin'], summary="Get an expert's weekly default schedule")
    def get(self, request, pk):
        try:
            expert = Expert.objects.get(pk=pk, is_deleted=False)
        except Expert.DoesNotExist:
            return StandardResponse.error('Expert not found.', status_code=status.HTTP_404_NOT_FOUND)

        if not _can_manage_expert(request.user, expert):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)

        defaults = ExpertWeeklyDefault.objects.filter(expert=expert, is_deleted=False)
        data = [
            {
                'weekday': d.weekday,
                'start': d.start_time.strftime('%H:%M'),
                'end': d.end_time.strftime('%H:%M'),
                'max_bookings': d.max_bookings,
            }
            for d in defaults
        ]
        return StandardResponse.success(data=data)

    @extend_schema(tags=['Expert Booking - Admin'], summary="Set an expert's weekly default schedule (bulk)", request=BulkWeeklyDefaultsSerializer)
    def post(self, request, pk):
        try:
            expert = Expert.objects.get(pk=pk, is_deleted=False)
        except Expert.DoesNotExist:
            return StandardResponse.error('Expert not found.', status_code=status.HTTP_404_NOT_FOUND)

        if not _can_manage_expert(request.user, expert):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)

        serializer = BulkWeeklyDefaultsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        submitted = serializer.validated_data['slots']
        submitted_keys = {
            (s['weekday'], s['start'].strftime('%H:%M') if hasattr(s['start'], 'strftime') else s['start'], s['end'].strftime('%H:%M') if hasattr(s['end'], 'strftime') else s['end'])
            for s in submitted
        }

        existing = ExpertWeeklyDefault.objects.filter(expert=expert, is_deleted=False)
        for d in existing:
            key = (d.weekday, d.start_time.strftime('%H:%M'), d.end_time.strftime('%H:%M'))
            if key not in submitted_keys:
                d.soft_delete(user=request.user)

        for s in submitted:
            ExpertWeeklyDefault.objects.update_or_create(
                expert=expert, weekday=s['weekday'], start_time=s['start'], end_time=s['end'],
                defaults={'max_bookings': s.get('max_bookings', 1)},
            )

        # Cascade the updated weekly template onto every already-saved (today or
        # future) date that falls on one of the edited weekdays, so existing
        # calendar entries actually reflect the new schedule instead of only
        # affecting brand-new dates picked after this save.
        from datetime import date as date_cls
        affected_weekdays = {s['weekday'] for s in submitted}
        blocked_dates = []
        for weekday in affected_weekdays:
            weekday_slot_specs = [s for s in submitted if s['weekday'] == weekday]
            weekday_submitted_keys = {
                (
                    s['start'].strftime('%H:%M') if hasattr(s['start'], 'strftime') else s['start'],
                    s['end'].strftime('%H:%M') if hasattr(s['end'], 'strftime') else s['end'],
                )
                for s in weekday_slot_specs
            }
            future_avails = ExpertAvailability.objects.filter(
                expert=expert, is_deleted=False, date__gte=date_cls.today()
            )
            for avail in future_avails:
                # Python's date.weekday() is Monday=0..Sunday=6; convert to this
                # project's 0=Sunday..6=Saturday convention.
                if (avail.date.weekday() + 1) % 7 != weekday:
                    continue
                if avail.is_custom:
                    # Expert manually edited this specific date — leave it alone
                    # until they explicitly reset it back to the weekly default.
                    continue
                date_has_blocked_slot = False
                for old_slot in avail.time_slots.filter(is_deleted=False):
                    key = (old_slot.start_time.strftime('%H:%M'), old_slot.end_time.strftime('%H:%M'))
                    if key not in weekday_submitted_keys:
                        if old_slot.confirmed_count == 0:
                            old_slot.soft_delete(user=request.user)
                        else:
                            date_has_blocked_slot = True
                for s in weekday_slot_specs:
                    ExpertTimeSlot.objects.update_or_create(
                        availability=avail,
                        start_time=s['start'], end_time=s['end'],
                        defaults={
                            'max_bookings': s.get('max_bookings', 1),
                            'is_deleted': False,
                            'deleted_at': None,
                        },
                    )
                if date_has_blocked_slot:
                    blocked_dates.append(str(avail.date))

        message = 'Weekly schedule updated.'
        if blocked_dates:
            message = (
                'Weekly schedule updated, and applied to matching upcoming dates. '
                f"Some slots on {', '.join(sorted(set(blocked_dates)))} could not be "
                'removed because they already have confirmed bookings.'
            )

        return StandardResponse.success(message=message)






class AdminBookingListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=['Expert Booking - Admin'], summary='List all bookings')
    def get(self, request):
        qs = ExpertBooking.objects.filter(is_deleted=False)
        if not _is_admin(request.user):
            expert = getattr(request.user, 'expert_profile', None)
            if not expert or not expert.is_active:
                return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
            qs = qs.filter(expert=expert)

        expert_id = request.query_params.get('expert')
        if expert_id:
            qs = qs.filter(expert_id=expert_id)
        status_filter = request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)

        return StandardResponse.success(data=ExpertBookingSerializer(qs, many=True).data)



class AdminConfirmBookingView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=['Expert Booking - Admin'], summary='Confirm a pending booking')
    def post(self, request, pk):
        booking = ExpertBooking.objects.filter(pk=pk, is_deleted=False).first()
        if not booking:
            return StandardResponse.error('Booking not found.', status_code=status.HTTP_404_NOT_FOUND)

        if not _can_manage_expert(request.user, booking.expert):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)

        if booking.status != ExpertBooking.Status.PENDING:
            return StandardResponse.error('Only pending bookings can be confirmed.', status_code=status.HTTP_400_BAD_REQUEST)

        # No manual slot update needed — is_full is computed from confirmed bookings,
        # and this booking's time_slot was already set when the FPO requested it.
        booking.status = ExpertBooking.Status.CONFIRMED
        booking.save(update_fields=['status'])
        notify_context = {'expert_name': booking.expert.name_en, 'date': str(booking.requested_date), 'time': booking.requested_time}
        if booking.fpo.primary_user:
            try:
                send_notification(user=booking.fpo.primary_user, code='expert_booking_confirmed', channel='email', context=notify_context)
            except Exception:
                pass
            try:
                send_notification(user=booking.fpo.primary_user, code='expert_booking_confirmed', channel='in_app', context=notify_context)
            except Exception:
                pass
        return StandardResponse.success(data=ExpertBookingSerializer(booking).data, message='Booking confirmed.')



class AdminRejectBookingView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=['Expert Booking - Admin'], summary='Reject a pending booking with a reason')
    def post(self, request, pk):
        booking = ExpertBooking.objects.filter(pk=pk, is_deleted=False).first()
        if not booking:
            return StandardResponse.error('Booking not found.', status_code=status.HTTP_404_NOT_FOUND)

        if not _can_manage_expert(request.user, booking.expert):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)

        if booking.status != ExpertBooking.Status.PENDING:
            return StandardResponse.error('Only pending bookings can be rejected.', status_code=status.HTTP_400_BAD_REQUEST)

        reason = request.data.get('reason', '')
        booking.status = ExpertBooking.Status.REJECTED
        booking.cancellation_reason = reason
        booking.save(update_fields=['status', 'cancellation_reason'])
        notify_context = {'expert_name': booking.expert.name_en, 'date': str(booking.requested_date), 'time': booking.requested_time, 'reason': reason}
        if booking.fpo.primary_user:
            try:
                send_notification(user=booking.fpo.primary_user, code='expert_booking_rejected', channel='email', context=notify_context)
            except Exception:
                pass
            try:
                send_notification(user=booking.fpo.primary_user, code='expert_booking_rejected', channel='in_app', context=notify_context)
            except Exception:
                pass

        return StandardResponse.success(data=ExpertBookingSerializer(booking).data, message='Booking rejected.')

class RescheduleSerializer(serializers.Serializer):
    new_date = serializers.DateField()
    new_time = serializers.CharField(max_length=10)
    reason = serializers.CharField(required=False, allow_blank=True, default='')




class AdminRescheduleBookingView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=['Expert Booking - Admin'], summary='Propose a new date/time for a booking', request=RescheduleSerializer)
    def post(self, request, pk):
        booking = ExpertBooking.objects.filter(pk=pk, is_deleted=False).first()
        if not booking:
            return StandardResponse.error('Booking not found.', status_code=status.HTTP_404_NOT_FOUND)

        if not _can_manage_expert(request.user, booking.expert):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)

        if booking.status != ExpertBooking.Status.PENDING:
            return StandardResponse.error('Only pending bookings can be rescheduled.', status_code=status.HTTP_400_BAD_REQUEST)

        serializer = RescheduleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        booking.requested_date = data['new_date']
        booking.requested_time = data['new_time']
        booking.cancellation_reason = data.get('reason', '')
        booking.save(update_fields=['requested_date', 'requested_time', 'cancellation_reason'])
        notify_context = {
            'expert_name': booking.expert.name_en, 'date': str(data['new_date']),
            'time': data['new_time'], 'reason': data.get('reason', ''),
        }
        if booking.fpo.primary_user:
            try:
                send_notification(user=booking.fpo.primary_user, code='expert_booking_rescheduled', channel='email', context=notify_context)
            except Exception:
                pass
            try:
                send_notification(user=booking.fpo.primary_user, code='expert_booking_rescheduled', channel='in_app', context=notify_context)
            except Exception:
                pass

        return StandardResponse.success(data=ExpertBookingSerializer(booking).data, message='Booking rescheduled. Awaiting FPO confirmation.')


class AdminCancelBookingView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=['Expert Booking - Admin'], summary='Expert cancels a confirmed booking')
    def post(self, request, pk):
        booking = ExpertBooking.objects.filter(pk=pk, is_deleted=False).first()
        if not booking:
            return StandardResponse.error('Booking not found.', status_code=status.HTTP_404_NOT_FOUND)

        if not _can_manage_expert(request.user, booking.expert):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)

        if booking.status != ExpertBooking.Status.CONFIRMED:
            return StandardResponse.error(
                'Only confirmed bookings can be cancelled this way.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        reason = request.data.get('reason', '')
        booking.status = ExpertBooking.Status.CANCELLED
        booking.cancellation_reason = reason
        booking.save(update_fields=['status', 'cancellation_reason'])

        notify_context = {
            'expert_name': booking.expert.name_en,
            'date': str(booking.requested_date),
            'time': booking.requested_time,
            'reason': reason,
        }
        if booking.fpo.primary_user:
            try:
                send_notification(
                    user=booking.fpo.primary_user, code='expert_cancelled_confirmed_booking',
                    channel='email', context=notify_context,
                )
            except Exception:
                pass
            try:
                send_notification(
                    user=booking.fpo.primary_user, code='expert_cancelled_confirmed_booking',
                    channel='in_app', context=notify_context,
                )
            except Exception:
                pass

        return StandardResponse.success(data=ExpertBookingSerializer(booking).data, message='Booking cancelled.')


class FpoBookingListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=['Expert Booking'], summary="List the FPO's own bookings")
    def get(self, request):
        fpo = _get_fpo(request.user)
        if not fpo:
            return StandardResponse.error(
                'FPO not found.', status_code=status.HTTP_404_NOT_FOUND,
            )

        bookings = ExpertBooking.objects.filter(fpo=fpo, is_deleted=False)
        expert_id = request.query_params.get('expert_id')
        if expert_id:
            bookings = bookings.filter(expert_id=expert_id)

        bookings = bookings.order_by('-requested_date')
        return StandardResponse.success(
            data=ExpertBookingSerializer(bookings, many=True).data,
        )