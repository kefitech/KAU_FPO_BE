from django.contrib.auth.models import User
from django.db import models

from apps.core.models.base import BaseModel, TimeStampedModel
from apps.core.utils.constants import District


class SubAdminDistrictAssignment(BaseModel):
    """Which district a sub-admin currently owns. One row per sub-admin.

    KAU suggestion #1 — replaced the old manual per-FPO assignment.
    scope_fpo_queryset uses this row to grant the sub-admin visibility of
    every FPO whose district matches; without it they see nothing.

    Uses BaseModel — created_by is the super admin who did the assignment,
    updated_by is whoever last edited the row (should never happen in
    practice; use SubAdminDistrictTransfer for moves instead).
    """
    subadmin = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name='district_assignment',
    )
    district = models.CharField(max_length=5, choices=District.choices)

    class Meta:
        db_table = 'subadmin_district_assignment'
        indexes  = [models.Index(fields=['district'])]

    def __str__(self):
        return f"{self.subadmin.email} → {self.get_district_display()}"


class SubAdminDistrictTransfer(TimeStampedModel):
    """Append-only audit log — one row per district move.

    Includes the very first assignment (from_district blank).
    Never edited, never deleted. `transferred_by` is the super admin who
    triggered the move; more readable than inherited created_by here.
    """
    subadmin       = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='district_transfers',
    )
    from_district  = models.CharField(
        max_length=5, choices=District.choices, blank=True,
        help_text='Blank on first assignment.',
    )
    to_district    = models.CharField(max_length=5, choices=District.choices)
    reason         = models.TextField(blank=True)
    transferred_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name='+',
    )

    class Meta:
        db_table = 'subadmin_district_transfer'
        indexes  = [models.Index(fields=['subadmin', '-created_at'])]
        ordering = ['-created_at']

    def __str__(self):
        arrow = f"{self.from_district or '—'} → {self.to_district}"
        return f"{self.subadmin.email}: {arrow}"


class SubAdminConfig(BaseModel):
    """Editable configuration for sub-admin caps + expiry windows.

    Singleton-per-key: one row per config knob. Values are integers.
    Cached in Redis under `subadmin:config`, busted on every write.

    Known keys (seeded by 0116_seed_subadmin_config_defaults):
      global_cap                    default 30
      scheme_expiry_days            default 5
      training_expiry_days          default 5
      district_cap_<CODE>           optional per-district overrides
    """
    key         = models.CharField(max_length=50, unique=True)
    value       = models.IntegerField()
    description = models.CharField(max_length=200, blank=True)

    class Meta:
        db_table = 'subadmin_config'
        ordering = ['key']

    def __str__(self):
        return f"{self.key} = {self.value}"
