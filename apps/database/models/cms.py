"""
Site Content CMS Models
========================
SiteBlock   — editable text blocks (hero, about, how-to-register)
Announcement — news & announcements
FAQ          — frequently asked questions

All text fields use JSONField: {"en": "...", "ml": "..."}
Admin edits via PATCH with the full language map.
Public API returns single value based on X-Language header.
"""

from django.db import models


class SiteBlock(models.Model):
    block_key   = models.CharField(max_length=100, unique=True)
    content     = models.JSONField(default=dict, help_text='{"en": "...", "ml": "..."}')
    is_active   = models.BooleanField(default=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['block_key']

    def __str__(self):
        return self.block_key

    def get_content(self, lang='en'):
        if isinstance(self.content, dict):
            return self.content.get(lang) or self.content.get('en', '')
        return ''


class AnnouncementCategory(models.TextChoices):
    ANNOUNCEMENT = 'announcement', 'Announcement'
    NEWS         = 'news',         'News'


class Announcement(models.Model):
    title          = models.JSONField(default=dict, help_text='{"en": "...", "ml": "..."}')
    body           = models.JSONField(default=dict, help_text='{"en": "...", "ml": "..."}')
    category       = models.CharField(max_length=20, choices=AnnouncementCategory.choices,
                                      default=AnnouncementCategory.ANNOUNCEMENT)
    published_date = models.DateField(null=True, blank=True)
    is_active      = models.BooleanField(default=True)
    order          = models.PositiveSmallIntegerField(default=0)
    created_at     = models.DateTimeField(auto_now_add=True)
    updated_at     = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order', '-published_date']

    def get_title(self, lang='en'):
        if isinstance(self.title, dict):
            return self.title.get(lang) or self.title.get('en', '')
        return ''

    def get_body(self, lang='en'):
        if isinstance(self.body, dict):
            return self.body.get(lang) or self.body.get('en', '')
        return ''


class FAQCategory(models.TextChoices):
    FPO_GENERAL      = 'fpo_general',      'FPO General'
    SCHEMES          = 'schemes',           'Schemes & Financial Support'
    PLATFORM_USAGE   = 'platform_usage',    'Platform Usage'


class FAQ(models.Model):
    question   = models.JSONField(default=dict, help_text='{"en": "...", "ml": "..."}')
    answer     = models.JSONField(default=dict, help_text='{"en": "...", "ml": "..."}')
    category   = models.CharField(max_length=30, choices=FAQCategory.choices)
    order      = models.PositiveSmallIntegerField(default=0)
    is_active  = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['category', 'order']

    def get_question(self, lang='en'):
        if isinstance(self.question, dict):
            return self.question.get(lang) or self.question.get('en', '')
        return ''

    def get_answer(self, lang='en'):
        if isinstance(self.answer, dict):
            return self.answer.get(lang) or self.answer.get('en', '')
        return ''
