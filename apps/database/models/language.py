"""
Language and Translation Models for KAU-FPO Platform
====================================================

PostgreSQL + Redis Hybrid Architecture:
- PostgreSQL: Stores all translation data (admin-editable)
- Redis: Caches translations (24h TTL, <1ms lookups)
- Auto cache invalidation on admin updates

Allows KAU Admin to:
- Add new languages without developer involvement
- Manage all translations via admin panel
- Bulk import/export translations

Models:
- Language: Supported languages (en, ml, ta, hi, etc.)
- TranslationCategory: Organized categories (ui, validation, auth, etc.)
- Translation: All translatable UI strings and messages
- NotificationTemplate: Email/SMS templates in multiple languages

Author: Athul Gopan (Kefi Tech Solutions)
Created: 28-04-2026
SRS Reference: Section 3.1.7 (Multilingual Support)
"""

from django.db import models
from django.core.cache import cache
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from apps.core.models.base import TimeStampedModel


class Language(TimeStampedModel):
    """
    Supported languages in the platform.

    KAU Admin can add new languages via admin panel without developer involvement.

    Initial languages: English (en), Malayalam (ml)
    Can add: Tamil (ta), Hindi (hi), Kannada (kn), Telugu (te), etc.

    Cached in Redis for fast access.
    """

    code = models.CharField(
        max_length=10,
        unique=True,
        db_index=True,
        help_text="ISO 639-1 language code (e.g., 'en', 'ml', 'ta')"
    )

    name = models.CharField(
        max_length=50,
        help_text="Language name in English (e.g., 'English', 'Malayalam')"
    )

    native_name = models.CharField(
        max_length=50,
        help_text="Language name in native script (e.g., 'English', 'മലയാളം')"
    )

    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Only active languages are available for selection"
    )

    is_default = models.BooleanField(
        default=False,
        help_text="Default language for new users and fallback"
    )

    display_order = models.PositiveIntegerField(
        default=0,
        help_text="Order in language selector dropdown"
    )

    # RTL support for future (Arabic, Urdu, etc.)
    is_rtl = models.BooleanField(
        default=False,
        help_text="Right-to-left text direction"
    )

    # Locale settings for formatting (dates, numbers)
    locale = models.CharField(
        max_length=10,
        blank=True,
        help_text="Full locale code (e.g., 'en_US', 'ml_IN')"
    )

    class Meta:
        db_table = 'languages'
        ordering = ['display_order', 'name']
        verbose_name = 'Language'
        verbose_name_plural = 'Languages'

    def __str__(self):
        return f"{self.native_name} ({self.code})"

    def save(self, *args, **kwargs):
        """Ensure only one default language"""
        if self.is_default:
            # Remove default from other languages
            Language.objects.filter(is_default=True).exclude(pk=self.pk).update(is_default=False)

        super().save(*args, **kwargs)

        # Clear language cache
        self.clear_cache()

    def clear_cache(self):
        """Clear all language-related caches"""
        cache.delete('active_languages')
        cache.delete('default_language')
        cache.delete(f'language:{self.code}')

    @classmethod
    def get_default(cls):
        """Get default language (cached)"""
        cache_key = 'default_language'
        lang = cache.get(cache_key)

        if not lang:
            lang = cls.objects.filter(is_default=True).first()
            if not lang:
                lang = cls.objects.filter(code='en').first()
            if lang:
                cache.set(cache_key, lang, 60 * 60 * 24)  # 24 hours

        return lang

    @classmethod
    def get_active_languages(cls):
        """Get all active languages (cached for 24h)"""
        cache_key = 'active_languages'
        languages = cache.get(cache_key)

        if languages is None:
            languages = list(cls.objects.filter(is_active=True).values(
                'code', 'name', 'native_name', 'is_default', 'is_rtl', 'display_order'
            ))
            cache.set(cache_key, languages, 60 * 60 * 24)  # 24 hours

        return languages


class TranslationCategory(TimeStampedModel):
    """
    Categories for organizing translations.

    Makes translation management easier for admins.

    Categories:
    - ui: UI labels, buttons, navigation, form labels
    - validation: Form validation error messages
    - notification: Email/SMS notification messages
    - auth: Authentication and authorization messages
    - fpo: FPO-specific messages
    - error: System error messages
    - success: Success messages
    - info: Informational messages
    """

    code = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        help_text="Category code (e.g., 'ui', 'validation', 'auth')"
    )

    name = models.CharField(
        max_length=100,
        help_text="Category name for display"
    )

    description = models.TextField(
        blank=True,
        help_text="What this category contains"
    )

    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'translation_categories'
        ordering = ['display_order', 'name']
        verbose_name = 'Translation Category'
        verbose_name_plural = 'Translation Categories'

    def __str__(self):
        return f"{self.name} ({self.code})"


