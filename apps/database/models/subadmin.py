from django.db import models
from django.contrib.auth.models import User
from apps.core.models.base import TimeStampedModel
from apps.database.models.fpo import FPO


class SubAdminFPOAssignment(TimeStampedModel):
    fpo = models.OneToOneField(FPO, on_delete=models.CASCADE, related_name='subadmin_assignment')
    subadmin = models.ForeignKey(User, on_delete=models.CASCADE, related_name='fpo_assignments')
    assigned_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='fpo_assignments_made')

    class Meta:
        db_table = 'subadmin_fpo_assignment'
