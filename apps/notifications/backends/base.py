"""
Base Notification Backend
=========================

All channel backends inherit from BaseNotificationBackend.
Each backend must implement the `send()` method.

Adding a new channel:
    1. Create apps/notifications/backends/whatsapp.py
    2. Inherit BaseNotificationBackend
    3. Implement send()
    4. Register in dispatcher (services.py)
"""

from abc import ABC, abstractmethod


class BaseNotificationBackend(ABC):
    """Abstract base for all notification channel backends."""

    def __init__(self, settings: dict):
        """
        Args:
            settings: Decrypted config dict from NotificationChannelSettings.config
        """
        self.settings = settings

    @abstractmethod
    def send(self, recipient: str, subject: str, body: str, log) -> bool:
        """
        Deliver the notification.

        Args:
            recipient : email address / phone number / device token
            subject   : rendered subject line (empty string for SMS/in-app)
            body      : rendered body content
            log       : NotificationLog instance — update status here

        Returns:
            True on success, False on failure.
        """
        raise NotImplementedError
