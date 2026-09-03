"""
AI Crop Recommendations Models — P2-06
Django acts as proxy to FastAPI ML service on port 8001 (internal only).
"""
from django.db import models
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