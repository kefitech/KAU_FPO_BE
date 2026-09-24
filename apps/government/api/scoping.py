from apps.database.models.government import GovernmentOfficialProfile


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
      {'type': 'block', 'values': [<block_code>]}
    or None if the user has no usable jurisdiction.
    """
    profile = get_govt_profile(user)
    if not profile:
        return None
    if profile.jurisdiction_type == 'state':
        return {'type': 'ALL'}
    if profile.jurisdiction_type == 'block' and profile.assigned_block:
        return {'type': 'block', 'values': [profile.assigned_block]}
    if profile.jurisdiction_type == 'district' and profile.assigned_district:
        return {'type': 'district', 'values': [profile.assigned_district]}
    return None


def scope_fpo_qs(qs, user):
    scope = get_jurisdiction_scope(user)
    if not scope:
        return qs.none()
    if scope['type'] == 'ALL':
        return qs
    if scope['type'] == 'block':
        return qs.filter(block_taluk__in=scope['values'])
    return qs.filter(district__in=scope['values'])


def is_fpo_assigned(fpo, user):
    scope = get_jurisdiction_scope(user)
    if not scope:
        return False
    if scope['type'] == 'ALL':
        return True
    if scope['type'] == 'block':
        return fpo.block_taluk in scope['values']
    return fpo.district in scope['values']


def get_fpo_scoped(fpo_id, user):
    from apps.database.models.fpo import FPO
    scope = get_jurisdiction_scope(user)
    qs = FPO.objects.filter(id=fpo_id)
    if not scope:
        return None
    if scope['type'] == 'block':
        qs = qs.filter(block_taluk__in=scope['values'])
    elif scope['type'] != 'ALL':
        qs = qs.filter(district__in=scope['values'])
    return qs.select_related('primary_user').first()
