"""Async DeepSeek client using the OpenAI-compatible SDK."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from openai import AsyncOpenAI, APIConnectionError, RateLimitError, APITimeoutError

from src.config import DeepSeekConfig
from src.exceptions import ChatConnectionError, ChatRateLimitError

logger = logging.getLogger(__name__)


class DeepSeekClient:
    """Async streaming client for the DeepSeek chat API."""

    def __init__(self, config: DeepSeekConfig) -> None:
        self._client = AsyncOpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
            timeout=float(config.timeout_seconds),
        )
        self._model = config.model
        self._max_tokens = config.max_tokens
        self._temperature = config.temperature

    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        system_prompt: str,
    ) -> AsyncIterator[str]:
        """Stream chat completion, yielding content deltas.

        Args:
            messages: Conversation history [{role, content}, ...].
            system_prompt: System prompt prepended to messages.

        Yields:
            Content delta strings from the LLM.

        Raises:
            ChatConnectionError: On network/API connection issues.
            ChatRateLimitError: When the API rate limit is hit.
        """
        full_messages = [{"role": "system", "content": system_prompt}] + messages
        try:
            stream = await self._client.chat.completions.create(
                model=self._model,
                messages=full_messages,
                max_tokens=self._max_tokens,
                temperature=self._temperature,
                stream=True,
            )
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except RateLimitError as exc:
            logger.warning("DeepSeek rate limit hit: %s", exc)
            raise ChatRateLimitError(str(exc)) from exc
        except (APIConnectionError, APITimeoutError) as exc:
            logger.error("DeepSeek connection error: %s", exc)
            raise ChatConnectionError(str(exc)) from exc

    async def chat(
        self,
        messages: list[dict[str, str]],
        system_prompt: str,
    ) -> str:
        """Non-streaming chat completion. Returns full response text."""
        full_messages = [{"role": "system", "content": system_prompt}] + messages
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=full_messages,
                max_tokens=self._max_tokens,
                temperature=self._temperature,
                stream=False,
            )
            return response.choices[0].message.content or ""
        except RateLimitError as exc:
            logger.warning("DeepSeek rate limit hit: %s", exc)
            raise ChatRateLimitError(str(exc)) from exc
        except (APIConnectionError, APITimeoutError) as exc:
            logger.error("DeepSeek connection error: %s", exc)
            raise ChatConnectionError(str(exc)) from exc

    async def close(self) -> None:
        """Shutdown the underlying httpx client."""
        await self._client.close()
