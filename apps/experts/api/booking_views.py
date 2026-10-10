"""
Expert Booking API - P2-08

Bookings belong to an individual FPO member and are first come, first served:
booking an open slot confirms it at once, with no expert approval step. A
member may hold at most one appointment per calendar day, with any expert.

FPO member side:
  GET  /api/experts/{id}/availability/    - browse an expert's open slots
  POST /api/experts/{id}/book/            - book a slot (confirmed immediately)
  GET  /api/experts/bookings/             - my bookings
  POST /api/experts/bookings/{id}/cancel/ - cancel my booking (the FPO primary may cancel any)

Expert / admin side:
  POST     /api/experts/admin/{id}/availability/    - set slots per date
  GET/POST /api/experts/admin/{id}/weekly-defaults/ - weekly template
  GET      /api/experts/admin/bookings/             - bookings (an expert sees only their own)
  POST     /api/experts/admin/bookings/{id}/cancel/ - expert cancels a confirmed booking
  confirm / reject / reschedule remain only for legacy pending rows.
"""
from django.conf import settings as django_settings
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.core.utils.constants import UserRole, FPOStatus
from apps.core.utils.responses import StandardResponse
from apps.database.models.schemes import Expert
from apps.database.models.expert_booking import ExpertAvailability, ExpertTimeSlot, ExpertBooking, ExpertWeeklyDefault
from apps.core.services.fpo_permission import has_fpo_permission
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
    user_name = serializers.SerializerMethodField()
    user_email = serializers.SerializerMethodField()
    user_phone = serializers.SerializerMethodField()
    can_cancel = serializers.SerializerMethodField()
    status_display = serializers.SerializerMethodField()

    class Meta:
        model = ExpertBooking
        fields = [
            'id', 'expert', 'expert_name', 'fpo', 'fpo_name', 'fpo_email', 'fpo_phone',
            'fpo_contact_name', 'fpo_application_id', 'fpo_location',
            'fpo_district', 'fpo_registration_number', 'fpo_total_members',
            'user', 'user_name', 'user_email', 'user_phone', 'can_cancel',
            'requested_date', 'requested_time',
            'topic', 'notes', 'status', 'status_display', 'cancellation_reason',
            'created_at', 'updated_at',
        ]

    def get_expert_name(self, obj):
        return obj.expert.name_en

    # The member who made the booking. Rows from before bookings were per user
    # have no user; the fpo_* fields still describe the FPO's primary contact.
    def get_user_name(self, obj):
        if not obj.user:
            return None
        return obj.user.get_full_name() or obj.user.username

    def get_user_email(self, obj):
        return obj.user.email if obj.user else None

    def get_user_phone(self, obj):
        profile = getattr(obj.user, 'profile', None) if obj.user else None
        return profile.phone if profile else None

    def get_can_cancel(self, obj):
        """Whether the requesting user may cancel this booking. Needs `request` in context."""
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return False
        return obj.status in LIVE_STATUSES and _can_cancel_booking(request.user, obj)

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
    notes = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=1000,
        error_messages={'max_length': 'Notes must be 1000 characters or fewer.'},
    )
def _get_fpo(user):
    membership = FPOUserMembership.objects.filter(user=user, is_active=True).first()
    if membership:
        return membership.fpo
    return FPO.objects.filter(primary_user=user, is_deleted=False).first()





def _is_admin(user):
    return user.groups.filter(name__in=[UserRole.SUPER_ADMIN, UserRole.SUB_ADMIN]).exists()


def _can_manage_expert(user, expert):
    return _is_admin(user) or (expert.is_active and expert.user_id and expert.user_id == user.id)


# ---------------------------------------------------------------------------
# Booking rules
# ---------------------------------------------------------------------------
# Longest cancellation reason an FPO member may give (the frontend shows the same limit).
CANCEL_REASON_MAX_CHARS = 300
# How many upcoming appointments one member may hold at a time (stops slot hoarding).
MAX_UPCOMING_BOOKINGS_PER_USER = getattr(django_settings, 'EXPERT_MAX_UPCOMING_BOOKINGS_PER_USER', 5)

# Statuses that hold a place in the calendar.
LIVE_STATUSES = (ExpertBooking.Status.PENDING, ExpertBooking.Status.CONFIRMED)


def _time_str(t):
    return t.strftime('%H:%M')


def _slot_is_past(date, start_time):
    now = timezone.localtime()
    return date < now.date() or (date == now.date() and start_time <= now.time())


