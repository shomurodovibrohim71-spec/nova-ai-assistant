"""Lazy-init wrapper around the Anthropic async client."""
from __future__ import annotations

import logging
from typing import Any

from ..config import settings

log = logging.getLogger(__name__)


class AnthropicClient:
    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or settings.anthropic_api_key
        self._client: Any = None

    @property
    def available(self) -> bool:
        return bool(self._api_key)

    def get(self) -> Any:
        if self._client is not None:
            return self._client
        if not self._api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set")
        try:
            from anthropic import AsyncAnthropic
        except ImportError as e:
            raise RuntimeError(
                "anthropic package not installed. Run: pip install -r requirements.txt"
            ) from e
        self._client = AsyncAnthropic(api_key=self._api_key)
        log.info("Anthropic client initialized")
        return self._client
