"""
Site Content CMS Models
========================
SiteBlock    — editable text blocks (hero, about, how-to-register)
Announcement — news & announcements
FAQ          — frequently asked questions
QuickLink    — logo + URL links shown on landing page
NewsSource   — newspaper/magazine logo links grouped by category

All text fields use JSONField: {"en": "...", "ml": "..."}
Admin edits via PATCH with the full language map.
Public API returns single value based on X-Language header.
"""

import os
import uuid

from django.db import models

from apps.core.models.base import BaseModel


# ─────────────────────────────────────────────────────────────────────────────
# Upload path helpers
# ─────────────────────────────────────────────────────────────────────────────

def _quick_link_logo_path(instance, filename):
    ext = os.path.splitext(filename)[1]
    return f'cms/quick-links/{uuid.uuid4()}{ext}'


def _news_source_logo_path(instance, filename):
    ext = os.path.splitext(filename)[1]
    return f'cms/news-sources/{uuid.uuid4()}{ext}'


# ─────────────────────────────────────────────────────────────────────────────
# Models
# ─────────────────────────────────────────────────────────────────────────────

class SiteBlock(BaseModel):
    block_key = models.CharField(max_length=100, unique=True)
    content   = models.JSONField(default=dict, help_text='{"en": "...", "ml": "..."}')
    is_active = models.BooleanField(default=True)

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


class Announcement(BaseModel):
    title          = models.JSONField(default=dict, help_text='{"en": "...", "ml": "..."}')
    body           = models.JSONField(default=dict, help_text='{"en": "...", "ml": "..."}')
    category       = models.CharField(max_length=20, choices=AnnouncementCategory.choices,
                                      default=AnnouncementCategory.ANNOUNCEMENT)
    published_date = models.DateField(null=True, blank=True)
    is_active      = models.BooleanField(default=True)
    order          = models.PositiveSmallIntegerField(default=0)

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
    FPO_GENERAL    = 'fpo_general',    'FPO General'
    SCHEMES        = 'schemes',        'Schemes & Financial Support'
    PLATFORM_USAGE = 'platform_usage', 'Platform Usage'


class FAQ(BaseModel):
    question  = models.JSONField(default=dict, help_text='{"en": "...", "ml": "..."}')
    answer    = models.JSONField(default=dict, help_text='{"en": "...", "ml": "..."}')
    category  = models.CharField(max_length=30, choices=FAQCategory.choices)
    order     = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

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


class QuickLink(BaseModel):
    name      = models.CharField(max_length=200, help_text='Admin label — not shown publicly')
    url       = models.URLField(max_length=500)
    logo      = models.ImageField(upload_to=_quick_link_logo_path, null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return self.name


def _partner_logo_path(instance, filename):
    ext = os.path.splitext(filename)[1]
    return f'cms/partners/{uuid.uuid4()}{ext}'


class Partner(BaseModel):
    name      = models.CharField(max_length=200)
    url       = models.URLField(max_length=500, blank=True)
    logo      = models.ImageField(upload_to=_partner_logo_path, null=True, blank=True)
    order     = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['order', 'id']

    def __str__(self):
        return self.name


class NewsSourceCategory(models.TextChoices):
    NEWSPAPER = 'newspaper', 'Newspaper'
    MAGAZINE  = 'magazine',  'Magazine'


class NewsSource(BaseModel):
    name      = models.CharField(max_length=200, help_text='Admin label — e.g. "The Hindu"')
    url       = models.URLField(max_length=500)
    logo      = models.ImageField(upload_to=_news_source_logo_path, null=True, blank=True)
    category  = models.CharField(max_length=20, choices=NewsSourceCategory.choices,
                                 default=NewsSourceCategory.NEWSPAPER)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['category', 'name']

    def __str__(self):
        return self.name


def _gallery_photo_path(instance, filename):
    ext = os.path.splitext(filename)[1]
    return f'cms/gallery/{uuid.uuid4()}{ext}'


def _document_library_path(instance, filename):
    ext = os.path.splitext(filename)[1]
    return f'cms/documents/{uuid.uuid4()}{ext}'


def _team_member_photo_path(instance, filename):
    ext = os.path.splitext(filename)[1]
    return f'cms/team/{uuid.uuid4()}{ext}'


class TeamMember(BaseModel):
    name        = models.CharField(max_length=200)
    designation = models.CharField(max_length=300, help_text='Full title — e.g. "Hon. Chief Minister"')
    photo       = models.ImageField(upload_to=_team_member_photo_path, null=True, blank=True)
    order       = models.PositiveSmallIntegerField(default=0)
    is_active   = models.BooleanField(default=True)

    class Meta:
        ordering = ['order', 'name']

    def __str__(self):
        return self.name


class GalleryAlbum(BaseModel):
    title     = models.CharField(max_length=300)
    order     = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['order', 'id']

    def cover_photo(self):
        return self.photos.filter(is_deleted=False, is_active=True).order_by('order', 'id').first()

    def photo_count(self):
        return self.photos.filter(is_deleted=False).count()

    def __str__(self):
        return self.title


class GalleryPhoto(BaseModel):
    album   = models.ForeignKey(GalleryAlbum, on_delete=models.CASCADE, related_name='photos', null=True, blank=True)
    photo   = models.ImageField(upload_to=_gallery_photo_path)
    caption = models.JSONField(default=dict, blank=True, help_text='{"en": "...", "ml": "..."}')
    order   = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['order', 'id']

    def get_caption(self, lang='en'):
        if isinstance(self.caption, dict):
            return self.caption.get(lang) or self.caption.get('en', '')
        return ''

    def __str__(self):
        return self.get_caption() or f'Photo {self.id}'


class VisitorCount(models.Model):
    count      = models.PositiveBigIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Visitor Counter'

    @classmethod
    def increment(cls):
        cls.objects.get_or_create(pk=1)
        cls.objects.filter(pk=1).update(count=models.F('count') + 1)

    @classmethod
    def get_count(cls):
        obj = cls.objects.filter(pk=1).first()
        return obj.count if obj else 0


class FeedbackStatus(models.TextChoices):
    UNREAD   = 'unread',   'Unread'
    READ     = 'read',     'Read'
    RESOLVED = 'resolved', 'Resolved'


class Feedback(models.Model):
    name       = models.CharField(max_length=200)
    email      = models.EmailField()
    phone      = models.CharField(max_length=20, blank=True, default='')
    subject    = models.CharField(max_length=300)
    message    = models.TextField()
    status     = models.CharField(max_length=20, choices=FeedbackStatus.choices,
                                  default=FeedbackStatus.UNREAD)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.name} — {self.subject}'


class DocumentLibrary(BaseModel):
    title        = models.JSONField(default=dict, help_text='{"en": "...", "ml": "..."}')
    file         = models.FileField(upload_to=_document_library_path)
    is_view_only = models.BooleanField(default=False, help_text='True = view only, no download button')
    order        = models.PositiveSmallIntegerField(default=0)
    is_active    = models.BooleanField(default=True)

    class Meta:
        ordering = ['order']

    def get_title(self, lang='en'):
        if isinstance(self.title, dict):
            return self.title.get(lang) or self.title.get('en', '')
        return ''

    def __str__(self):
        return self.get_title()
