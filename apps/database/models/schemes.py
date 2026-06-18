"""
Schemes & Subsidies and Expert Directory Models
================================================
"""

from django.db import models
from apps.core.models.base import BaseModel


# ─── Schemes ─────────────────────────────────────────────────────────────────

class SchemeCategory(models.TextChoices):
    CREDIT       = 'credit',            'Credit & Finance'
    INSURANCE    = 'insurance',         'Insurance'
    MARKETING    = 'marketing',         'Marketing & Trade'
    INFRA        = 'infrastructure',    'Infrastructure'
    CAPACITY     = 'capacity_building', 'Capacity Building'


class Scheme(BaseModel):
    name_en             = models.CharField(max_length=255)
    name_ml             = models.CharField(max_length=255, blank=True)
    administering_body  = models.CharField(max_length=255)
    category            = models.CharField(max_length=30, choices=SchemeCategory.choices)
    objective           = models.TextField(blank=True)
    eligibility         = models.TextField()
    benefit_details     = models.TextField()
    application_process = models.TextField()
    official_link       = models.URLField(blank=True)
    last_updated        = models.DateField(null=True, blank=True)
    is_active           = models.BooleanField(default=True)
    order               = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['order', 'name_en']

    def __str__(self):
        return self.name_en


# ─── Expert Directory ─────────────────────────────────────────────────────────

class ExpertCategory(models.TextChoices):
    SCIENTIST   = 'scientist',   'Scientist / Researcher'
    TRAINER     = 'trainer',     'Trainer / Extension Worker'
    BANKER      = 'banker',      'Banker / Financial Advisor'
    FACILITATOR = 'facilitator', 'Facilitator / NGO'


class Expert(BaseModel):
    name_en             = models.CharField(max_length=255)
    name_ml             = models.CharField(max_length=255, blank=True)
    designation         = models.CharField(max_length=255)
    organisation        = models.CharField(max_length=255)
    primary_expertise   = models.CharField(max_length=255)
    secondary_expertise = models.CharField(max_length=255, blank=True)
    district            = models.CharField(max_length=10, blank=True)
    email               = models.EmailField()
    phone               = models.CharField(max_length=15, blank=True)
    category            = models.CharField(max_length=20, choices=ExpertCategory.choices)
    is_active           = models.BooleanField(default=True)
    order               = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['order', 'name_en']

    def __str__(self):
        return self.name_en


class ExpertEnquiry(models.Model):
    expert       = models.ForeignKey(Expert, on_delete=models.CASCADE, related_name='enquiries')
    fpo          = models.ForeignKey('database.FPO', on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name='expert_enquiries')
    fpo_user     = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True,
                                     related_name='expert_enquiries')
    message      = models.TextField()
    submitted_at = models.DateTimeField(auto_now_add=True)
    email_sent   = models.BooleanField(default=False)

    class Meta:
        ordering = ['-submitted_at']
