"""
█╗  ██╗ ███████╗███████╗██╗    ████████╗███████╗ ██████╗██╗  ██╗
██║ ██╔╝██╔════╝██╔════╝██║    ╚══██╔══╝██╔════╝██╔════╝██║  ██║
█████╔╝ █████╗  █████╗  ██║       ██║   █████╗  ██║     ███████║
██╔═██╗ ██╔══╝  ██╔══╝  ██║       ██║   ██╔══╝  ██║     ██╔══██║
██║  ██╗███████╗██║     ██║       ██║   ███████╗╚██████╗██║  ██║
╚═╝  ╚═╝╚══════╝╚═╝     ╚═╝       ╚═╝   ╚══════╝ ╚═════╝╚═╝  ╚═╝

                KEFI TECH

 █████╗ ████████╗██╗  ██╗██╗   ██╗██╗     
██╔══██╗╚══██╔══╝██║  ██║██║   ██║██║     
███████║   ██║   ███████║██║   ██║██║     
██╔══██║   ██║   ██╔══██║██║   ██║██║     
██║  ██║   ██║   ██║  ██║╚██████╔╝███████╗
╚═╝  ╚═╝   ╚═╝   ╚═╝  ╚═╝ ╚═════╝ ╚══════╝

        ATHUL GOPAN

-----------------------------------------------------
Model Mixins for KAU-FPO Platform
=================================

Reusable mixins that can be added to any model:
- TranslatableMixin: For bilingual content (English + Malayalam)
- StatusMixin: For models with status workflow and history tracking
- OrderedMixin: For models with display ordering
- SlugMixin: For models with URL-friendly slugs

Usage:
    from apps.core.models.mixins import StatusMixin

    class FPOApplication(BaseModel, StatusMixin):
        name = models.CharField(max_length=255)
        status = models.CharField(max_length=50)

Author:
    Athul Gopan
Created On:
    21-04-2026
"""

from django.db import models
from django.contrib.contenttypes.models import ContentType


class TranslatableMixin(models.Model):
    """
    Mixin for multilingual model fields.

    Convention: base field = English, {field}_{lang_code} = other languages.
    Example: name (English), name_ml (Malayalam), name_ta (Tamil if added later).

    For new multilingual data, prefer the Translation table over model columns.
    Use this mixin only for FPO-specific fields like FPO.name / FPO.name_ml
    that are user-entered content (not system labels).
    """

    class Meta:
        abstract = True

    def get_translated_field(self, field_name: str, language: str = 'en'):
        """
        Get field value in specified language.
        Looks for {field_name}_{language} column, falls back to base field (English).
        Works for any language code — not limited to 'ml'.
        """
        if language != 'en':
            lang_field = f"{field_name}_{language}"
            lang_value = getattr(self, lang_field, None)
            if lang_value:
                return lang_value
        return getattr(self, field_name, None)

    def get_all_translations(self, field_name: str) -> dict:
        """
        Get all available translations for a field as a dict.
        Returns only languages that have a corresponding column on the model.
        """
        from apps.database.models import Language
        result = {'en': getattr(self, field_name, None)}
        for lang in Language.objects.filter(is_active=True).exclude(code='en').values_list('code', flat=True):
            value = getattr(self, f"{field_name}_{lang}", None)
            if value is not None:
                result[lang] = value
        return result


class StatusMixin(models.Model):
    """
    Mixin for models with status workflow.

    Automatically logs status changes to StatusHistory table.
    Provides methods for status transitions with validation.

    Requires:
        - Model must have a 'status' field
        - Override can_transition_to() to define valid transitions

    Example:
        class FPOApplication(BaseModel, StatusMixin):
            status = models.CharField(max_length=50, default='draft')

            def can_transition_to(self, new_status):
                transitions = {
                    'draft': ['submitted'],
                    'submitted': ['under_review', 'rejected'],
                    'under_review': ['approved', 'rejected'],
                }
                return new_status in transitions.get(self.status, [])
    """

    class Meta:
        abstract = True

    def change_status(self, new_status, user=None, remarks='', request=None):
        """
        Change status with automatic history logging.

        Args:
            new_status: The new status value
            user: User making the change
            remarks: Optional remarks for the change
            request: HTTP request for IP/user-agent logging

        Returns:
            self (for method chaining)

        Raises:
            ValueError: If transition is not allowed
        """
        # Import here to avoid circular imports
        from apps.core.models.generic import StatusHistory

        old_status = getattr(self, 'status', None)

        # Validate transition
        if not self.can_transition_to(new_status):
            raise ValueError(
                f"Invalid status transition: {old_status} → {new_status}"
            )

        # Update status
        self.status = new_status
        self.save(update_fields=['status', 'updated_at'])

        # Extract request context
        ip_address = None
        user_agent = ''
        if request:
            ip_address = self._get_client_ip(request)
            user_agent = request.headers.get('User-Agent', '')[:500]

        # Log to StatusHistory
        StatusHistory.objects.create(
            content_type=ContentType.objects.get_for_model(self),
            object_id=self.pk,
            from_status=old_status,
            to_status=new_status,
            changed_by=user,
            remarks=remarks,
            ip_address=ip_address,
            user_agent=user_agent
        )

        return self

    def can_transition_to(self, new_status) -> bool:
        """
        Check if transition to new_status is allowed.

        Override in child class to define valid transitions.
        Default: Allow all transitions.

        Args:
            new_status: Target status

        Returns:
            True if transition is allowed, False otherwise
        """
        return True

    def get_status_history(self):
        """
        Get all status changes for this object.

        Returns:
            QuerySet of StatusHistory objects, ordered by most recent first
        """
        from apps.core.models.generic import StatusHistory

        content_type = ContentType.objects.get_for_model(self)
        return StatusHistory.objects.filter(
            content_type=content_type,
            object_id=self.pk
        ).order_by('-created_at')

    def get_current_status_entry(self):
        """
        Get the most recent status history entry.

        Returns:
            StatusHistory object or None
        """
        return self.get_status_history().first()

    @staticmethod
    def _get_client_ip(request):
        """Extract client IP from request headers."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR')


class OrderedMixin(models.Model):
    """
    Mixin for models with display ordering.

    Adds a display_order field for custom sorting.

    Example:
        class Category(OrderedMixin):
            name = models.CharField(max_length=100)

        # Categories will be ordered by display_order by default
    """

    display_order = models.PositiveIntegerField(
        default=0,
        db_index=True,
        help_text="Order for display purposes. Lower numbers appear first."
    )

    class Meta:
        abstract = True
        ordering = ['display_order']


class SlugMixin(models.Model):
    """
    Mixin for models with URL-friendly slugs.

    Adds a unique slug field for SEO-friendly URLs.

    Example:
        class BlogPost(SlugMixin):
            title = models.CharField(max_length=200)

        # Access via: /blog/my-post-slug/
    """

    slug = models.SlugField(
        max_length=255,
        unique=True,
        db_index=True,
        help_text="URL-friendly identifier"
    )

    class Meta:
        abstract = True


class ActiveMixin(models.Model):
    """
    Mixin for models with active/inactive status.

    Simple boolean flag for enabling/disabling records.

    Example:
        class Feature(ActiveMixin):
            name = models.CharField(max_length=100)

        # Only show active features
        Feature.objects.filter(is_active=True)
    """

    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Whether this record is active"
    )

    class Meta:
        abstract = True
