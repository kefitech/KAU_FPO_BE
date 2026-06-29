"""
FPO Tier Assessment API
========================
GET   /api/fpo/me/tier-assessment/              — get current year assessment + all questions
POST  /api/fpo/me/tier-assessment/              — start new assessment for a financial year
PATCH /api/fpo/me/tier-assessment/{id}/         — save answers (auto-save, partial ok)
POST  /api/fpo/me/tier-assessment/{id}/submit/  — submit → auto-score → FPOTierHistory created
GET   /api/fpo/me/tier-assessment/history/      — all assessments across all years

Rules:
- Only APPROVED FPOs can take the assessment
- Only the primary user can fill and submit
- One assessment per FPO per financial year
- Editable until submitted (RCD confirmed)
- Previous year assessments are read-only
- Scoring is fully automated — FPO never sees raw formula
"""

from datetime import date
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.views import APIView

from apps.core.models.generic import AuditLog
from apps.core.permissions.rbac import IsFPOManager
from apps.core.services.audit import AuditService
from apps.core.utils.constants import FPOStatus
from apps.core.utils.responses import StandardResponse
from apps.database.models.fpo import (
    FPO, FPOAssessment, AssessmentAnswer, AssessmentUpload,
    TierDomain, TierCriterion, TierQuestion, FPOTierHistory,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _current_financial_year():
    today = date.today()
    if today.month >= 4:
        return f'{today.year}-{str(today.year + 1)[2:]}'
    return f'{today.year - 1}-{str(today.year)[2:]}'


def _get_primary_fpo(user):
    return FPO.objects.filter(primary_user=user, is_deleted=False).first()


def _prefill_answers(assessment, fpo):
    """
    Auto-save answers for questions whose data already exists in the FPO profile.
    Called once when a new assessment is created.
    """
    # Map question_no → value from FPO registration fields
    prefill_map = {
        1:  fpo.total_directors,       # Q1 — Total directors
        2:  fpo.women_directors,       # Q2 — Women directors
        7:  'yes' if fpo.ceo_available else 'no',         # Q7 — CEO available?
        8:  'yes' if fpo.accountant_available else 'no',  # Q8 — Accountant available?
        12: fpo.total_directors,       # Q12 — Total Board Members (same as Q1)
        15: fpo.total_members,         # Q15 — Total members
    }

    question_map = {
        q.question_no: q
        for q in TierQuestion.objects.filter(question_no__in=prefill_map.keys())
    }

    for qno, value in prefill_map.items():
        if value is None:
            continue
        question = question_map.get(qno)
        if not question:
            continue
        AssessmentAnswer.objects.get_or_create(
            assessment=assessment,
            question=question,
            defaults={'answer': value, 'score': 0},
        )


# ─────────────────────────────────────────────────────────────────────────────
# Scoring Engine
# ─────────────────────────────────────────────────────────────────────────────

def _score_criterion(criterion, answers_by_qno, fpo):
    """
    Calculate score for a criterion given the answers dict {question_no: answer}.
    Returns score as Decimal.
    """
    code = criterion.code

    # ── Age of FPO (computed) ─────────────────────────────────────────────────
    if code == 'age_of_fpo':
        if not fpo.date_of_registration:
            return Decimal('0')
        age_years = (date.today() - fpo.date_of_registration).days / 365.25
        if age_years > 5:
            return Decimal('5')
        elif age_years >= 3:
            return Decimal('4')
        elif age_years >= 1:
            return Decimal('2')
        return Decimal('1')

    # ── Board Representation (additive — Q1 + Q2 + Q3) ───────────────────────
    if code == 'board_representation':
        score = Decimal('0')
        # Q1 — board strength (1 mark)
        q1 = answers_by_qno.get(1)
        if q1 is not None:
            try:
                v = int(q1)
                score += Decimal('1') if 5 <= v <= 15 else Decimal('0')
            except (ValueError, TypeError):
                pass
        # Q2 — women directors (max 2)
        q2 = answers_by_qno.get(2)
        if q2 is not None:
            try:
                v = int(q2)
                score += Decimal('2') if v > 2 else (Decimal('1') if v >= 1 else Decimal('0'))
            except (ValueError, TypeError):
                pass
        # Q3 — small/marginal farmers (max 2)
        q3 = answers_by_qno.get(3)
        if q3 is not None:
            try:
                v = int(q3)
                score += Decimal('2') if v > 2 else (Decimal('1') if v == 1 else Decimal('0'))
            except (ValueError, TypeError):
                pass
        return min(score, Decimal('5'))

    # ── Governance Practices (additive — Q4 + Q5 + Q6) ───────────────────────
    if code == 'governance_practices':
        score = Decimal('0')
        # Q4 — meetings (4 marks if ≥ 4 meetings)
        q4 = answers_by_qno.get(4)
        if q4 is not None:
            try:
                score += Decimal('4') if int(q4) >= 4 else Decimal('0')
            except (ValueError, TypeError):
                pass
        # Q5 — AGM (2 marks)
        if answers_by_qno.get(5) == 'yes':
            score += Decimal('2')
        # Q6 — audited statements (4 marks)
        if answers_by_qno.get(6) == 'yes':
            score += Decimal('4')
        return min(score, Decimal('10'))

    # ── CEO Availability (Q7 single-select) ───────────────────────────────────
    if code == 'ceo_availability':
        mapping = {'fulltime_ceo': 5, 'parttime_ceo': 3, 'no_ceo': 0}
        return Decimal(str(mapping.get(answers_by_qno.get(7), 0)))

    # ── Human Resources (additive — Q8 + Q9 + Q10) ───────────────────────────
    if code == 'human_resources':
        score = Decimal('0')
        if answers_by_qno.get(8) == 'yes':  score += Decimal('2')
        if answers_by_qno.get(9) == 'yes':  score += Decimal('2')
        if answers_by_qno.get(10) == 'yes': score += Decimal('1')
        return min(score, Decimal('5'))

    # ── Capacity Building (percentage Q11 / Q12) ─────────────────────────────
    if code == 'capacity_building':
        try:
            trained = int(answers_by_qno.get(11, 0) or 0)
            total   = int(answers_by_qno.get(12, 0) or 0)
            if total == 0:
                return Decimal('0')
            pct = (trained / total) * 100
            if pct > 80:   return Decimal('5')
            if pct >= 50:  return Decimal('3')
            if pct >= 1:   return Decimal('1')
        except (ValueError, TypeError):
            pass
        return Decimal('0')

    # ── Active Membership (Q13 numeric range) ────────────────────────────────
    if code == 'active_membership':
        try:
            v = int(answers_by_qno.get(13, 0) or 0)
            if v > 1000:   return Decimal('10')
            if v >= 501:   return Decimal('8')
            if v >= 201:   return Decimal('6')
            if v >= 101:   return Decimal('4')
            return Decimal('2')
        except (ValueError, TypeError):
            return Decimal('0')

    # ── Share Capital Participation (percentage Q14 / Q15) ───────────────────
    if code == 'share_capital_participation':
        try:
            members_shares = int(answers_by_qno.get(14, 0) or 0)
            total_members  = int(answers_by_qno.get(15, 0) or 0)
            if total_members == 0:
                return Decimal('0')
            pct = (members_shares / total_members) * 100
            if pct > 90:   return Decimal('5')
            if pct >= 70:  return Decimal('4')
            if pct >= 50:  return Decimal('2')
        except (ValueError, TypeError):
            pass
        return Decimal('0')

    # ── Share Capital Mobilised (Q16 numeric range) ───────────────────────────
    if code == 'share_capital_mobilised':
        try:
            v = float(answers_by_qno.get(16, 0) or 0)
            if v > 1000000:   return Decimal('5')
            if v >= 500000:   return Decimal('4')
            if v >= 200000:   return Decimal('2')
            return Decimal('1')
        except (ValueError, TypeError):
            return Decimal('0')

    # ── Annual Turnover (Q17 numeric range) ───────────────────────────────────
    if code == 'annual_turnover':
        try:
            v = float(answers_by_qno.get(17, 0) or 0)
            if v > 10000000:  return Decimal('10')
            if v >= 5000000:  return Decimal('8')
            if v >= 2500000:  return Decimal('5')
            if v >= 1000000:  return Decimal('3')
            return Decimal('1')
        except (ValueError, TypeError):
            return Decimal('0')

    # ── Credit Linkage (Q18 conditional → Q20) ───────────────────────────────
    if code == 'credit_linkage':
        q18 = answers_by_qno.get(18)
        if q18 == 'yes':
            return Decimal('5')
        if q18 == 'no':
            q20 = answers_by_qno.get(20)
            if q20 == 'yes':
                return Decimal('3')
        return Decimal('0')

    # ── Office Infrastructure (Q21 single-select) ────────────────────────────
    if code == 'office_infrastructure':
        mapping = {'own_office': 5, 'rented_office': 3, 'shared_office': 1, 'no_office': 0}
        return Decimal(str(mapping.get(answers_by_qno.get(21), 0)))

    # ── Operational Infrastructure (additive Q21 implicit + Q22-Q25) ─────────
    if code == 'operational_infrastructure':
        score = Decimal('0')
        # Dedicated office presence = Q21 != no_office
        if answers_by_qno.get(21) not in (None, 'no_office'):
            score += Decimal('1')
        if answers_by_qno.get(22) == 'yes': score += Decimal('1')
        if answers_by_qno.get(23) == 'yes': score += Decimal('1')
        if answers_by_qno.get(24) == 'yes': score += Decimal('1')
        if answers_by_qno.get(25) == 'yes': score += Decimal('1')
        return min(score, Decimal('5'))

    # ── Market Linkage (Q26 multi-select count, cap 5) ────────────────────────
    if code == 'market_linkage':
        selected = answers_by_qno.get(26) or []
        if isinstance(selected, list):
            return min(Decimal(str(len(selected))), Decimal('5'))
        return Decimal('0')

    # ── Business Planning (Q27 single-select) ────────────────────────────────
    if code == 'business_planning':
        mapping = {'3year_plan': 5, 'annual_plan': 3, 'no_plan': 0}
        return Decimal(str(mapping.get(answers_by_qno.get(27), 0)))

    # ── Convergence & External Support (Q28 multi-select count) ──────────────
    if code == 'convergence_support':
        selected = answers_by_qno.get(28) or []
        if isinstance(selected, list):
            count = len(selected)
            if count >= 2: return Decimal('5')
            if count == 1: return Decimal('3')
        return Decimal('0')

    return Decimal('0')


def _calculate_total_score(fpo, answers_by_qno):
    """Calculate total score across all criteria. Returns (total, domain_scores)."""
    criteria   = TierCriterion.objects.select_related('domain').filter(is_active=True)
    total      = Decimal('0')
    domain_scores = {}

    for criterion in criteria:
        score     = _score_criterion(criterion, answers_by_qno, fpo)
        capped    = min(score, Decimal(str(criterion.max_marks)))
        total    += capped
        domain_code = criterion.domain.code
        domain_scores.setdefault(domain_code, Decimal('0'))
        domain_scores[domain_code] += capped

    return total, domain_scores


def _assign_tier(score):
    if score >= 80: return 'A'
    if score >= 65: return 'B'
    if score >= 50: return 'C'
    return 'D'


# ─────────────────────────────────────────────────────────────────────────────
# Serializers
# ─────────────────────────────────────────────────────────────────────────────

class QuestionSerializer(serializers.ModelSerializer):
    criterion_code = serializers.CharField(source='criterion.code', read_only=True)
    criterion_name = serializers.CharField(source='criterion.name', read_only=True)
    domain_code    = serializers.CharField(source='criterion.domain.code', read_only=True)
    domain_name    = serializers.CharField(source='criterion.domain.name', read_only=True)
    condition_on_question_no = serializers.SerializerMethodField()
    is_prefilled   = serializers.SerializerMethodField()

    # Questions auto-filled from FPO registration data — frontend shows these as read-only
    PREFILLED_QNOS = {1, 2, 8, 12, 15}

    class Meta:
        model  = TierQuestion
        fields = [
            'question_no', 'text', 'input_type', 'answer_config',
            'is_conditional', 'condition_on_question_no', 'condition_value',
            'is_required', 'has_upload', 'upload_label',
            'criterion_code', 'criterion_name', 'domain_code', 'domain_name',
            'is_prefilled',
        ]

    def get_condition_on_question_no(self, obj):
        return obj.condition_on.question_no if obj.condition_on else None

    def get_is_prefilled(self, obj):
        return obj.question_no in self.PREFILLED_QNOS


class AssessmentAnswerSerializer(serializers.ModelSerializer):
    question_no = serializers.IntegerField(source='question.question_no', read_only=True)

    class Meta:
        model  = AssessmentAnswer
        fields = ['question_no', 'answer', 'score']


class AssessmentUploadSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()

    class Meta:
        model  = AssessmentUpload
        fields = ['id', 'question_no', 'original_filename', 'file_url', 'uploaded_at']

    def get_file_url(self, obj):
        request = self.context.get('request')
        if request:
            return request.build_absolute_uri(obj.file.url)
        return obj.file.url


class AssessmentSerializer(serializers.ModelSerializer):
    answers = AssessmentAnswerSerializer(many=True, read_only=True)
    uploads = AssessmentUploadSerializer(many=True, read_only=True)

    class Meta:
        model  = FPOAssessment
        fields = [
            'id', 'financial_year', 'status',
            'total_score', 'tier_assigned', 'domain_scores', 'submitted_at',
            'created_at', 'updated_at', 'answers', 'uploads',
        ]


# ─────────────────────────────────────────────────────────────────────────────
# Views
# ─────────────────────────────────────────────────────────────────────────────

class TierAssessmentView(APIView):
    permission_classes = [IsFPOManager]

    @extend_schema(
        tags=['FPO - Tier Assessment'],
        summary='Get current assessment + all questions',
        description=(
            'Returns the current financial year assessment (if started) and the full '
            'list of 28 questions with their answer options and scoring config.\n\n'
            'If no assessment exists for the current year, `assessment` is null.\n\n'
            'Questions are ordered by question_no. Conditional questions include '
            '`condition_on_question_no` and `condition_value` for frontend to show/hide.'
        ),
        responses={200: None},
    )
    def get(self, request):
        fpo = _get_primary_fpo(request.user)
        if not fpo:
            return StandardResponse.error(
                'Only the primary user can access tier assessment.',
                status_code=status.HTTP_403_FORBIDDEN,
            )
        if fpo.status != FPOStatus.APPROVED:
            return StandardResponse.error(
                'Tier assessment is only available after FPO is approved.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        fy           = _current_financial_year()
        assessment   = FPOAssessment.objects.filter(fpo=fpo, financial_year=fy).first()
        questions    = TierQuestion.objects.select_related(
            'criterion', 'criterion__domain', 'condition_on'
        ).all()

        return StandardResponse.success({
            'financial_year': fy,
            'assessment':     AssessmentSerializer(assessment).data if assessment else None,
            'questions':      QuestionSerializer(questions, many=True).data,
        }, 'Assessment loaded.')

    @extend_schema(
        tags=['FPO - Tier Assessment'],
        summary='Start new assessment',
        description=(
            'Creates a new DRAFT assessment for the current financial year. '
            'Returns 409 if an assessment already exists for this year.'
        ),
        responses={201: None},
    )
    def post(self, request):
        fpo = _get_primary_fpo(request.user)
        if not fpo:
            return StandardResponse.error(
                'Only the primary user can start a tier assessment.',
                status_code=status.HTTP_403_FORBIDDEN,
            )
        if fpo.status != FPOStatus.APPROVED:
            return StandardResponse.error(
                'Tier assessment is only available after FPO is approved.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        fy = _current_financial_year()
        if FPOAssessment.objects.filter(fpo=fpo, financial_year=fy).exists():
            return StandardResponse.error(
                f'An assessment already exists for {fy}. Use PATCH to update answers.',
                status_code=status.HTTP_409_CONFLICT,
            )

        assessment = FPOAssessment.objects.create(
            fpo=fpo,
            financial_year=fy,
            status=FPOAssessment.Status.DRAFT,
            created_by=request.user,
        )
        _prefill_answers(assessment, fpo)

        return StandardResponse.created(
            data=AssessmentSerializer(assessment).data,
            message=f'Assessment for {fy} started.',
        )


class TierAssessmentDetailView(APIView):
    permission_classes = [IsFPOManager]

    def _get_assessment(self, request, assessment_id):
        fpo = _get_primary_fpo(request.user)
        if not fpo:
            return None, StandardResponse.error(
                'Only the primary user can manage tier assessment.',
                status_code=status.HTTP_403_FORBIDDEN,
            )
        try:
            assessment = FPOAssessment.objects.get(id=assessment_id, fpo=fpo)
            return assessment, None
        except FPOAssessment.DoesNotExist:
            return None, StandardResponse.error(
                'Assessment not found.',
                status_code=status.HTTP_404_NOT_FOUND,
            )

    @extend_schema(
        tags=['FPO - Tier Assessment'],
        summary='Save answers (auto-save)',
        description=(
            'Save answers for one or more questions. Safe to call on every field change '
            '(auto-save). Partial — only questions included in the request are updated.\n\n'
            '**Request body:**\n'
            '```json\n'
            '{ "answers": { "7": "fulltime_ceo", "8": "yes", "13": 250, "26": ["local_market", "trader_wholesaler"] } }\n'
            '```\n\n'
            'Keys are question numbers as strings. Values match the question input_type.'
        ),
        responses={200: None},
    )
    def patch(self, request, assessment_id):
        assessment, err = self._get_assessment(request, assessment_id)
        if err:
            return err

        if assessment.status == FPOAssessment.Status.SUBMITTED:
            fy = assessment.financial_year
            current_fy = _current_financial_year()
            if fy != current_fy:
                return StandardResponse.error(
                    'Previous year assessments are read-only.',
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

        answers_input = request.data.get('answers', {})
        if not isinstance(answers_input, dict):
            return StandardResponse.error('answers must be a dict of {question_no: answer}.',
                                          status_code=status.HTTP_400_BAD_REQUEST)

        PREFILLED_QNOS = {1, 2, 8, 12, 15}
        question_map = {q.question_no: q for q in TierQuestion.objects.all()}
        saved = []

        for qno_str, answer in answers_input.items():
            try:
                qno = int(qno_str)
            except (ValueError, TypeError):
                continue
            if qno in PREFILLED_QNOS:
                continue  # pre-filled from FPO profile — not editable
            if answer is None:
                continue  # null = conditional question not applicable — skip
            question = question_map.get(qno)
            if not question:
                continue

            AssessmentAnswer.objects.update_or_create(
                assessment=assessment,
                question=question,
                defaults={'answer': answer, 'score': 0},
            )
            saved.append(qno)

        assessment.updated_at = timezone.now()
        assessment.save(update_fields=['updated_at'])

        return StandardResponse.success(
            data={'saved_questions': saved},
            message=f'{len(saved)} answer(s) saved.',
        )


class TierAssessmentSubmitView(APIView):
    permission_classes = [IsFPOManager]

    @extend_schema(
        tags=['FPO - Tier Assessment'],
        summary='Submit assessment → auto-score → tier assigned',
        description=(
            'Validates all required questions are answered, runs the scoring engine, '
            'assigns a tier (A/B/C/D), and creates a FPOTierHistory record.\n\n'
            'The FPO dashboard tier badge is updated immediately.'
        ),
        responses={200: None},
    )
    def post(self, request, assessment_id):
        fpo = _get_primary_fpo(request.user)
        if not fpo:
            return StandardResponse.error(
                'Only the primary user can submit a tier assessment.',
                status_code=status.HTTP_403_FORBIDDEN,
            )

        try:
            assessment = FPOAssessment.objects.prefetch_related('answers__question').get(
                id=assessment_id, fpo=fpo,
            )
        except FPOAssessment.DoesNotExist:
            return StandardResponse.error('Assessment not found.', status_code=status.HTTP_404_NOT_FOUND)

        # Check required questions answered
        answered_qnos = set(assessment.answers.values_list('question__question_no', flat=True))
        required_qnos = set(
            TierQuestion.objects
            .filter(is_required=True)
            .exclude(input_type='computed')
            .values_list('question_no', flat=True)
        )
        # Remove conditional questions from required check
        conditional_qnos = set(
            TierQuestion.objects.filter(is_conditional=True).values_list('question_no', flat=True)
        )
        required_qnos -= conditional_qnos

        missing = required_qnos - answered_qnos
        if missing:
            return StandardResponse.error(
                f'Please answer all required questions. Missing: Q{sorted(missing)}',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # Build answers dict
        answers_by_qno = {
            a.question.question_no: a.answer
            for a in assessment.answers.select_related('question').all()
        }

        # Score all criteria and save per-answer scores
        with transaction.atomic():
            criteria = TierCriterion.objects.select_related('domain').filter(is_active=True)
            total_score, domain_scores = _calculate_total_score(fpo, answers_by_qno)

            # Update per-answer scores (for breakdown display)
            for answer_obj in assessment.answers.select_related('question__criterion').all():
                criterion = answer_obj.question.criterion
                # Store criterion score on the answer for the primary question of each criterion
                pass  # Score breakdown stored at assessment level

            tier = _assign_tier(float(total_score))

            assessment.total_score   = total_score
            assessment.tier_assigned = tier
            assessment.domain_scores = {k: float(v) for k, v in domain_scores.items()}
            assessment.status        = FPOAssessment.Status.SUBMITTED
            assessment.submitted_at  = timezone.now()
            assessment.updated_by    = request.user
            assessment.save()

            # Create FPOTierHistory — syncs FPO.tier
            FPOTierHistory.objects.create(
                fpo            = fpo,
                tier           = tier,
                financial_year = assessment.financial_year,
                assigned_by    = request.user,
                notes          = f'Auto-scored via tier assessment. Total score: {total_score}/100',
            )

        AuditService.log(
            user=request.user,
            action=AuditLog.Action.TIER_RECALCULATION,
            instance=fpo,
            request=request,
            changes={
                'financial_year': assessment.financial_year,
                'total_score':    str(total_score),
                'tier':           tier,
                'domain_scores':  {k: str(v) for k, v in domain_scores.items()},
            },
        )

        return StandardResponse.success(
            data={
                'tier':          tier,
                'total_score':   float(total_score),
                'domain_scores': {k: float(v) for k, v in domain_scores.items()},
                'financial_year': assessment.financial_year,
            },
            message=f'Assessment submitted. Your FPO has been assigned Tier {tier} for {assessment.financial_year}.',
        )


class TierAssessmentHistoryView(APIView):
    permission_classes = [IsFPOManager]

    @extend_schema(
        tags=['FPO - Tier Assessment'],
        summary='Assessment history across all years',
        description='Returns all past assessments for this FPO, ordered by most recent year first.',
        responses={200: AssessmentSerializer(many=True)},
    )
    def get(self, request):
        fpo = _get_primary_fpo(request.user)
        if not fpo:
            return StandardResponse.error(
                'Only the primary user can view assessment history.',
                status_code=status.HTTP_403_FORBIDDEN,
            )

        assessments = FPOAssessment.objects.filter(fpo=fpo).prefetch_related(
            'answers__question'
        ).order_by('-financial_year')

        return StandardResponse.success(
            AssessmentSerializer(assessments, many=True).data,
            'Assessment history retrieved.',
        )


class TierAssessmentReopenView(APIView):
    permission_classes = [IsFPOManager]

    @extend_schema(
        tags=['FPO - Tier Assessment'],
        summary='Reopen submitted assessment for current year',
        description=(
            'Resets a submitted assessment back to DRAFT so the FPO can correct answers and resubmit.\n\n'
            'Only allowed for the **current financial year**. Previous year assessments cannot be reopened.\n\n'
            'The tier badge on the dashboard reverts to the previous year\'s tier (or null) until resubmitted.'
        ),
        responses={200: None},
    )
    def post(self, request, assessment_id):
        fpo = _get_primary_fpo(request.user)
        if not fpo:
            return StandardResponse.error(
                'Only the primary user can reopen a tier assessment.',
                status_code=status.HTTP_403_FORBIDDEN,
            )

        try:
            assessment = FPOAssessment.objects.get(id=assessment_id, fpo=fpo)
        except FPOAssessment.DoesNotExist:
            return StandardResponse.error('Assessment not found.', status_code=status.HTTP_404_NOT_FOUND)

        if assessment.financial_year != _current_financial_year():
            return StandardResponse.error(
                'Only the current year assessment can be reopened.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        if assessment.status != FPOAssessment.Status.SUBMITTED:
            return StandardResponse.error(
                'Assessment is already in draft.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            # Revert tier history — remove the entry for this year
            FPOTierHistory.objects.filter(
                fpo=fpo,
                financial_year=assessment.financial_year,
            ).delete()

            # Sync FPO.tier to previous year's tier (or empty)
            prev = FPOTierHistory.objects.filter(fpo=fpo).order_by('-created_at').first()
            fpo.tier = prev.tier if prev else ''
            fpo.save(update_fields=['tier'])

            # Reset assessment to draft
            assessment.status        = FPOAssessment.Status.DRAFT
            assessment.total_score   = None
            assessment.tier_assigned = ''
            assessment.domain_scores = {}
            assessment.submitted_at  = None
            assessment.save()

        return StandardResponse.success(
            data=AssessmentSerializer(assessment).data,
            message='Assessment reopened. You can now update your answers and resubmit.',
        )


# Upload-enabled question numbers
UPLOAD_QUESTION_NOS = {6, 17, 27}

# Allowed mime types for assessment uploads
ALLOWED_MIME_TYPES = {'application/pdf', 'image/jpeg', 'image/png'}
MAX_UPLOAD_SIZE    = 5 * 1024 * 1024  # 5 MB


class TierAssessmentUploadView(APIView):
    permission_classes = [IsFPOManager]

    @extend_schema(
        tags=['FPO - Tier Assessment'],
        summary='Upload supporting document for a question',
        description=(
            'Upload a supporting document for Q6, Q17, or Q27.\n\n'
            '**Form fields:**\n'
            '- `question_no` — 6, 17, or 27\n'
            '- `file` — PDF, JPG, or PNG, max 5 MB\n\n'
            'Multiple files can be uploaded for the same question (e.g. Q6 needs two files).\n'
            'Returns the upload record with `id` and `file_url`.'
        ),
        responses={201: None},
    )
    def post(self, request, assessment_id):
        fpo = _get_primary_fpo(request.user)
        if not fpo:
            return StandardResponse.error(
                'Only the primary user can upload assessment documents.',
                status_code=status.HTTP_403_FORBIDDEN,
            )

        try:
            assessment = FPOAssessment.objects.get(id=assessment_id, fpo=fpo)
        except FPOAssessment.DoesNotExist:
            return StandardResponse.error('Assessment not found.', status_code=status.HTTP_404_NOT_FOUND)

        if assessment.status == FPOAssessment.Status.SUBMITTED:
            if assessment.financial_year != _current_financial_year():
                return StandardResponse.error(
                    'Previous year assessments are read-only.',
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

        try:
            question_no = int(request.data.get('question_no', 0))
        except (ValueError, TypeError):
            question_no = 0

        if question_no not in UPLOAD_QUESTION_NOS:
            return StandardResponse.error(
                f'File uploads are only allowed for questions {sorted(UPLOAD_QUESTION_NOS)}.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        file = request.FILES.get('file')
        if not file:
            return StandardResponse.error('No file provided.', status_code=status.HTTP_400_BAD_REQUEST)

        if file.content_type not in ALLOWED_MIME_TYPES:
            return StandardResponse.error(
                'Only PDF, JPG, and PNG files are allowed.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        if file.size > MAX_UPLOAD_SIZE:
            return StandardResponse.error(
                'File size must not exceed 5 MB.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        upload = AssessmentUpload.objects.create(
            assessment        = assessment,
            question_no       = question_no,
            file              = file,
            original_filename = file.name,
        )

        return StandardResponse.created(
            data=AssessmentUploadSerializer(upload, context={'request': request}).data,
            message='Document uploaded successfully.',
        )


class TierAssessmentUploadDeleteView(APIView):
    permission_classes = [IsFPOManager]

    @extend_schema(
        tags=['FPO - Tier Assessment'],
        summary='Delete an uploaded document',
        description='Delete a previously uploaded supporting document by its upload ID.',
        responses={200: None},
    )
    def delete(self, request, assessment_id, upload_id):
        fpo = _get_primary_fpo(request.user)
        if not fpo:
            return StandardResponse.error(
                'Only the primary user can delete assessment documents.',
                status_code=status.HTTP_403_FORBIDDEN,
            )

        try:
            upload = AssessmentUpload.objects.select_related('assessment').get(
                id=upload_id,
                assessment__id=assessment_id,
                assessment__fpo=fpo,
            )
        except AssessmentUpload.DoesNotExist:
            return StandardResponse.error('Upload not found.', status_code=status.HTTP_404_NOT_FOUND)

        if upload.assessment.status == FPOAssessment.Status.SUBMITTED:
            if upload.assessment.financial_year != _current_financial_year():
                return StandardResponse.error(
                    'Cannot delete documents from a previous year assessment.',
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

        upload.file.delete(save=False)
        upload.delete()

        return StandardResponse.success(data=None, message='Document deleted.')
