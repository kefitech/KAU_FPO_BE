"""
AI Crop Recommendations Models — P2-06
Django acts as proxy to FastAPI ML service on port 8001 (internal only).
"""
from django.db import models
from django.db.models.functions import Lower

from apps.core.models.base import BaseModel


class MLModelVersion(BaseModel):
    version_code = models.CharField(
        max_length=20, unique=True,
        help_text='e.g. v1.2.0'
    )
    description = models.TextField()
    is_active = models.BooleanField(
        default=False,
        help_text='Only ONE version can be active at a time'
    )
    deployed_at = models.DateTimeField()
    model_file_path = models.CharField(
        max_length=500,
        help_text='Path inside ml_models Docker volume'
    )
    training_metrics = models.JSONField(
        null=True, blank=True, default=None,
        help_text='Full metrics from the ml_service /train/ endpoint '
                   '(accuracy, feature importances, leave-one-zone-out CV, '
                   'class balance) when this version came from a CSV '
                   'retrain. Null for versions registered via direct '
                   'model-file upload, since that flow has no metrics.'
    )
    class Status(models.TextChoices):
        TRAINING = 'training', 'Training'
        READY = 'ready', 'Ready'
        FAILED = 'failed', 'Failed'

    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.READY,
        help_text='training while a Celery retrain job is running; ready once '
                  'the model file exists (or was uploaded directly); failed if '
                  'training did not complete -- see training_error.'
    )
    training_error = models.TextField(
        blank=True, default='',
        help_text='Why training failed, verbatim from the ML service or the task. '
                  'Empty unless status is failed.'
    )
    class Meta:
        verbose_name = 'ML Model Version'
        verbose_name_plural = 'ML Model Versions'

    def save(self, *args, **kwargs):
        if self.is_active:
            MLModelVersion.objects.exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.version_code} {'(active)' if self.is_active else ''}"

class CropRecommendation(BaseModel):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        PROCESSING = 'processing', 'Processing'
        COMPLETED = 'completed', 'Completed'
        FAILED = 'failed', 'Failed'

    fpo = models.ForeignKey(
        'database.FPO', on_delete=models.CASCADE, related_name='recommendations'
    )
    model_version = models.ForeignKey(
        MLModelVersion, on_delete=models.PROTECT,
        help_text='Stored for audit and explainability — SRS §3.2.1'
    )
    financial_year = models.CharField(max_length=10, help_text='e.g. 2025-26')
    input_snapshot = models.JSONField(
        help_text='District, zone, soil type, season at time of request'
    )
    recommendations = models.JSONField(
        default=list,
        help_text='[{crop, confidence, reasoning, estimated_yield}]'
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING,
        help_text='Tracks the async request lifecycle — pending while '
                   'queued for Celery, processing while the FastAPI call '
                   'is in flight, completed/failed once resolved.'
    )
    feedback_rating = models.IntegerField(
        null=True, blank=True,
        help_text='FPO rates the recommendation 1–5'
    )
    feedback_comment = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Crop Recommendation'
        verbose_name_plural = 'Crop Recommendations'
        unique_together = ('fpo', 'financial_year')
        # One active recommendation per FPO per financial year

    def __str__(self):
        return f"{self.fpo} — {self.financial_year} ({self.status})"


# ─────────────────────────────────────────────────────────────────────────────
# Crop Package of Practices (Aravind — P2-06 knowledge base)
# ─────────────────────────────────────────────────────────────────────────────

