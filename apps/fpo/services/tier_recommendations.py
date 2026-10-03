"""
Tier upgrade recommendations — rule-based (no AI).

After an FPO submits a tier assessment we walk every active TierUpgradeTip
tied to the FPO's target tier and evaluate its trigger against the FPO's
answers. Matching tips are returned sorted by priority.

The target tier defaults to one tier up from the current tier (e.g. B → A).
Tier A FPOs get their own "maintain-A" tips.

No LLM call — KAU Admin edits the wording in `TierUpgradeTip`.
"""

from decimal import Decimal

from apps.database.models.fpo import (
    FPOAssessment,
    TierUpgradeTip,
    TierChoice,
)


# Which tier is one step above the given tier?
_NEXT_TIER = {'D': 'C', 'C': 'B', 'B': 'A', 'A': 'A'}

# Numeric rank for "better than" comparisons on the tier ladder.
# A is best (3), D is worst (0). Higher number = better tier.
_TIER_RANK = {'D': 0, 'C': 1, 'B': 2, 'A': 3}


def _next_tier_for(current_tier: str) -> str:
    return _NEXT_TIER.get(current_tier, 'A')


def _target_tiers_for(current_tier: str) -> list[str]:
    """
    Which `target_tier` values on TierUpgradeTip rows apply to an FPO
    sitting at `current_tier`? Returns every tier strictly above the
    FPO's current rank, so a Tier D FPO sees tips targeting C, B, and
    A (anything that lifts them). Tier A FPOs see the Tier A
    'maintain-rank' tips.
    """
    if not current_tier:
        # Unknown tier — fall back to showing the A-tier maintain tips.
        return ['A']
    current_rank = _TIER_RANK.get(current_tier, 0)
    if current_tier == 'A':
        return ['A']
    return sorted(
        [tier for tier, rank in _TIER_RANK.items() if rank > current_rank],
        key=_TIER_RANK.get,
    )  # closest-tier first (e.g. ['C', 'B', 'A'] for a Tier D FPO)


def _get_answer_value(answer_json):
    """AssessmentAnswer.answer is stored as JSON — could be a scalar or {'value': X}."""
    if isinstance(answer_json, dict):
        return answer_json.get('value', answer_json)
    return answer_json


def _tip_matches(tip: TierUpgradeTip, answer_obj, question) -> bool:
    """Return True if the tip's trigger fires for this FPO's answer."""
    trigger    = tip.trigger_type
    trig_val   = tip.trigger_value or {}
    answered   = answer_obj is not None
    raw_answer = _get_answer_value(answer_obj.answer) if answered else None
    score      = float(answer_obj.score) if answered else 0.0
    max_score  = float(question.answer_config.get('max_score', 0) or 0) if question else 0

    if trigger == TierUpgradeTip.Trigger.ALWAYS:
        return True

    if trigger == TierUpgradeTip.Trigger.UNANSWERED:
        return not answered or raw_answer in (None, '', [])

    if not answered:
        # All remaining triggers require an answer to evaluate.
        return False

    if trigger == TierUpgradeTip.Trigger.SCORE_BELOW_MAX:
        # Fire when this question didn't get full marks. Fall back to
        # question.answer_config['max_score'] if not set on the tip.
        cap = float(trig_val.get('max_score', max_score) or max_score)
        return cap > 0 and score < cap

    if trigger == TierUpgradeTip.Trigger.BOOLEAN_NO:
        return str(raw_answer).lower() in ('no', 'false', '0')

    if trigger == TierUpgradeTip.Trigger.VALUE_BELOW:
        threshold = trig_val.get('threshold')
        try:
            return threshold is not None and float(raw_answer) < float(threshold)
        except (TypeError, ValueError):
            return False

    if trigger == TierUpgradeTip.Trigger.VALUE_ABOVE:
        threshold = trig_val.get('threshold')
        try:
            return threshold is not None and float(raw_answer) > float(threshold)
        except (TypeError, ValueError):
            return False

    if trigger == TierUpgradeTip.Trigger.ANSWER_EQUALS:
        return str(raw_answer) == str(trig_val.get('value', ''))

    if trigger == TierUpgradeTip.Trigger.ANSWER_NOT_IN:
        allowed = trig_val.get('values') or []
        if isinstance(raw_answer, list):
            return not any(v in allowed for v in raw_answer)
        return raw_answer not in allowed

    return False


def get_recommendations(
    assessment: FPOAssessment,
    language: str = 'en',
    limit: int = 5,
) -> dict:
    """
    Build the upgrade recommendation payload for a submitted assessment.

    Returns:
        {
          'current_tier': 'B',
          'next_tier':    'A',
          'score':        68.0,
          'max_score':    100,
          'recommendations': [
            { 'question_no': 6, 'criterion_code': '...', 'tip': '...', 'priority': 1 },
            ...
          ],
        }
    """
    current_tier = assessment.tier_assigned or ''
    target_tier  = _next_tier_for(current_tier) if current_tier else 'A'
    # Admins seed tips keyed to WHICH higher tier the tip helps reach
    # (target_tier). For a Tier D FPO we need to show tips targeting any
    # higher tier — otherwise the panel is empty whenever KAU hasn't
    # seeded a tip for the exact next step (the common case). See
    # _target_tiers_for() for the full ladder logic.
    eligible_tiers = _target_tiers_for(current_tier)

    # All answers keyed by question — for O(1) lookup during trigger eval.
    answers_by_q = {
        a.question_id: a
        for a in assessment.answers.select_related('question__criterion').all()
    }

    tips = (
        TierUpgradeTip.objects
        .select_related('question', 'criterion')
        .filter(is_active=True, target_tier__in=eligible_tiers)
        .order_by('priority', 'id')
    )

    matches = []
    for tip in tips:
        # Locate the answer this tip cares about.
        answer_obj = None
        question   = None
        if tip.question_id:
            answer_obj = answers_by_q.get(tip.question_id)
            question   = tip.question
        elif tip.criterion_id:
            # Pick the lowest-scoring answer under this criterion — that's the
            # gap the tip wants to fix. If any answer under the criterion is
            # unanswered, prefer that one.
            crit_answers = [
                a for a in answers_by_q.values()
                if a.question.criterion_id == tip.criterion_id
            ]
            if crit_answers:
                answer_obj = min(crit_answers, key=lambda a: float(a.score or 0))
                question   = answer_obj.question

        if _tip_matches(tip, answer_obj, question):
            tip_text = tip.tip_ml if (language == 'ml' and tip.tip_ml) else tip.tip_en
            matches.append({
                'question_no':    question.question_no if question else None,
                'criterion_code': (question.criterion.code if question else
                                   (tip.criterion.code if tip.criterion_id else None)),
                'tip':            tip_text,
                'priority':       tip.priority,
                'target_tier':    tip.target_tier,
            })
            if len(matches) >= limit:
                break

    return {
        'current_tier':    current_tier,
        'next_tier':       target_tier,
        'score':           float(assessment.total_score or 0),
        'max_score':       100,
        'financial_year':  assessment.financial_year,
        'recommendations': matches,
    }
