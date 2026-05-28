"""
AdminTwoFactor model — stores TOTP secret and backup codes per admin user.
Only created for super_admin and sub_admin users.
"""

import secrets
from django.db import models
from django.contrib.auth.models import User
from apps.core.models.base import TimeStampedModel


class AdminTwoFactor(TimeStampedModel):
    user       = models.OneToOneField(User, on_delete=models.CASCADE, related_name='two_factor')
    secret     = models.CharField(max_length=64)
    is_enabled = models.BooleanField(default=False)
    backup_codes = models.JSONField(default=list)

    class Meta:
        db_table = 'admin_two_factor'
        verbose_name = 'Admin Two-Factor Auth'

    def generate_backup_codes(self):
        """Generate 8 one-time backup codes and store them."""
        codes = [secrets.token_hex(5).upper() for _ in range(8)]
        self.backup_codes = codes
        return codes

    def use_backup_code(self, code):
        """Consume a backup code. Returns True if valid."""
        code = code.upper().strip()
        if code in self.backup_codes:
            self.backup_codes = [c for c in self.backup_codes if c != code]
            self.save(update_fields=['backup_codes'])
            return True
        return False

    def __str__(self):
        return f"2FA({self.user.email}, enabled={self.is_enabled})"
