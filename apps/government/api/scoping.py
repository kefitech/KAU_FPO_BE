from rest_framework import serializers

from apps.database.models.government import GovernmentOfficialProfile


def clean_jurisdiction_districts(attrs):
    """
    Shared by the admin and self-registration serializers. Folds the legacy single
    `assigned_district` into the `assigned_districts` list, de-dupes it, and requires
    at least one district for district jurisdiction (empty when state-wide).
    """
    districts = list(attrs.get('assigned_districts') or [])
    legacy = attrs.pop('assigned_district', None)
    if legacy:
        districts.append(legacy)
    districts = list(dict.fromkeys(districts))

    if attrs['jurisdiction_type'] == 'district' and not districts:
        raise serializers.ValidationError({'assigned_districts': 'Select at least one district.'})
    attrs['assigned_districts'] = districts if attrs['jurisdiction_type'] == 'district' else []
    return attrs


def get_govt_profile(user):
    if not user or not user.is_authenticated:
        return None
    return GovernmentOfficialProfile.objects.filter(user=user).first()


def is_government_user(user):
    return get_govt_profile(user) is not None


def get_jurisdiction_scope(user):
    """
    Returns a dict describing scope:
      {'type': 'ALL'}
      {'type': 'district', 'values': [<district_code>]}
    or None if the user has no usable jurisdiction.
    """
    profile = get_govt_profile(user)
    if not profile:
        return None
    if profile.jurisdiction_type == 'state':
        return {'type': 'ALL'}
    if profile.jurisdiction_type == 'district' and profile.assigned_districts:
        return {'type': 'district', 'values': list(profile.assigned_districts)}
    return None


def scope_fpo_qs(qs, user):
    scope = get_jurisdiction_scope(user)
    if not scope:
        return qs.none()
    if scope['type'] == 'ALL':
        return qs
    return qs.filter(district__in=scope['values'])


def is_fpo_assigned(fpo, user):
    scope = get_jurisdiction_scope(user)
    if not scope:
        return False
    if scope['type'] == 'ALL':
        return True
    return fpo.district in scope['values']


def get_fpo_scoped(fpo_id, user):
    from apps.database.models.fpo import FPO
    scope = get_jurisdiction_scope(user)
    qs = FPO.objects.filter(id=fpo_id)
    if not scope:
        return None
    if scope['type'] != 'ALL':
        qs = qs.filter(district__in=scope['values'])
    return qs.select_related('primary_user').first()
