"""Tests for DeepSeek client."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.chat.client import DeepSeekClient
from src.config import DeepSeekConfig
from src.exceptions import ChatConnectionError, ChatRateLimitError


@pytest.fixture
def config():
    return DeepSeekConfig(
        api_key="test-key",
        base_url="https://api.test.com",
        model="test-model",
        max_tokens=512,
        temperature=0.5,
        timeout_seconds=10,
    )


class TestDeepSeekClient:
    """Tests for DeepSeekClient."""

    @patch("src.chat.client.AsyncOpenAI")
    def test_init(self, mock_openai_cls, config):
        client = DeepSeekClient(config)
        mock_openai_cls.assert_called_once_with(
            api_key="test-key",
            base_url="https://api.test.com",
            timeout=10.0,
        )
        assert client._model == "test-model"
        assert client._max_tokens == 512
        assert client._temperature == 0.5

    @pytest.mark.asyncio
    @patch("src.chat.client.AsyncOpenAI")
    async def test_chat_non_streaming(self, mock_openai_cls, config):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Hello response"
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        client = DeepSeekClient(config)
        result = await client.chat(
            [{"role": "user", "content": "Hello"}],
            "System prompt",
        )

        assert result == "Hello response"
        mock_client.chat.completions.create.assert_called_once()
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["model"] == "test-model"
        assert call_kwargs["stream"] is False
        assert len(call_kwargs["messages"]) == 2
        assert call_kwargs["messages"][0]["role"] == "system"

    @pytest.mark.asyncio
    @patch("src.chat.client.AsyncOpenAI")
    async def test_stream_chat(self, mock_openai_cls, config):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        # Create mock chunks
        chunk1 = MagicMock()
        chunk1.choices = [MagicMock()]
        chunk1.choices[0].delta.content = "Hello"

        chunk2 = MagicMock()
        chunk2.choices = [MagicMock()]
        chunk2.choices[0].delta.content = " world"

        chunk3 = MagicMock()
        chunk3.choices = [MagicMock()]
        chunk3.choices[0].delta.content = None

        async def mock_stream():
            for chunk in [chunk1, chunk2, chunk3]:
                yield chunk

        mock_client.chat.completions.create = AsyncMock(return_value=mock_stream())

        client = DeepSeekClient(config)
        collected = []
        async for delta in client.stream_chat(
            [{"role": "user", "content": "Hi"}],
            "System prompt",
        ):
            collected.append(delta)

        assert collected == ["Hello", " world"]

    @pytest.mark.asyncio
    @patch("src.chat.client.AsyncOpenAI")
    async def test_close(self, mock_openai_cls, config):
        mock_client = MagicMock()
        mock_client.close = AsyncMock()
        mock_openai_cls.return_value = mock_client

        client = DeepSeekClient(config)
        await client.close()
        mock_client.close.assert_called_once()

    @pytest.mark.asyncio
    @patch("src.chat.client.AsyncOpenAI")
    async def test_rate_limit_error(self, mock_openai_cls, config):
        from openai import RateLimitError

        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.headers = {}
        mock_client.chat.completions.create = AsyncMock(
            side_effect=RateLimitError(
                message="Rate limit exceeded",
                response=mock_resp,
                body=None,
            )
        )

        client = DeepSeekClient(config)
        with pytest.raises(ChatRateLimitError):
            await client.chat([{"role": "user", "content": "test"}], "system")

    @pytest.mark.asyncio
    @patch("src.chat.client.AsyncOpenAI")
    async def test_connection_error(self, mock_openai_cls, config):
        from openai import APIConnectionError

        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        mock_client.chat.completions.create = AsyncMock(
            side_effect=APIConnectionError(request=MagicMock())
        )

        client = DeepSeekClient(config)
        with pytest.raises(ChatConnectionError):
            await client.chat([{"role": "user", "content": "test"}], "system")
