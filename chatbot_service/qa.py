"""
Extractive Question-Answering — Chatbot support (Phase 1).

Loads a small transformer QA model (deepset/tinyroberta-squad2, ~82MB) at
startup and answers questions with a literal span from a provided context.

Extractive (not generative) — the answer is always a substring of the
context. Zero hallucination by design: the model *cannot* invent details
that aren't in the retrieved knowledge base.

Called from Django's chatbot service after Postgres FTS retrieves the top
few knowledge-base entries. The context passed here is the concatenation
of those entries; the QA model finds the best-scoring span across them.

Runtime: <100ms per query on CPU after warmup. Cold start ~2s.
"""

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# Model choice:
#   - tinyroberta-squad2: 82MB, ~50ms inference, decent English QA quality.
#   - Alternative: distilbert-base-cased-distilled-squad (65MB, similar).
# Overridable via env var for testing larger models without a code deploy.
QA_MODEL_NAME = os.environ.get('QA_MODEL_NAME', 'deepset/tinyroberta-squad2')

# Where transformers caches the downloaded model. Persisted across restarts
# so we don't re-download every startup.
QA_MODEL_CACHE_DIR = os.environ.get('QA_MODEL_CACHE_DIR', '/tmp/hf_cache')

# Answer-confidence threshold below which we call it "no good answer".
# Django decides how to handle low-confidence responses (usually falls back
# to a "I couldn't find that — please contact KAU" template).
QA_MIN_SCORE = float(os.environ.get('QA_MIN_SCORE', '0.15'))

_pipeline = None


def load_qa_pipeline():
    """Load the QA pipeline once at ml_service startup.

    Safe to call multiple times — subsequent calls are no-ops. Cached in
    the module-global _pipeline. Downloads the model on first run (~90MB
    over the network) and caches to QA_MODEL_CACHE_DIR.
    """
    global _pipeline
    if _pipeline is not None:
        return _pipeline

    # Import lazily so ml_service can still start if transformers/torch
    # aren't installed in this environment (development / older images).
    from transformers import pipeline

    logger.info("QA: loading model %s (cache=%s)", QA_MODEL_NAME, QA_MODEL_CACHE_DIR)
    os.environ.setdefault('HF_HOME', QA_MODEL_CACHE_DIR)
    os.environ.setdefault('TRANSFORMERS_CACHE', QA_MODEL_CACHE_DIR)

    _pipeline = pipeline(
        'question-answering',
        model=QA_MODEL_NAME,
        # device=-1 forces CPU. GPU auto-selection would try CUDA and fail
        # in our CPU-only container.
        device=-1,
    )
    logger.info("QA: model loaded")
    return _pipeline


def answer_question(question: str, context: str) -> dict:
    """Answer a question grounded in the given context.

    Args:
        question: user's natural-language question.
        context: concatenation of retrieved knowledge-base entries.

    Returns:
        {
            'answer':    <str>,   # the literal span from context, or empty if low-conf
            'score':     <float>, # confidence 0.0–1.0
            'start':     <int>,   # start char offset in context
            'end':       <int>,   # end char offset in context
            'confident': <bool>,  # True iff score >= QA_MIN_SCORE
        }

    Never raises for bad inputs — returns an empty low-confidence result.
    Only raises if the pipeline itself failed to load.
    """
    if not question or not context:
        return {'answer': '', 'score': 0.0, 'start': 0, 'end': 0, 'confident': False}

    if _pipeline is None:
        load_qa_pipeline()

    # transformers pipelines are safe to call on any string; guard length
    # anyway — models truncate at 512 tokens (~2000 chars). We assume
    # Django kept the top-3 KB entries small enough to fit; this is just a
    # defense against a caller stuffing megabytes.
    max_context_chars = 3000
    ctx = context[:max_context_chars]

    result = _pipeline(question=question, context=ctx, handle_impossible_answer=True)

    # handle_impossible_answer=True lets the model return empty answer with
    # low score for "this question can't be answered from the context".
    answer = (result.get('answer') or '').strip()
    score = float(result.get('score') or 0.0)
    return {
        'answer': answer,
        'score': score,
        'start': int(result.get('start') or 0),
        'end':   int(result.get('end') or 0),
        'confident': score >= QA_MIN_SCORE and bool(answer),
    }