class Translation(TimeStampedModel):
    """
    All translatable strings in the platform.

    Stored in PostgreSQL, cached in Redis (24h TTL).

    Key naming convention: category.specific_key
    Examples:
    - auth.login_success
    - validation.required_field
    - ui.dashboard_title
    - notification.fpo_approved_email_subject
    - error.server_error

    Variable substitution using {{variable_name}} format:
    - "Welcome {{user_name}} to KAU-FPO Platform"
    - "Your application {{application_id}} has been approved"
    - "{{count}} FPOs registered in {{district}}"
    """

    category = models.ForeignKey(
        TranslationCategory,
        on_delete=models.PROTECT,
        related_name='translations',
        help_text="Category this translation belongs to"
    )

    key = models.CharField(
        max_length=255,
        db_index=True,
        help_text="Translation key (e.g., 'login_success', 'required_field')"
    )

    language = models.ForeignKey(
        Language,
        on_delete=models.CASCADE,
        related_name='translations'
    )

    value = models.TextField(
        help_text="Translated text. Use {{variable}} for dynamic content"
    )

    # Context for translators
    context = models.TextField(
        blank=True,
        help_text="Context/notes for translators (e.g., 'Shown on login page after successful authentication')"
    )

    # Variables used in this translation
    variables = models.JSONField(
        default=list,
        blank=True,
        help_text="List of variable names used (e.g., ['user_name', 'fpo_name'])"
    )

    # For translation review workflow
    is_verified = models.BooleanField(
        default=False,
        help_text="Has this translation been reviewed and approved by KAU?"
    )

    verified_by = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='verified_translations',
        help_text="Admin who verified this translation"
    )

    verified_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When was this translation verified?"
    )

    class Meta:
        db_table = 'translations'
        unique_together = [['category', 'key', 'language']]
        indexes = [
            models.Index(fields=['category', 'key', 'language']),
            models.Index(fields=['language', 'is_verified']),
        ]
        verbose_name = 'Translation'
        verbose_name_plural = 'Translations'

    def __str__(self):
        return f"{self.full_key} ({self.language.code})"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Auto-invalidate cache on save
        self.clear_cache()

    def clear_cache(self):
        """Clear cached translation (called automatically on save/delete)"""
        cache_key = f"trans:{self.language.code}:{self.full_key}"
        cache.delete(cache_key)

        # Also clear category cache (for bulk fetching)
        cache.delete(f"trans_cat:{self.language.code}:{self.category.code}")

    @property
    def full_key(self):
        """Get full translation key (category.key)"""
        return f"{self.category.code}.{self.key}"


class NotificationTemplateCode(TimeStampedModel):
    """
    Defines what a notification template is — code, channel, variables.

    This is the parent/definition table. One row per unique notification event
    per channel (e.g. fpo_approved/email, fpo_approved/sms are two separate definitions).

    NotificationTemplate holds the actual content per language and references this.

    Admin creates this first → then adds language versions via NotificationTemplate.
    Frontend shows a dropdown populated from this table.
    """

    class Channel(models.TextChoices):
        EMAIL    = 'email',    'Email'
        SMS      = 'sms',      'SMS'
        IN_APP   = 'in_app',   'In-App Notification'
        PUSH     = 'push',     'Push Notification'
        WHATSAPP = 'whatsapp', 'WhatsApp'

    code = models.CharField(
        max_length=50,
        help_text="Unique event code (e.g. 'fpo_approved', 'password_reset', 'otp_sent')"
    )

    name = models.CharField(
        max_length=100,
        help_text="Human-readable name shown in admin (e.g. 'FPO Application Approved')"
    )

    channel = models.CharField(
        max_length=10,
        choices=Channel.choices,
        help_text="Delivery channel for this definition"
    )

    variables = models.JSONField(
        default=list,
        blank=True,
        help_text="Variable names the template body expects (e.g. ['user_name', 'fpo_name'])"
    )

    description = models.TextField(
        blank=True,
        help_text="When this notification is triggered — for admin reference"
    )

    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Inactive definitions are hidden from the template creation dropdown"
    )

    class Meta:
        db_table = 'notification_template_codes'
        unique_together = [['code', 'channel']]
        ordering = ['channel', 'code']
        verbose_name = 'Notification Template Code'
        verbose_name_plural = 'Notification Template Codes'

    def __str__(self):
        return f"{self.code} ({self.get_channel_display()})"

    @property
    def missing_languages(self):
        """Returns language codes that don't have a template yet for this definition."""
        translated = set(self.templates.values_list('language__code', flat=True))
        all_active = set(lang['code'] for lang in Language.get_active_languages())
        return all_active - translated


