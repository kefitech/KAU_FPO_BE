"""
Own-data context for the chatbot (2026-10-09, approved by Athul).

Testers asked the bot "what was MY tier in 2025-26?", "how many DPRs do
I have?", "why was MY appointment declined?" — unanswerable because the
bot only knew KB text. For a logged-in FPO user asking a PERSONAL
question, this builds a short private summary of their OWN records that
the Gemini prompt may use.

Privacy rules:
  * Only rows belonging to the requesting user's own FPO are read.
  * The block is built per-request and injected only when the question
    looks personal — and the message API SKIPS the answer cache for
    those turns, so a personal answer can never be replayed to anyone
    else.
  * Nothing here is written to the KB or stored anywhere.
"""

import logging
import re

logger = logging.getLogger(__name__)

# "my / mine / I have / do I ..." style questions.
PERSONAL_RE = re.compile(
    r'\b(my|mine|me)\b|\b(do|have|did|am|was|can|how many|what)\b[^.?!]{0,40}\bi\b',
    re.IGNORECASE,
)


def is_personal_question(text: str) -> bool:
    return bool(PERSONAL_RE.search(text or ''))


def _get_fpo(user):
    fpo = getattr(user, 'fpo', None)
    if fpo:
        return fpo
    from apps.database.models.fpo import FPOUserMembership
    m = (FPOUserMembership.objects
         .filter(user=user, is_deleted=False)
         .select_related('fpo').first())
    return m.fpo if m else None


def build_user_context(user) -> str:
    """Return the private own-data block, or '' when not applicable."""
    if not user or not getattr(user, 'is_authenticated', False):
        return ''
    try:
        fpo = _get_fpo(user)
        if fpo is None:
            return ''

        lines = [
            f"FPO: {fpo.name} — status {fpo.status}, "
            f"tier {fpo.tier or 'not yet assessed'}, "
            f"application ID {fpo.application_id or 'pending'}.",
        ]

        # Tier history (last 3 financial years)
        try:
            hist = list(fpo.tier_history.order_by('-created_at')[:3])
            if hist:
                lines.append('Tier history: ' + '; '.join(
                    f'{h.financial_year}: Tier {h.tier}' for h in hist))
        except Exception:  # noqa: BLE001
            pass

        # DPR projects (up to 6)
        try:
            from apps.database.models import DPRProject
            projs = list(DPRProject.objects.filter(
                fpo=fpo, is_deleted=False).order_by('-updated_at')[:6])
            if projs:
                lines.append(
                    f'DPR projects ({len(projs)} shown): ' + '; '.join(
                        f'"{p.title or "untitled"}" — {p.status}' for p in projs))
        except Exception:  # noqa: BLE001
            pass

        # Expert bookings (last 4, any status — includes decline reasons)
        try:
            bookings = list(fpo.expert_bookings
                            .select_related('expert')
                            .order_by('-requested_date')[:4])
            if bookings:
                blines = []
                for b in bookings:
                    item = (f'{b.expert.name_en} on {b.requested_date:%d %b %Y} '
                            f'{b.requested_time} — {b.status}')
                    reason = (b.cancellation_reason or '').strip()
                    if reason and b.status in ('rejected', 'cancelled'):
                        item += f' (reason: {reason[:120]})'
                    blines.append(item)
                lines.append('Expert appointments: ' + '; '.join(blines))
        except Exception:  # noqa: BLE001
            pass

        # In-app notifications (unread count + latest 3 titles)
        try:
            from apps.database.models import InAppNotification
            qs = InAppNotification.objects.filter(user=user)
            unread = qs.filter(is_read=False).count()
            latest = list(qs.order_by('-created_at')[:3])
            if latest:
                lines.append(
                    f'Notifications: {unread} unread; latest: ' + '; '.join(
                        f'"{n.title}"' for n in latest))
        except Exception:  # noqa: BLE001
            pass

        block = '\n'.join(lines)
        return block[:1500]
    except Exception:  # noqa: BLE001 — own-data must never break chat
        logger.warning('user context build failed', exc_info=True)
        return ''
