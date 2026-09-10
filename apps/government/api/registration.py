"""
Public self-registration for government officials and facilitators.
POST /api/government/register/ - AllowAny, creates a pending account.
Requires Super Admin or Sub Admin approval before the account can log in.
"""
from django.contrib.auth.models import User
from rest_framework import serializers, status
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny

from apps.core.utils.constants import UserRole, District
from apps.core.utils.responses import StandardResponse
from apps.database.models.government import GovernmentOfficialProfile, USER_CATEGORY_CHOICES

from apps.government.api.validators import validate_id_number


class GovernmentRegistrationSerializer(serializers.Serializer):
    email = serializers.EmailField()
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150, required=False, default='')
    phone = serializers.CharField(max_length=15)
    password = serializers.CharField(min_length=8, write_only=True)
    designation = serializers.CharField(max_length=200)
    department = serializers.CharField(max_length=200)
    user_category = serializers.ChoiceField(choices=USER_CATEGORY_CHOICES)
    id_number = serializers.CharField(max_length=30)
    jurisdiction_type = serializers.ChoiceField(choices=[('district', 'District'), ('state', 'State')])
    assigned_district = serializers.ChoiceField(choices=District.choices, required=False, allow_null=True)

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError('A user with this email already exists.')
        return value.lower()

    def validate(self, attrs):
        if attrs['jurisdiction_type'] == 'district' and not attrs.get('assigned_district'):
            raise serializers.ValidationError({
                'assigned_district': 'Required when jurisdiction_type=district.'
            })

        is_valid, error = validate_id_number(attrs['user_category'], attrs['id_number'])
        if not is_valid:
            raise serializers.ValidationError({'id_number': error})

        return attrs


class GovernmentRegistrationView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = GovernmentRegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        user = User.objects.create_user(
            username=data['email'],
            email=data['email'],
            password=data['password'],
            first_name=data['first_name'],
            last_name=data.get('last_name', ''),
            is_active=False,
        )

        from django.contrib.auth.models import Group
        govt_group, _ = Group.objects.get_or_create(name=UserRole.GOVERNMENT)
        user.groups.add(govt_group)

        GovernmentOfficialProfile.objects.create(
            user=user,
            designation=data['designation'],
            department=data['department'],
            jurisdiction_type=data['jurisdiction_type'],
            assigned_district=data.get('assigned_district') if data['jurisdiction_type'] == 'district' else None,
            user_category=data['user_category'],
            id_number=data['id_number'],
            registration_status='pending',
        )

        profile = user.profile
        if data.get('phone'):
            profile.phone = data['phone']
            profile.save(update_fields=['phone'])

        return StandardResponse.success(
            data={'id': user.id, 'status': 'pending'},
            message='Registration submitted. Your account will be reviewed by an administrator before you can log in.',
            status_code=201,
        )