class NotificationTemplate(TimeStampedModel):
    """
    Language-specific content for a notification template.

    One row per (template_code + language) combination.
    Admin selects the template_code from a dropdown (populated from NotificationTemplateCode),
    then selects the language and writes the subject/body.

    Variable substitution uses {{variable_name}} syntax — matches variables
    defined on the parent NotificationTemplateCode.

    Example:
        NotificationTemplateCode: code='fpo_approved', channel='email', variables=['user_name', 'fpo_name']
        NotificationTemplate (EN): subject="FPO Approved", body="Dear {{user_name}}, your FPO {{fpo_name}}..."
        NotificationTemplate (ML): subject="FPO അംഗീകരിച്ചു", body="{{user_name}}, {{fpo_name}} അംഗീകരിച്ചു..."
    """

    template_code = models.ForeignKey(
        NotificationTemplateCode,
        on_delete=models.CASCADE,
        related_name='templates',
        help_text="Select the notification event this content belongs to"
    )

    language = models.ForeignKey(
        Language,
        on_delete=models.CASCADE,
        related_name='notification_templates',
        help_text="Language this content is written in"
    )

    subject = models.CharField(
        max_length=255,
        blank=True,
        help_text="Email subject line (email channel only). Supports {{variables}}."
    )

    body = models.TextField(
        help_text="Template body. Use {{variable_name}} for dynamic content. HTML allowed for email."
    )

    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Only active templates are used when sending notifications"
    )

    # WhatsApp Business API — Meta requires pre-approved template names
    whatsapp_template_name = models.CharField(
        max_length=100,
        blank=True,
        help_text="Meta-approved WhatsApp template name (e.g. kau_fpo_password_reset). WhatsApp channel only."
    )
    whatsapp_template_language = models.CharField(
        max_length=10,
        blank=True,
        default='en',
        help_text="WhatsApp template language code (e.g. en, ml). Must match Meta-approved language."
    )

    class Meta:
        db_table = 'notification_templates'
        unique_together = [['template_code', 'language']]
        indexes = [
            models.Index(fields=['template_code', 'language', 'is_active']),
            models.Index(fields=['is_active']),
        ]
        verbose_name = 'Notification Template'
        verbose_name_plural = 'Notification Templates'

    def __str__(self):
        return f"{self.template_code.code} ({self.template_code.get_channel_display()}) - {self.language.code}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.clear_cache()

    def clear_cache(self):
        cache_key = f"notif_template:{self.template_code.channel}:{self.template_code.code}:{self.language.code}"
        cache.delete(cache_key)

    def render(self, context: dict) -> dict:
        """
        Render template with variable substitution.

        Returns dict with 'body' always present, 'subject' added for email channel.

        Example:
            template.render({'user_name': 'Rajan', 'fpo_name': 'Kerala FPO'})
            -> {'subject': 'FPO Approved', 'body': 'Dear Rajan, Kerala FPO is approved...'}
        """
        result = {'body': self.body}

        for key, value in context.items():
            placeholder = f"{{{{{key}}}}}"
            result['body'] = result['body'].replace(placeholder, str(value))

        if self.template_code.channel == NotificationTemplateCode.Channel.EMAIL and self.subject:
            result['subject'] = self.subject
            for key, value in context.items():
                placeholder = f"{{{{{key}}}}}"
                result['subject'] = result['subject'].replace(placeholder, str(value))

        if self.template_code.channel == NotificationTemplateCode.Channel.WHATSAPP:
            result['whatsapp_template_name']     = self.whatsapp_template_name
            result['whatsapp_template_language'] = self.whatsapp_template_language or 'en'

        return result


# ============================================================================
# SIGNALS - Auto Cache Invalidation
# ============================================================================

@receiver([post_save, post_delete], sender=Language)
def invalidate_language_cache(sender, instance, **kwargs):
    """Auto-invalidate language cache when language is added/updated/deleted"""
    instance.clear_cache()


@receiver([post_save, post_delete], sender=Translation)
def invalidate_translation_cache(sender, instance, **kwargs):
    instance.clear_cache()
    # If a ui category key is edited, bust the public bundle cache for that language
    if instance.category.code == 'ui':
        pattern = f'translations:public:{instance.language.code}:*'
        # Delete all public bundle cache keys for this language
        # (delete_pattern requires django-redis; fall back to deleting known keys)
        try:
            cache.delete_pattern(pattern)
        except AttributeError:
            # Standard Django cache — delete common known keys
            for screen in ['all', 'login', 'register', 'fpo_form', 'dashboard', 'nav', 'common']:
                cache.delete(f'translations:public:{instance.language.code}:{screen}')


@receiver([post_save, post_delete], sender=NotificationTemplate)
def invalidate_template_cache(sender, instance, **kwargs):
    instance.clear_cache()