def _find_slot(avail, slot_id=None, start_time=None, lock=False):
    """The slot on `avail` picked by id (preferred) or by start time, or None."""
    qs = ExpertTimeSlot.objects.filter(availability=avail, is_deleted=False)
    if lock:
        qs = qs.select_for_update()
    if slot_id:
        return qs.filter(id=slot_id).first()
    return qs.filter(start_time=start_time).first()


def _user_bookings_by_date(user, dates, exclude_pk=None):
    """The member's live bookings on `dates`, keyed by date (earliest first wins)."""
    qs = ExpertBooking.objects.filter(
        user=user, status__in=LIVE_STATUSES, is_deleted=False, requested_date__in=list(dates),
    ).select_related('expert').order_by('requested_time')
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    by_date = {}
    for booking in qs:
        by_date.setdefault(booking.requested_date, booking)
    return by_date


def _user_conflict_error(user, slot, date, exclude_pk=None, subject='You already have'):
    """
    Rules that stop one person holding two places at once: no second booking of
    the same slot, and at most one live booking (with any expert) per calendar
    day. Returns an error message, or None when allowed.
    """
    live = ExpertBooking.objects.filter(user=user, status__in=LIVE_STATUSES, is_deleted=False)
    if exclude_pk:
        live = live.exclude(pk=exclude_pk)

    if live.filter(time_slot=slot).exists():
        return f'{subject} a booking for this exact slot.'

    other = _user_bookings_by_date(user, [date], exclude_pk=exclude_pk).get(date)
    if other:
        return (
            f'{subject} an appointment on {other.requested_date} with {other.expert.name_en} '
            f'at {other.requested_time}. Only one appointment per day is allowed.'
        )
    return None


def _can_cancel_booking(user, booking):
    """
    Only the member who made the booking may cancel it. Legacy rows with no
    booker belong to the FPO's primary user, as in the bookings list.
    """
    if booking.user_id:
        return user.id == booking.user_id
    return user.id == booking.fpo.primary_user_id


def _booking_recipient(booking):
    """Who hears about changes to a booking: the member who made it, else the FPO's primary user."""
    return booking.user or booking.fpo.primary_user


def _remove_slot(slot, user, cancelled, rejected):
    """
    Soft-delete `slot`. Confirmed bookings on it are cancelled and pending
    requests rejected, so no FPO is left holding a booking on a slot that no
    longer exists. Affected bookings are appended to `cancelled` / `rejected`
    for the caller to notify.
    """
    live = ExpertBooking.objects.filter(
        time_slot=slot, status__in=LIVE_STATUSES, is_deleted=False,
    ).select_related('fpo', 'fpo__primary_user', 'user')
    for booking in live:
        if booking.status == ExpertBooking.Status.CONFIRMED:
            booking.status = ExpertBooking.Status.CANCELLED
            booking.cancellation_reason = 'Expert marked this date as unavailable.'
            cancelled.append(booking)
        else:
            booking.status = ExpertBooking.Status.REJECTED
            booking.cancellation_reason = 'Expert removed this time slot.'
            rejected.append(booking)
        booking.save(update_fields=['status', 'cancellation_reason'])
    slot.soft_delete(user=user)


def _notify_expert_in_app(expert, code, context):
    """In-app notification to the expert's own login, when they have one; failures are swallowed."""
    if not expert.user_id:
        return
    try:
        send_notification(user=expert.user, code=code, channel='in_app', context=context)
    except Exception:
        pass


def _notify_booker(booking, code, context):
    """Email + in-app notification to the booking's member; failures are swallowed."""
    recipient = _booking_recipient(booking)
    if not recipient:
        return
    for channel in ('email', 'in_app'):
        try:
            send_notification(user=recipient, code=code, channel=channel, context=context)
        except Exception:
            pass



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

        # One appointment per day: dates the caller already holds a booking on
        # (with any expert) are reported so the calendar can mark them unavailable.
        my_bookings = _user_bookings_by_date(request.user, [a.date for a in avails])

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
            mine = my_bookings.get(a.date)
            data.append({
                'id': a.id,
                'date': str(a.date),
                'time_slots': slots,
                'my_booking': {'expert_name': mine.expert.name_en, 'time': mine.requested_time} if mine else None,
            })

        return StandardResponse.success(data=data)

