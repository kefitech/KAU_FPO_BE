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
from apps.database.models.expert_booking import ExpertAvailability, ExpertBooking
from apps.database.models.fpo import FPO, FPOUserMembership
from apps.notifications.services import send_notification


class ExpertAvailabilitySerializer(serializers.ModelSerializer):
    class Meta:
        model = ExpertAvailability
        fields = ['id', 'date', 'time_slots']


class SetAvailabilitySerializer(serializers.Serializer):
    date = serializers.DateField()
    time_slots = serializers.ListField(child=serializers.DictField())


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
    status_display = serializers.SerializerMethodField()

    class Meta:
        model = ExpertBooking
        fields = [
            'id', 'expert', 'expert_name', 'fpo', 'fpo_name', 'fpo_email', 'fpo_phone', 'fpo_contact_name', 'fpo_application_id', 'fpo_location',
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

    def get_status_display(self, obj):
        return obj.get_status_display()


class CreateBookingSerializer(serializers.Serializer):
    requested_date = serializers.DateField()
    requested_time = serializers.CharField(max_length=10)
    topic = serializers.CharField(max_length=500, required=False, allow_blank=True, default='')
    notes = serializers.CharField(required=False, allow_blank=True, default='')
def _get_fpo(user):
    membership = FPOUserMembership.objects.filter(user=user, is_active=True).first()
    if membership:
        return membership.fpo
    return FPO.objects.filter(primary_user=user, is_deleted=False).first()





def _is_admin(user):
    return user.groups.filter(name__in=[UserRole.SUPER_ADMIN, UserRole.SUB_ADMIN]).exists()


def _can_manage_expert(user, expert):
    return _is_admin(user) or (expert.user_id and expert.user_id == user.id)



class ExpertAvailabilityView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=['Expert Booking'], summary="Browse an expert's open slots")
    def get(self, request, pk):
        try:
            expert = Expert.objects.get(pk=pk, is_deleted=False, is_active=True)
        except Expert.DoesNotExist:
            return StandardResponse.error('Expert not found.', status_code=status.HTTP_404_NOT_FOUND)

        from datetime import date as date_cls
        qs = ExpertAvailability.objects.filter(
            expert=expert, is_deleted=False, date__gte=date_cls.today()
        ).order_by('date')

        data = ExpertAvailabilitySerializer(qs, many=True).data
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

        slot = next((s for s in avail.time_slots if s.get('start') == data['requested_time']), None)
        if not slot:
            return StandardResponse.error('That time slot does not exist.', status_code=status.HTTP_400_BAD_REQUEST)
        if slot.get('is_booked'):
            return StandardResponse.error('That slot is already booked.', status_code=status.HTTP_400_BAD_REQUEST)

        booking = ExpertBooking.objects.create(
            expert=expert, fpo=fpo,
            requested_date=data['requested_date'], requested_time=data['requested_time'],
            topic=data.get('topic', ''), notes=data.get('notes', ''),
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
        for slot_group in serializer.validated_data['slots']:
            obj, _ = ExpertAvailability.objects.update_or_create(
                expert=expert, date=slot_group['date'],
                defaults={'time_slots': slot_group['time_slots']},
            )
            results.append(obj)

        return StandardResponse.success(
            data=ExpertAvailabilitySerializer(results, many=True).data,
            message='Availability updated.',
        )





class AdminBookingListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=['Expert Booking - Admin'], summary='List all bookings')
    def get(self, request):
        qs = ExpertBooking.objects.filter(is_deleted=False)
        if not _is_admin(request.user):
            expert = getattr(request.user, 'expert_profile', None)
            if not expert:
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

        avail = ExpertAvailability.objects.filter(expert=booking.expert, date=booking.requested_date, is_deleted=False).first()
        if avail:
            for slot in avail.time_slots:
                if slot.get('start') == booking.requested_time:
                    slot['is_booked'] = True
            avail.save(update_fields=['time_slots'])

        booking.status = ExpertBooking.Status.CONFIRMED
        booking.save(update_fields=['status'])

        notify_context = {'expert_name': booking.expert.name_en, 'date': str(booking.requested_date), 'time': booking.requested_time}
        if booking.fpo.primary_user:
            try:
                send_notification(
                    user=booking.fpo.primary_user, code='expert_booking_confirmed', channel='email',
                    context=notify_context,
                )
            except Exception:
                pass
            try:
                send_notification(
                    user=booking.fpo.primary_user, code='expert_booking_confirmed', channel='in_app',
                    context=notify_context,
                )
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
                send_notification(
                    user=booking.fpo.primary_user, code='expert_booking_rejected', channel='email',
                    context=notify_context,
                )
            except Exception:
                pass
            try:
                send_notification(
                    user=booking.fpo.primary_user, code='expert_booking_rejected', channel='in_app',
                    context=notify_context,
                )
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
                send_notification(
                    user=booking.fpo.primary_user, code='expert_booking_rescheduled', channel='email',
                    context=notify_context,
                )
            except Exception:
                pass
            try:
                send_notification(
                    user=booking.fpo.primary_user, code='expert_booking_rescheduled', channel='in_app',
                    context=notify_context,
                )
            except Exception:
                pass

        return StandardResponse.success(data=ExpertBookingSerializer(booking).data, message='Booking rescheduled. Awaiting FPO confirmation.')
