"""
AI Translation Service
=======================
Wraps the Anthropic API for batch-translating admin UI strings.

Location convention: apps/core/services/ai_translation.py
Author:Aleena LT
created: 2026-08-22
"""

import json
import logging

from django.conf import settings
from anthropic import Anthropic, APIError, APITimeoutError

logger = logging.getLogger(__name__)

BATCH_SIZE = 50

SYSTEM_PROMPT = (
    "You are translating short UI/admin strings for a Kerala state government "
    "agricultural platform (Farmer Producer Organizations — FPO). "
    "Domain: agriculture, government administration, farmer services. "
    "Register: formal, respectful, consistent with official Kerala government "
    "digital service terminology. "
    "You will receive a JSON object mapping translation keys to English strings. "
    "Return ONLY a JSON object with the exact same keys, where each value is the "
    "translation into {target_language}. "
    "Do not add, remove, or rename keys. Do not add commentary, markdown, or "
    "code fences — return raw JSON only."
)


class AITranslationService:
    """
    Batches English strings and sends them to Claude for translation.

    Usage:
        service = AITranslationService()
        translated, failed_keys = service.translate_all(
            {"auth.login_success": "Login successful"},
            target_language="Hindi",
        )
    """

    def __init__(self):
        # NOTE: API key currently read from settings/env (ANTHROPIC_API_KEY).
        # Swap this line for a DB-backed credentials lookup later if needed —
        # nothing else in this file depends on where the key comes from.
        self.client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        self.model = getattr(settings, "ANTHROPIC_TRANSLATE_MODEL", "claude-haiku-4-5-20251001")

    def translate_batch(self, key_value_map: dict, target_language: str) -> tuple[dict, list]:
        """
        Translate a single batch (<= BATCH_SIZE keys) of English strings.
        Returns (translated_map, failed_keys).
        """
        if not key_value_map:
            return {}, []

        system = SYSTEM_PROMPT.format(target_language=target_language)
        user_payload = json.dumps(key_value_map, ensure_ascii=False)

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4000,
                system=system,
                messages=[{"role": "user", "content": user_payload}],
            )
        except (APIError, APITimeoutError) as exc:
            logger.error("AI translation batch failed: %s", exc)
            return {}, list(key_value_map.keys())

        raw_text = "".join(
            block.text for block in response.content if getattr(block, "type", None) == "text"
        ).strip()

        if raw_text.startswith("```"):
            raw_text = raw_text.strip("`")
            raw_text = raw_text.split("\n", 1)[-1] if "\n" in raw_text else raw_text

        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError:
            logger.error("AI translation returned non-JSON response: %s", raw_text[:500])
            return {}, list(key_value_map.keys())

        translated = {}
        failed_keys = []
        for key in key_value_map:
            value = parsed.get(key)
            if isinstance(value, str) and value.strip():
                translated[key] = value
            else:
                failed_keys.append(key)

        return translated, failed_keys

    def translate_all(self, key_value_map: dict, target_language: str) -> tuple[dict, list]:
        """
        Chunks key_value_map into batches of BATCH_SIZE and translates each.
        Returns (translated_map, failed_keys) aggregated across all batches.
        """
        items = list(key_value_map.items())
        translated_all = {}
        failed_all = []

        for i in range(0, len(items), BATCH_SIZE):
            chunk = dict(items[i:i + BATCH_SIZE])
            translated, failed = self.translate_batch(chunk, target_language)
            translated_all.update(translated)
            failed_all.extend(failed)

        return translated_all, failed_all