class CreateBookingView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=['Expert Booking'], summary='Book a slot (first come, first served)', request=CreateBookingSerializer)
    def post(self, request, pk):
        if not request.user.groups.filter(name=UserRole.FPO_MANAGER).exists():
            return StandardResponse.error('Only FPO members can book experts.', status_code=status.HTTP_403_FORBIDDEN)

        fpo = _get_fpo(request.user)
        if not fpo or fpo.status != FPOStatus.APPROVED:
            return StandardResponse.error('Your FPO must be approved to book experts.', status_code=status.HTTP_403_FORBIDDEN)
        if not has_fpo_permission(request.user, fpo, 'can_book_experts'):
            return StandardResponse.error('You do not have permission to book experts.', status_code=status.HTTP_403_FORBIDDEN)

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

        with transaction.atomic():
            # Lock the slot row so two people cannot both take its last place, and
            # the member's own row so a double submit cannot pass the per-user
            # rules twice.
            User.objects.select_for_update().get(pk=request.user.pk)
            slot = _find_slot(avail, slot_id=data.get('time_slot_id'), start_time=data['requested_time'], lock=True)
            if not slot:
                return StandardResponse.error('That time slot does not exist.', status_code=status.HTTP_400_BAD_REQUEST)
            if _slot_is_past(avail.date, slot.start_time):
                return StandardResponse.error('That time slot has already passed.', status_code=status.HTTP_400_BAD_REQUEST)
            if slot.is_full:
                return StandardResponse.error('That slot is already fully booked.', status_code=status.HTTP_400_BAD_REQUEST)

            upcoming = ExpertBooking.objects.filter(
                user=request.user, status=ExpertBooking.Status.CONFIRMED, is_deleted=False,
                requested_date__gte=timezone.localdate(),
            ).count()
            if upcoming >= MAX_UPCOMING_BOOKINGS_PER_USER:
                return StandardResponse.error(
                    f'You already have {upcoming} upcoming appointments. Cancel one before booking another.',
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

            error = _user_conflict_error(request.user, slot, avail.date)
            if error:
                return StandardResponse.error(error, status_code=status.HTTP_400_BAD_REQUEST)

            # First come, first served: the slot is confirmed the moment it is booked.
            booking = ExpertBooking.objects.create(
                expert=expert, fpo=fpo, user=request.user, time_slot=slot,
                requested_date=avail.date, requested_time=_time_str(slot.start_time),
                topic=data['topic'], notes=data.get('notes', ''),
                status=ExpertBooking.Status.CONFIRMED,
                created_by=request.user,
            )

        user_name = request.user.get_full_name() or request.user.username
        expert_context = {
            'expert_name': expert.name_en, 'fpo_name': fpo.name, 'user_name': user_name,
            'date': str(booking.requested_date), 'time': booking.requested_time, 'topic': booking.topic,
        }
        try:
            send_notification(
                user=expert.user or request.user, code='expert_booking_new', channel='email',
                context=expert_context, override_recipient=expert.email,
            )
        except Exception:
            pass
        _notify_expert_in_app(expert, 'expert_booking_new', expert_context)
        _notify_booker(booking, 'expert_booking_receipt', {
            'expert_name': expert.name_en, 'date': str(booking.requested_date), 'time': booking.requested_time,
        })

        return StandardResponse.success(
            data=ExpertBookingSerializer(booking, context={'request': request}).data,
            message='Appointment booked.',
            status_code=status.HTTP_201_CREATED,
        )


class CancelBookingView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=['Expert Booking'], summary='Cancel my booking')
    def post(self, request, pk):
        fpo = _get_fpo(request.user)
        booking = (
            ExpertBooking.objects.filter(pk=pk, fpo=fpo, is_deleted=False)
            .select_related('expert', 'expert__user', 'fpo', 'user')
            .first()
        )
        if not booking:
            return StandardResponse.error('Booking not found.', status_code=status.HTTP_404_NOT_FOUND)
        if not _can_cancel_booking(request.user, booking):
            return StandardResponse.error('You can only cancel your own bookings.', status_code=status.HTTP_403_FORBIDDEN)

        if booking.status not in LIVE_STATUSES:
            return StandardResponse.error('This booking cannot be cancelled.', status_code=status.HTTP_400_BAD_REQUEST)

        reason = (request.data.get('reason') or '').strip()
        if len(reason) > CANCEL_REASON_MAX_CHARS:
            return StandardResponse.error(
                f'Reason must be {CANCEL_REASON_MAX_CHARS} characters or fewer.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        booking.status = ExpertBooking.Status.CANCELLED
        booking.cancellation_reason = reason
        booking.save(update_fields=['status', 'cancellation_reason'])

        booker = booking.user or request.user
        expert_context = {
            'fpo_name': fpo.name, 'user_name': booker.get_full_name() or booker.username,
            'date': str(booking.requested_date), 'time': booking.requested_time, 'reason': reason,
        }
        try:
            send_notification(
                user=booking.expert.user or request.user, code='expert_booking_cancelled', channel='email',
                context=expert_context, override_recipient=booking.expert.email,
            )
        except Exception:
            pass
        _notify_expert_in_app(booking.expert, 'expert_booking_cancelled', expert_context)

        return StandardResponse.success(
            data=ExpertBookingSerializer(booking, context={'request': request}).data,
            message='Booking cancelled.',
        )

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
        rejected_bookings = []
        for slot_group in serializer.validated_data['slots']:
            avail, _ = ExpertAvailability.objects.get_or_create(
                expert=expert, date=slot_group['date'],
            )
            if not avail.is_custom:
                avail.is_custom = True
                avail.save(update_fields=['is_custom'])
            submitted = {(s['start'], s['end']) for s in slot_group['time_slots']}

            # Slots the expert has un-chosen are removed. Confirmed bookings on
            # them are auto-cancelled and pending requests auto-rejected, so no
            # FPO is left holding a booking on a slot that no longer exists.
            candidates = avail.time_slots.filter(is_deleted=False)
            date_has_cancelled_booking = False
            for old_slot in candidates:
                key = (old_slot.start_time.strftime('%H:%M'), old_slot.end_time.strftime('%H:%M'))
                if key not in submitted:
                    cancelled_before = len(affected_bookings)
                    _remove_slot(old_slot, request.user, affected_bookings, rejected_bookings)
                    if len(affected_bookings) > cancelled_before:
                        date_has_cancelled_booking = True
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
        # Notify members exactly once per call, after all slot_groups are processed.
        for booking in affected_bookings:
            _notify_booker(booking, 'expert_cancelled_confirmed_booking', {
                'expert_name': expert.name_en,
                'fpo_name': booking.fpo.name,
                'date': str(booking.requested_date),
                'time': booking.requested_time,
                'reason': booking.cancellation_reason,
            })

        for booking in rejected_bookings:
            _notify_booker(booking, 'expert_booking_rejected', {
                'expert_name': expert.name_en,
                'date': str(booking.requested_date),
                'time': booking.requested_time,
                'reason': booking.cancellation_reason,
            })

        notes = []
        if cancelled_dates:
            notes.append(
                f"Confirmed bookings on {', '.join(cancelled_dates)} were automatically cancelled "
                'because the expert marked those dates unavailable.'
            )
        if rejected_bookings:
            notes.append(f'{len(rejected_bookings)} pending request(s) on removed slots were declined.')
        message = 'Availability updated.'
        if notes:
            message = f"Availability updated. {' '.join(notes)} Affected FPOs have been notified."

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
        rejected_bookings = []
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
                            # Only pending requests can be on it; they are rejected.
                            _remove_slot(old_slot, request.user, [], rejected_bookings)
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

        for booking in rejected_bookings:
            _notify_booker(booking, 'expert_booking_rejected', {
                'expert_name': expert.name_en,
                'date': str(booking.requested_date),
                'time': booking.requested_time,
                'reason': booking.cancellation_reason,
            })

        notes = []
        if blocked_dates:
            notes.append(
                f"Some slots on {', '.join(sorted(set(blocked_dates)))} could not be removed "
                'because they already have confirmed bookings.'
            )
        if rejected_bookings:
            notes.append(
                f'{len(rejected_bookings)} pending request(s) on removed slots were declined '
                'and the FPOs notified.'
            )
        message = 'Weekly schedule updated.'
        if notes:
            message = f"Weekly schedule updated, and applied to matching upcoming dates. {' '.join(notes)}"

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

        qs = qs.select_related('expert', 'fpo', 'fpo__primary_user', 'user')
        return StandardResponse.success(data=ExpertBookingSerializer(qs, many=True, context={'request': request}).data)



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

        with transaction.atomic():
            # Pending requests do not consume capacity, so several FPOs may be
            # waiting on the same slot. Lock it and re-check before confirming.
            slot = ExpertTimeSlot.objects.select_for_update().filter(
                pk=booking.time_slot_id, is_deleted=False,
            ).first()
            if not slot:
                return StandardResponse.error(
                    'The requested time slot no longer exists. Reject or reschedule this request instead.',
                    status_code=status.HTTP_400_BAD_REQUEST,
                )
            if slot.is_full:
                return StandardResponse.error(
                    'This slot has already reached its booking limit. Reject or reschedule this request instead.',
                    status_code=status.HTTP_400_BAD_REQUEST,
                )
            booking.status = ExpertBooking.Status.CONFIRMED
            booking.save(update_fields=['status'])
        _notify_booker(booking, 'expert_booking_confirmed', {
            'expert_name': booking.expert.name_en, 'date': str(booking.requested_date), 'time': booking.requested_time,
        })
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
        _notify_booker(booking, 'expert_booking_rejected', {
            'expert_name': booking.expert.name_en, 'date': str(booking.requested_date),
            'time': booking.requested_time, 'reason': reason,
        })

        return StandardResponse.success(data=ExpertBookingSerializer(booking).data, message='Booking rejected.')

class RescheduleSerializer(serializers.Serializer):
    new_date = serializers.DateField()
    new_time = serializers.TimeField(required=False)
    time_slot_id = serializers.IntegerField(required=False)
    reason = serializers.CharField(required=False, allow_blank=True, default='')

    def validate(self, attrs):
        if not attrs.get('new_time') and not attrs.get('time_slot_id'):
            raise serializers.ValidationError('Provide new_time or time_slot_id.')
        return attrs




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

        avail = ExpertAvailability.objects.filter(
            expert=booking.expert, date=data['new_date'], is_deleted=False,
        ).first()
        if not avail:
            return StandardResponse.error(
                'No availability found for that date. Add a slot for it first.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            slot = _find_slot(avail, slot_id=data.get('time_slot_id'), start_time=data.get('new_time'), lock=True)
            if not slot:
                return StandardResponse.error('That time slot does not exist on the new date.', status_code=status.HTTP_400_BAD_REQUEST)
            if _slot_is_past(avail.date, slot.start_time):
                return StandardResponse.error('That time slot has already passed.', status_code=status.HTTP_400_BAD_REQUEST)
            if slot.is_full:
                return StandardResponse.error('That slot is already fully booked.', status_code=status.HTTP_400_BAD_REQUEST)

            if booking.user:
                error = _user_conflict_error(
                    booking.user, slot, avail.date, exclude_pk=booking.pk, subject='This member already has',
                )
                if error:
                    return StandardResponse.error(error, status_code=status.HTTP_400_BAD_REQUEST)

            # Keep the slot pointer in step with the new date/time, otherwise the
            # booking keeps consuming capacity on the old slot once confirmed.
            booking.time_slot = slot
            booking.requested_date = avail.date
            booking.requested_time = _time_str(slot.start_time)
            booking.cancellation_reason = data.get('reason', '')
            booking.save(update_fields=['time_slot', 'requested_date', 'requested_time', 'cancellation_reason'])

        _notify_booker(booking, 'expert_booking_rescheduled', {
            'expert_name': booking.expert.name_en, 'date': str(booking.requested_date),
            'time': booking.requested_time, 'reason': data.get('reason', ''),
        })

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

        _notify_booker(booking, 'expert_cancelled_confirmed_booking', {
            'expert_name': booking.expert.name_en,
            'date': str(booking.requested_date),
            'time': booking.requested_time,
            'reason': reason,
        })

        return StandardResponse.success(data=ExpertBookingSerializer(booking).data, message='Booking cancelled.')


class FpoBookingListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=['Expert Booking'],
        summary='List my bookings',
    )
    def get(self, request):
        fpo = _get_fpo(request.user)
        if not fpo:
            return StandardResponse.error(
                'FPO not found.', status_code=status.HTTP_404_NOT_FOUND,
            )

        # Bookings belong to the member who made them; nobody sees another
        # member's. Rows from before bookings were per user belong to the owner.
        mine = Q(user=request.user)
        if fpo.primary_user_id == request.user.id:
            mine |= Q(user__isnull=True)
        bookings = ExpertBooking.objects.filter(mine, fpo=fpo, is_deleted=False)
        expert_id = request.query_params.get('expert_id') or request.query_params.get('expert')
        if expert_id:
            bookings = bookings.filter(expert_id=expert_id)

        bookings = bookings.select_related('expert', 'fpo', 'fpo__primary_user', 'user').order_by('-requested_date')
        return StandardResponse.success(
            data=ExpertBookingSerializer(bookings, many=True, context={'request': request}).data,
        )