"""
HTTP client for the chatbot_service microservice.

chatbot_service runs the extractive QA model (tinyroberta-squad2) as a
separate FastAPI container on port 8002. Django never runs the transformer
locally -- it only sends {question, context} and receives {answer, score}.

Fails soft: on any HTTP/timeout/parse error, returns an empty low-
confidence result. The caller (message endpoint) surfaces a friendly
fallback message when confident=False.
"""

import logging
from typing import Optional

import requests
from django.conf import settings


logger = logging.getLogger(__name__)


DEFAULT_TIMEOUT_SECONDS = 5   # QA inference is ~100ms on CPU; 5s is 50x headroom.


def ask(question: str, context: str, timeout: Optional[float] = None) -> dict:
    """POST to chatbot_service /qa/answer.

    Returns:
        {
            'answer':    <str>,     # empty string on failure
            'score':     <float>,   # 0.0 on failure
            'start':     <int>,
            'end':       <int>,
            'confident': <bool>,    # False on failure
        }

    Never raises. Any exception is logged and swallowed as low-confidence.
    """
    url = getattr(settings, 'CHATBOT_SERVICE_URL', 'http://localhost:8002').rstrip('/')
    endpoint = f'{url}/qa/answer'

    empty = {'answer': '', 'score': 0.0, 'start': 0, 'end': 0, 'confident': False}

    if not question or not context:
        return empty

    try:
        resp = requests.post(
            endpoint,
            json={'question': question, 'context': context},
            timeout=timeout or DEFAULT_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            'answer':    str(data.get('answer', '')).strip(),
            'score':     float(data.get('score', 0.0)),
            'start':     int(data.get('start', 0)),
            'end':       int(data.get('end', 0)),
            'confident': bool(data.get('confident', False)),
        }
    except requests.exceptions.Timeout:
        logger.warning('chatbot_service timeout on /qa/answer (>%ss)', timeout or DEFAULT_TIMEOUT_SECONDS)
        return empty
    except requests.exceptions.ConnectionError:
        logger.warning('chatbot_service unreachable at %s', endpoint)
        return empty
    except requests.exceptions.RequestException as e:
        logger.warning('chatbot_service HTTP error: %s', e)
        return empty
    except (ValueError, KeyError, TypeError) as e:
        logger.warning('chatbot_service returned malformed JSON: %s', e)
        return empty
