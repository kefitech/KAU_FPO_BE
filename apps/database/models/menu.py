"""
MenuItem Model
==============

Stores sidebar navigation menu items.
Each item is assigned to one or more Django Groups (roles).
build_menu() in apps/accounts/menu.py filters by user's groups
and translates labels via TranslationService.

Admin manages items via /api/admin/menu/ — no code deploy needed
to add/remove/reorder menu items or change role access.
"""

from django.contrib.auth.models import Group
from django.db import models

from apps.core.models.base import TimeStampedModel


class MenuItem(TimeStampedModel):

    label_key = models.CharField(
        max_length=100,
        help_text="Translation key from the 'menu' category — e.g. 'menu.notifications'"
    )

    path = models.CharField(
        max_length=200,
        help_text="Frontend route — e.g. '/admin/notifications'"
    )

    icon = models.CharField(
        max_length=50,
        blank=True,
        help_text="Icon name for the frontend — e.g. 'bell', 'building', 'globe'"
    )

    roles = models.ManyToManyField(
        Group,
        blank=True,
        related_name='menu_items',
        help_text="Roles (Django Groups) that can see this menu item"
    )

    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='children',
        help_text="Parent item — null means top-level"
    )

    order = models.PositiveIntegerField(
        default=0,
        help_text="Sort order within the same level (lower = first)"
    )

    is_active = models.BooleanField(
        default=True,
        db_index=True,
    )

    class Meta:
        db_table = 'menu_items'
        ordering = ['order', 'label_key']
        verbose_name = 'Menu Item'
        verbose_name_plural = 'Menu Items'

    def __str__(self):
        return f"{self.label_key} ({self.path})"
