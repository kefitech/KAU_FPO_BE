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
Status Service for KAU-FPO Platform
===================================

Service for managing status transitions and history.

Features:
- Validate status transitions
- Log status changes to StatusHistory
- Get status history for objects

Usage:
    from apps.core.services.status import StatusService

    StatusService.change_status(
        instance=fpo,
        new_status='approved',
        user=admin_user,
        remarks='Verified all documents'
    )

Author:
    Athul Gopan
Created On:
    21-04-2026
"""

from typing import List, Optional, Dict, Any
from django.contrib.contenttypes.models import ContentType

from apps.core.models.generic import StatusHistory
from apps.core.utils.helpers import get_client_ip, get_user_agent
from apps.core.exceptions import InvalidStateTransitionError


class StatusService:
    """
    Service for status management.

    Works with any model that has a 'status' field.
    """

    @classmethod
    def change_status(
        cls,
        instance,
        new_status: str,
        user=None,
        remarks: str = '',
        request=None,
        validate: bool = True,
        transitions: Dict[str, List[str]] = None
    ) -> StatusHistory:
        """
        Change status of an instance with history logging.

        Args:
            instance: Model instance with 'status' field
            new_status: Target status
            user: User making the change
            remarks: Optional remarks
            request: HTTP request (for context)
            validate: Whether to validate transition
            transitions: Custom transitions dict (overrides model's)

        Returns:
            Created StatusHistory instance

        Raises:
            InvalidStateTransitionError: If transition is not valid
        """
        old_status = getattr(instance, 'status', None)

        # Validate transition if requested
        if validate:
            if not cls.can_transition(instance, new_status, transitions):
                raise InvalidStateTransitionError(
                    from_status=old_status or 'None',
                    to_status=new_status
                )

        # Update instance status
        instance.status = new_status
        instance.save(update_fields=['status', 'updated_at'])

        # Create history entry
        return cls._create_history(
            instance=instance,
            from_status=old_status,
            to_status=new_status,
            user=user,
            remarks=remarks,
            request=request
        )

    @classmethod
    def can_transition(
        cls,
        instance,
        new_status: str,
        transitions: Dict[str, List[str]] = None
    ) -> bool:
        """
        Check if status transition is valid.

        Args:
            instance: Model instance
            new_status: Target status
            transitions: Custom transitions dict

        Returns:
            True if transition is valid
        """
        current_status = getattr(instance, 'status', None)

        # If no transitions defined, allow all
        if transitions is None:
            # Try to get from model method
            if hasattr(instance, 'can_transition_to'):
                return instance.can_transition_to(new_status)
            # Try to get from model class
            if hasattr(instance.__class__, 'STATUS_TRANSITIONS'):
                transitions = instance.__class__.STATUS_TRANSITIONS
            else:
                return True  # Allow all if no rules defined

        allowed = transitions.get(current_status, [])
        return new_status in allowed

    @classmethod
    def get_valid_transitions(
        cls,
        instance,
        transitions: Dict[str, List[str]] = None
    ) -> List[str]:
        """
        Get list of valid next statuses.

        Args:
            instance: Model instance
            transitions: Custom transitions dict

        Returns:
            List of valid status values
        """
        current_status = getattr(instance, 'status', None)

        if transitions is None:
            if hasattr(instance.__class__, 'STATUS_TRANSITIONS'):
                transitions = instance.__class__.STATUS_TRANSITIONS
            else:
                return []

        return transitions.get(current_status, [])

    @classmethod
    def get_history(cls, instance, limit: int = None) -> List[StatusHistory]:
        """
        Get status history for an instance.

        Args:
            instance: Model instance
            limit: Maximum entries to return

        Returns:
            QuerySet of StatusHistory entries
        """
        content_type = ContentType.objects.get_for_model(instance)
        qs = StatusHistory.objects.filter(
            content_type=content_type,
            object_id=instance.pk
        ).order_by('-created_at')

        if limit:
            qs = qs[:limit]

        return list(qs)

    @classmethod
    def get_latest_status_change(cls, instance) -> Optional[StatusHistory]:
        """
        Get the most recent status change.

        Args:
            instance: Model instance

        Returns:
            StatusHistory entry or None
        """
        history = cls.get_history(instance, limit=1)
        return history[0] if history else None

    @classmethod
    def get_status_duration(cls, instance, status: str) -> Optional[int]:
        """
        Get how long instance was in a specific status (in seconds).

        Args:
            instance: Model instance
            status: Status to check

        Returns:
            Duration in seconds, or None if never in that status
        """
        from django.utils import timezone

        history = cls.get_history(instance)
        if not history:
            return None

        total_seconds = 0
        in_status = False
        start_time = None

        # Process in reverse chronological order
        for entry in reversed(history):
            if entry.to_status == status:
                in_status = True
                start_time = entry.created_at
            elif in_status and entry.from_status == status:
                if start_time:
                    total_seconds += (entry.created_at - start_time).total_seconds()
                in_status = False

        # If currently in the status
        current_status = getattr(instance, 'status', None)
        if current_status == status and start_time:
            total_seconds += (timezone.now() - start_time).total_seconds()

        return int(total_seconds) if total_seconds > 0 else None

    @classmethod
    def _create_history(
        cls,
        instance,
        from_status: str,
        to_status: str,
        user=None,
        remarks: str = '',
        request=None
    ) -> StatusHistory:
        """Create status history entry."""
        content_type = ContentType.objects.get_for_model(instance)

        ip_address = None
        user_agent = ''

        if request:
            ip_address = get_client_ip(request)
            user_agent = get_user_agent(request)[:500]

        return StatusHistory.objects.create(
            content_type=content_type,
            object_id=instance.pk,
            from_status=from_status,
            to_status=to_status,
            changed_by=user,
            remarks=remarks,
            ip_address=ip_address,
            user_agent=user_agent
        )

    @classmethod
    def bulk_change_status(
        cls,
        instances: list,
        new_status: str,
        user=None,
        remarks: str = '',
        request=None,
        validate: bool = True,
        transitions: Dict[str, List[str]] = None
    ) -> List[StatusHistory]:
        """
        Change status for multiple instances.

        Args:
            instances: List of model instances
            new_status: Target status for all
            user: User making the change
            remarks: Optional remarks
            request: HTTP request
            validate: Whether to validate transitions
            transitions: Custom transitions dict

        Returns:
            List of created StatusHistory entries
        """
        histories = []

        for instance in instances:
            try:
                history = cls.change_status(
                    instance=instance,
                    new_status=new_status,
                    user=user,
                    remarks=remarks,
                    request=request,
                    validate=validate,
                    transitions=transitions
                )
                histories.append(history)
            except InvalidStateTransitionError:
                # Skip instances that can't transition
                continue

        return histories
