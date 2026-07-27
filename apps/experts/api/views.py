"""
Expert Directory — FPO-facing Browse & Contact Enquiry
========================================================
GET   /api/experts/            — browse active experts (filter: category, district, search)
GET   /api/experts/{id}/       — expert detail
POST  /api/experts/{id}/enquiry/ — submit contact enquiry (sends email to expert)
"""

from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView

from apps.core.utils.constants import UserRole
from apps.core.utils.pagination import StandardPagination
from apps.core.utils.responses import StandardResponse
from apps.database.models.schemes import Expert, ExpertEnquiry
from apps.database.models.fpo import FPO, FPOUserMembership
from apps.notifications.services import send_notification


class ExpertPublicSerializer(serializers.ModelSerializer):
    category_display = serializers.SerializerMethodField()
    name             = serializers.SerializerMethodField()

    class Meta:
        model = Expert
        fields = [
            'id', 'name', 'name_en', 'name_ml', 'designation', 'organisation',
            'primary_expertise', 'secondary_expertise', 'district',
            'email', 'phone', 'category', 'category_display',
        ]

    def get_category_display(self, obj):
        return obj.get_category_display()

    def get_name(self, obj):
        lang = self.context.get('language', 'en')
        if lang == 'ml' and obj.name_ml:
            return obj.name_ml
        return obj.name_en


class ExpertEnquirySerializer(serializers.Serializer):
    message = serializers.CharField(
        min_length=20,
        help_text='Your message to the expert (min 20 characters).',
    )


class ExpertListView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=['Expert Directory'],
        summary='Browse experts',
        description=(
            'Returns all active experts in the directory.\n\n'
            '**Filters:**\n'
            '- `category` — scientist / trainer / banker / facilitator\n'
            '- `district` — Kerala district code (e.g. TRS, TVM)\n'
            '- `search` — keyword search in name and expertise\n\n'
            '**Language:** Send `X-Language: ml` header for Malayalam names.'
        ),
    )
    def get(self, request):
        qs = Expert.objects.filter(is_deleted=False, is_active=True).order_by('order', 'name_en')

        category = request.query_params.get('category')
        if category:
            qs = qs.filter(category=category)

        district = request.query_params.get('district')
        if district:
            qs = qs.filter(district=district)

        search = request.query_params.get('search')
        if search:
            from django.db.models import Q
            qs = qs.filter(
                Q(name_en__icontains=search) |
                Q(primary_expertise__icontains=search) |
                Q(secondary_expertise__icontains=search) |
                Q(organisation__icontains=search)
            )

        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = ExpertPublicSerializer(
            page, many=True, context={'language': getattr(request, 'language', 'en')}
        )
        return paginator.get_paginated_response(serializer.data)


class ExpertDetailView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(tags=['Expert Directory'], summary='Expert detail')
    def get(self, request, pk):
        try:
            expert = Expert.objects.get(pk=pk, is_deleted=False, is_active=True)
        except Expert.DoesNotExist:
            return StandardResponse.error('Expert not found.', status_code=status.HTTP_404_NOT_FOUND)

        serializer = ExpertPublicSerializer(
            expert, context={'language': getattr(request, 'language', 'en')}
        )
        return StandardResponse.success(data=serializer.data)


class ExpertEnquiryView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=['Expert Directory'],
        summary='Submit enquiry to an expert',
        description=(
            'Sends a contact message to the expert via email.\n\n'
            '- FPO must be **approved**\n'
            '- Message minimum 20 characters\n'
            '- Expert receives an email with the FPO name and message'
        ),
        request=ExpertEnquirySerializer,
    )
    def post(self, request, pk):
        if not request.user.groups.filter(name=UserRole.FPO_MANAGER).exists():
            return StandardResponse.error('Only FPO members can contact experts.',
                                          status_code=status.HTTP_403_FORBIDDEN)

        try:
            expert = Expert.objects.get(pk=pk, is_deleted=False, is_active=True)
        except Expert.DoesNotExist:
            return StandardResponse.error('Expert not found.', status_code=status.HTTP_404_NOT_FOUND)

        membership = FPOUserMembership.objects.filter(user=request.user, is_active=True).first()
        fpo = membership.fpo if membership else None

        from apps.core.utils.constants import FPOStatus
        if fpo and fpo.status != FPOStatus.APPROVED:
            return StandardResponse.error('Your FPO must be approved to contact experts.',
                                          status_code=status.HTTP_403_FORBIDDEN)

        serializer = ExpertEnquirySerializer(data=request.data)
        if not serializer.is_valid():
            return StandardResponse.error('Validation failed.', errors=serializer.errors,
                                          status_code=status.HTTP_400_BAD_REQUEST)

        message = serializer.validated_data['message']
        user_name = f'{request.user.first_name} {request.user.last_name}'.strip() or request.user.email
        fpo_name = fpo.name if fpo else user_name

        enquiry = ExpertEnquiry.objects.create(
            expert=expert,
            fpo=fpo,
            fpo_user=request.user,
            message=message,
        )

        email_sent = False
        try:
            send_notification(
                user=request.user,
                code='expert_enquiry',
                channel='email',
                context={
                    'expert_name':  expert.name_en,
                    'fpo_name':     fpo_name,
                    'user_name':    user_name,
                    'user_email':   request.user.email,
                    'message':      message,
                },
                override_recipient=expert.email,
            )
            enquiry.email_sent = True
            enquiry.save(update_fields=['email_sent'])
            email_sent = True
        except Exception:
            pass

        return StandardResponse.success(
            data={'enquiry_id': enquiry.id, 'email_sent': email_sent},
            message='Your enquiry has been submitted. The expert will be notified.',
            status_code=status.HTTP_201_CREATED,
        )
