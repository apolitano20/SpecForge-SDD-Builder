"""Tests for ard.utils.parsing: strip_fences, invoke_with_retry."""

import json
from unittest.mock import patch, MagicMock

import httpx
import pytest

from ard.utils.parsing import strip_fences, invoke_with_retry


# --- strip_fences ---

class TestStripFences:
    def test_strip_json_fences(self):
        text = '```json\n{"key": "value"}\n```'
        assert strip_fences(text) == '{"key": "value"}'

    def test_strip_plain_fences(self):
        text = '```\n{"key": "value"}\n```'
        assert strip_fences(text) == '{"key": "value"}'

    def test_no_fences_returns_stripped(self):
        text = '  {"key": "value"}  '
        assert strip_fences(text) == '{"key": "value"}'

    def test_fences_with_extra_whitespace(self):
        text = '```json\n\n  {"key": "value"}  \n\n```'
        assert strip_fences(text).startswith("{")


# --- invoke_with_retry ---

class TestInvokeWithRetry:
    def _mock_llm(self, side_effect):
        llm = MagicMock()
        llm.invoke.side_effect = side_effect
        return llm

    @patch("ard.config._config", {"llm_max_retries": 3})
    def test_succeeds_on_first_try(self):
        response = MagicMock()
        response.content = '{"ok": true}'
        llm = self._mock_llm([response])

        result = invoke_with_retry(llm, [{"role": "user", "content": "hi"}])

        assert result.content == '{"ok": true}'
        assert llm.invoke.call_count == 1

    @patch("ard.config._config", {"llm_max_retries": 3})
    def test_retries_on_connect_error(self):
        response = MagicMock()
        response.content = '{"ok": true}'
        llm = self._mock_llm([
            httpx.ConnectError("connection refused"),
            response,
        ])

        result = invoke_with_retry(llm, [{"role": "user", "content": "hi"}])

        assert result.content == '{"ok": true}'
        assert llm.invoke.call_count == 2

    @patch("ard.config._config", {"llm_max_retries": 3})
    def test_retries_on_timeout(self):
        response = MagicMock()
        response.content = '{"ok": true}'
        llm = self._mock_llm([
            httpx.ReadTimeout("read timed out"),
            response,
        ])

        result = invoke_with_retry(llm, [{"role": "user", "content": "hi"}])

        assert result.content == '{"ok": true}'
        assert llm.invoke.call_count == 2

    @patch("ard.config._config", {"llm_max_retries": 3})
    def test_retries_on_429(self):
        response_429 = httpx.Response(429, request=httpx.Request("POST", "https://api.example.com"))
        response = MagicMock()
        response.content = '{"ok": true}'
        llm = self._mock_llm([
            httpx.HTTPStatusError("rate limited", request=response_429.request, response=response_429),
            response,
        ])

        result = invoke_with_retry(llm, [{"role": "user", "content": "hi"}])

        assert result.content == '{"ok": true}'
        assert llm.invoke.call_count == 2

    @patch("ard.config._config", {"llm_max_retries": 2})
    def test_raises_after_max_retries(self):
        llm = self._mock_llm([
            httpx.ConnectError("fail 1"),
            httpx.ConnectError("fail 2"),
            httpx.ConnectError("fail 3"),
        ])

        with pytest.raises(httpx.ConnectError):
            invoke_with_retry(llm, [{"role": "user", "content": "hi"}])

        assert llm.invoke.call_count == 3  # 1 initial + 2 retries

    @patch("ard.config._config", {"llm_max_retries": 3})
    def test_does_not_retry_on_auth_error(self):
        response_401 = httpx.Response(401, request=httpx.Request("POST", "https://api.example.com"))
        llm = self._mock_llm([
            httpx.HTTPStatusError("unauthorized", request=response_401.request, response=response_401),
        ])

        with pytest.raises(httpx.HTTPStatusError):
            invoke_with_retry(llm, [{"role": "user", "content": "hi"}])

        assert llm.invoke.call_count == 1  # no retry for 401