class CropPackageOfPractices(BaseModel):
    """
    Real cultivation guidance per crop, sourced from KAU's official
    "Package of Practices Recommendations: Crops" publication.
    Shown when an FPO taps a crop in their recommendation list.
    """
    crop_name = models.CharField(
        max_length=150, unique=True, db_index=True,
        help_text="Must match the `crop` string ml_service's predict_crops() "
                  "returns (crop_name in "
                  "ml_service/data/crop_prediction_dataset_with_commodity_codes.csv). "
                  "Looked up case-insensitively."
    )
    crop_group = models.CharField(max_length=100, blank=True, default='')
    season = models.TextField(blank=True, default='')
    varieties = models.JSONField(
        default=list, blank=True,
        help_text='[{name, description?}]'
    )
    spacing = models.TextField(blank=True, default='')
    manuring_fertilizer = models.TextField(blank=True, default='')
    plant_protection = models.TextField(blank=True, default='')
    harvesting = models.TextField(blank=True, default='')
    expected_yield = models.CharField(max_length=255, blank=True, default='')
    sections = models.JSONField(
        default=list, blank=True,
        help_text='Ordered [{heading, body}] -- preserves book structure that '
                  "doesn't fit the fixed fields above (e.g. a tree crop's "
                  'named propagation/pruning/intercropping sub-sections).'
    )
    source_reference = models.CharField(
        max_length=255, blank=True,
        default='KAU Package of Practices Recommendations: Crops 2024 (16th ed.)'
    )
    source_page_range = models.CharField(
        max_length=50, blank=True, default='',
        help_text="PDF page range this entry was transcribed from, e.g. '15-57' -- for audit/spot-check."
    )
    is_active = models.BooleanField(
        default=False, db_index=True,
        help_text='Visible to FPOs only when True. Defaults False so a newly '
                  'transcribed entry can be cross-checked against the source '
                  'PDF before publishing.'
    )

    class Meta:
        verbose_name = 'Crop Package of Practices'
        verbose_name_plural = 'Crop Packages of Practices'
        ordering = ['crop_name']
        constraints = [
            models.UniqueConstraint(Lower('crop_name'), name='croppop_crop_name_ci_unique'),
        ]

    def __str__(self):
        return self.crop_name


class CropZoneProfile(BaseModel):
    """
    The ML service's live crop-eligibility knowledge base -- NOT the same data
    as CropPackageOfPractices above. This drives ml_service's predict_crops():
    which crops are even CANDIDATES for a zone, and the documented temperature/
    pH/season text shown in a recommendation's reasoning.
    """
    class KauZone(models.TextChoices):
        COASTAL_PLAIN = 'Coastal Plain', 'Coastal Plain'
        MIDLAND_LATERITES = 'Midland Laterites', 'Midland Laterites'
        FOOTHILLS = 'Foothills', 'Foothills'
        HIGH_HILLS = 'High Hills', 'High Hills'
        PALAKKAD_PLAIN = 'Palakkad Plain', 'Palakkad Plain'
        GENERAL = 'General (all zones)', 'General (all zones)'

    crop_name = models.CharField(
        max_length=150, db_index=True,
        help_text="Should match the crop_name used elsewhere (CropPackageOfPractices, "
                  "ml_service's commodity crosswalk) so a crop's data lines up across systems."
    )
    crop_group = models.CharField(max_length=100, blank=True, default='')
    kau_zone = models.CharField(
        max_length=30, choices=KauZone.choices,
        help_text="The KAU book's own physiographic zone this profile documents -- "
                  "expanded into 1-5 service zones at export time via a fixed crosswalk."
    )
    temp_lo = models.FloatField(help_text="Documented minimum temperature (°C) this crop tolerates.")
    temp_hi = models.FloatField(help_text="Documented maximum temperature (°C) this crop tolerates.")
    ph_lo = models.FloatField(help_text="Documented minimum soil pH this crop tolerates.")
    ph_hi = models.FloatField(help_text="Documented maximum soil pH this crop tolerates.")
    seasons_text = models.TextField(
        blank=True, default='',
        help_text="Free-text season/planting-window description shown in a recommendation's reasoning."
    )
    temp_is_real = models.BooleanField(
        default=True,
        help_text="False if temp_lo/hi is a zone-default fallback rather than the book's own stated range."
    )
    ph_is_real = models.BooleanField(
        default=True,
        help_text="False if ph_lo/hi is a crop-group-median fallback rather than the book's own stated range."
    )
    is_active = models.BooleanField(
        default=False, db_index=True,
        help_text="Only active rows are exported to ml_service. Defaults False so a new/edited entry "
                  "can be reviewed before it affects live recommendations."
    )

    class Meta:
        verbose_name = 'Crop Zone Profile'
        verbose_name_plural = 'Crop Zone Profiles'
        ordering = ['crop_name', 'kau_zone']
        constraints = [
            models.UniqueConstraint(Lower('crop_name'), 'kau_zone', name='cropzoneprofile_crop_zone_ci_unique'),
        ]

    def __str__(self):
        return f"{self.crop_name} ({self.kau_zone})"