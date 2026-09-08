"""
Public self-registration for CBBO/NGO officers.
POST /api/cbbo/register/ - AllowAny, creates a pending account.
Mirrors apps/government/api/registration.py.
"""
from django.contrib.auth.models import User, Group
from rest_framework import serializers, status
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny

from apps.core.utils.constants import UserRole, District
from apps.core.utils.responses import StandardResponse
from apps.database.models.cbbo import CBBOAssignment
from apps.database.models.organisation import Organisation
from apps.database.models.cbbo_profile import CBBOOfficerProfile


class CBBORegistrationSerializer(serializers.Serializer):
    email = serializers.EmailField()
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150, required=False, default='')
    phone = serializers.CharField(max_length=15)
    password = serializers.CharField(min_length=8, write_only=True)
    designation = serializers.CharField(max_length=200, required=False, allow_blank=True, default='')
    organisation = serializers.PrimaryKeyRelatedField(queryset=Organisation.objects.filter(is_deleted=False, is_active=True))
    level = serializers.ChoiceField(choices=CBBOAssignment.LEVEL_CHOICES, default=CBBOAssignment.LEVEL_DISTRICT)
    district_codes = serializers.ListField(child=serializers.ChoiceField(choices=District.choices), required=False, default=list)

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError('A user with this email already exists.')
        return value.lower()

    def validate(self, attrs):
        if attrs['level'] == CBBOAssignment.LEVEL_DISTRICT and not attrs.get('district_codes'):
            raise serializers.ValidationError({'district_codes': 'Required when level=district.'})
        return attrs


class CBBORegistrationView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = CBBORegistrationSerializer(data=request.data)
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

        cbbo_group, _ = Group.objects.get_or_create(name=UserRole.CBBO)
        user.groups.add(cbbo_group)

        CBBOOfficerProfile.objects.create(
            user=user,
            organisation=data['organisation'],
            designation=data.get('designation', ''),
            registration_status='pending',
        )

        if data['level'] == CBBOAssignment.LEVEL_STATE:
            CBBOAssignment.objects.create(cbbo=user, level=CBBOAssignment.LEVEL_STATE, district='', is_active=True)
        else:
            CBBOAssignment.objects.bulk_create([
                CBBOAssignment(cbbo=user, level=CBBOAssignment.LEVEL_DISTRICT, district=code, is_active=True)
                for code in dict.fromkeys(data['district_codes'])
            ])

        profile = user.profile
        if data.get('phone'):
            profile.phone = data['phone']
            profile.save(update_fields=['phone'])

        return StandardResponse.success(
            data={'id': user.id, 'status': 'pending'},
            message='Registration submitted. Your account will be reviewed by an administrator before you can log in.',
            status_code=201,
        )


class PublicOrganisationListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        orgs = Organisation.objects.filter(is_deleted=False, is_active=True).order_by('name')
        data = [
            {'id': o.id, 'name': o.name, 'org_type': o.org_type, 'org_type_display': o.get_org_type_display()}
            for o in orgs
        ]
        return StandardResponse.success(data=data)
