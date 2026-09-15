"""
KAU-FPO Chatbot Service — extractive question-answering microservice.

Separate from ml_service (crop recommendation) so the two workloads don't
share resources or deploy cycles. Runs on its own port (default 8002)
inside its own container.

Public contract:
    GET  /health              -> {"status": "ok", "model": "...", "ready": bool}
    POST /qa/answer           -> {"answer": str, "score": float, "confident": bool}
    POST /qa/reload           -> force-reload the QA model (admin-only via nginx)

Django (apps.chatbot) calls /qa/answer after retrieving the top KB entries
via Postgres FTS. See context/CHATBOT_PLAN.md for the whole architecture.
"""

import logging
import os

from fastapi import FastAPI
from pydantic import BaseModel, Field

from qa import (
    QA_MODEL_NAME,
    answer_question,
    load_qa_pipeline,
)


logging.basicConfig(
    level=os.environ.get('LOG_LEVEL', 'INFO'),
    format='%(asctime)s %(levelname)s %(name)s: %(message)s',
)
logger = logging.getLogger('chatbot_service')

app = FastAPI(title='KAU-FPO Chatbot Service', version='0.1.0')

# Tracks whether load_qa_pipeline() succeeded. Startup logs the outcome
# but the service stays up either way — /health reports readiness.
_ready = False


class AnswerRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    context:  str = Field(min_length=1, max_length=8000)


class AnswerResponse(BaseModel):
    answer:    str
    score:     float
    start:     int
    end:       int
    confident: bool


@app.on_event('startup')
def _load_model():
    """Try to load the QA model. Non-fatal if it fails — /health shows ready=False."""
    global _ready
    try:
        load_qa_pipeline()
        _ready = True
        logger.info('startup complete: QA model ready')
    except Exception as e:
        _ready = False
        logger.error('QA model load failed at startup: %s', e)


@app.get('/health')
def health():
    return {
        'status': 'ok',
        'model':  QA_MODEL_NAME,
        'ready':  _ready,
    }


@app.post('/qa/answer', response_model=AnswerResponse)
def qa_answer(req: AnswerRequest):
    """Answer a question extractively from a provided context.

    Never raises for bad input — returns a low-confidence empty answer.
    Django decides how to handle low confidence (usually a fallback template).
    """
    result = answer_question(req.question, req.context)
    return AnswerResponse(**result)


@app.post('/qa/reload')
def qa_reload():
    """Force-reload the QA model. Useful after tweaking QA_MODEL_NAME env var
    without a container restart."""
    global _ready
    try:
        # Clear cached pipeline so load_qa_pipeline() re-instantiates.
        import qa as qa_mod
        qa_mod._pipeline = None
        load_qa_pipeline()
        _ready = True
        return {'status': 'reloaded', 'model': QA_MODEL_NAME}
    except Exception as e:
        _ready = False
        logger.error('QA reload failed: %s', e)
        return {'status': 'failed', 'error': str(e)}
