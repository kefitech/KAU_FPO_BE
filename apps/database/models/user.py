"""
User-related models — extends Django's built-in User with extra fields.
Phase II: add UserDevice here for push notification device tokens.
"""

from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.core.models.base import TimeStampedModel


class UserProfile(TimeStampedModel):
    user                 = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    phone                = models.CharField(max_length=15, blank=True, default='')
    preferred_language   = models.CharField(max_length=10, default='en')
    must_change_password = models.BooleanField(default=False)

    class Meta:
        db_table     = 'user_profile'
        verbose_name = 'User Profile'

    def __str__(self):
        return f"Profile({self.user.email})"


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Auto-create a UserProfile whenever a new User is created."""
    if created:
        UserProfile.objects.get_or_create(user=instance)
