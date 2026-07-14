"""Unit tests for jobfit/llm.py — resolve_model(), resolve_key(), no_thinking."""

import pytest
from unittest.mock import MagicMock, patch


def env(**kwargs):
    """Patch os.environ with only the given keys (all others absent)."""
    return patch.dict("os.environ", kwargs, clear=True)


# ── resolve_model ─────────────────────────────────────────────────────────────

class TestResolveModel:
    def test_command_var_wins_over_llm_model(self):
        with env(CLASSIFY_MODEL="cmd-model", LLM_MODEL="global-model", LLM_PROVIDER="anthropic"):
            from jobfit.llm import resolve_model
            assert resolve_model("CLASSIFY_MODEL") == "cmd-model"

    def test_llm_model_used_when_command_var_absent(self):
        with env(LLM_MODEL="global-model", LLM_PROVIDER="anthropic"):
            from jobfit.llm import resolve_model
            assert resolve_model("CLASSIFY_MODEL") == "global-model"

    def test_anthropic_default_when_nothing_set(self):
        with env(LLM_PROVIDER="anthropic"):
            from jobfit.llm import resolve_model
            assert resolve_model("CLASSIFY_MODEL") == "claude-haiku-4-5"

    def test_anthropic_default_when_provider_absent(self):
        with env():
            from jobfit.llm import resolve_model
            assert resolve_model("CLASSIFY_MODEL") == "claude-haiku-4-5"

    def test_openai_compat_without_model_raises(self):
        with env(LLM_PROVIDER="openai-compat"):
            from jobfit.llm import resolve_model
            with pytest.raises(RuntimeError, match="LLM_MODEL not set"):
                resolve_model("CLASSIFY_MODEL")

    def test_openai_compat_with_llm_model_ok(self):
        with env(LLM_PROVIDER="openai-compat", LLM_MODEL="gemini-2.5-flash"):
            from jobfit.llm import resolve_model
            assert resolve_model("CLASSIFY_MODEL") == "gemini-2.5-flash"

    def test_openai_compat_with_command_var_ok(self):
        with env(LLM_PROVIDER="openai-compat", CLASSIFY_MODEL="gemini-2.5-flash"):
            from jobfit.llm import resolve_model
            assert resolve_model("CLASSIFY_MODEL") == "gemini-2.5-flash"

    def test_command_var_empty_string_falls_through_to_llm_model(self):
        # Empty string is falsy — should fall through to LLM_MODEL
        with env(CLASSIFY_MODEL="", LLM_MODEL="global-model", LLM_PROVIDER="anthropic"):
            from jobfit.llm import resolve_model
            assert resolve_model("CLASSIFY_MODEL") == "global-model"


# ── resolve_key ───────────────────────────────────────────────────────────────

class TestResolveKey:
    def test_returns_llm_api_key(self):
        with env(LLM_PROVIDER="anthropic", LLM_API_KEY="sk-test"):
            from jobfit.llm import resolve_key
            assert resolve_key() == "sk-test"

    def test_raises_when_no_key(self):
        with env(LLM_PROVIDER="anthropic"):
            from jobfit.llm import resolve_key
            with pytest.raises(RuntimeError, match="LLM_API_KEY not set"):
                resolve_key()

    def test_fallback_param_takes_priority(self):
        with env(LLM_PROVIDER="anthropic", LLM_API_KEY="from-env"):
            from jobfit.llm import resolve_key
            assert resolve_key("from-arg") == "from-arg"

    def test_openai_compat_returns_key(self):
        with env(LLM_PROVIDER="openai-compat", LLM_API_KEY="or-key"):
            from jobfit.llm import resolve_key
            assert resolve_key() == "or-key"

    def test_openai_compat_raises_when_no_key(self):
        with env(LLM_PROVIDER="openai-compat", LLM_BASE_URL="https://example.com"):
            from jobfit.llm import resolve_key
            with pytest.raises(RuntimeError, match="LLM_API_KEY not set"):
                resolve_key()


class TestResolveProvider:
    def test_global_provider_default(self):
        with env():
            from jobfit.llm import resolve_provider
            assert resolve_provider() == "anthropic"

    def test_global_provider_from_env(self):
        with env(LLM_PROVIDER="openai-compat"):
            from jobfit.llm import resolve_provider
            assert resolve_provider() == "openai-compat"

    def test_command_prefix_overrides_global(self):
        with env(LLM_PROVIDER="openai-compat", CV_PROVIDER="anthropic"):
            from jobfit.llm import resolve_provider
            assert resolve_provider("CV") == "anthropic"

    def test_command_prefix_falls_back_to_global(self):
        with env(LLM_PROVIDER="openai-compat"):
            from jobfit.llm import resolve_provider
            assert resolve_provider("CV") == "openai-compat"

    def test_cv_extract_inherits_cv_provider(self):
        with env(LLM_PROVIDER="openai-compat", CV_PROVIDER="anthropic"):
            from jobfit.llm import resolve_provider, resolve_key

            assert resolve_provider("CV_EXTRACT") == "anthropic"

    def test_cv_extract_uses_own_api_key_before_cv(self):
        with env(
            LLM_API_KEY="google-key",
            CV_PROVIDER="anthropic",
            CV_API_KEY="cv-key",
            CV_EXTRACT_API_KEY="extract-key",
        ):
            from jobfit.llm import resolve_key

            assert resolve_key(command_prefix="CV_EXTRACT") == "extract-key"

    def test_cv_extract_falls_back_to_cv_api_key(self):
        with env(
            LLM_API_KEY="google-key",
            CV_PROVIDER="anthropic",
            CV_API_KEY="cv-key",
        ):
            from jobfit.llm import resolve_key

            assert resolve_key(command_prefix="CV_EXTRACT") == "cv-key"


class TestResolveKeyCommandPrefix:
    def test_uses_command_api_key(self):
        with env(
            LLM_PROVIDER="openai-compat",
            LLM_API_KEY="google-key",
            CV_PROVIDER="anthropic",
            CV_API_KEY="anthropic-key",
        ):
            from jobfit.llm import resolve_key
            assert resolve_key(command_prefix="CV") == "anthropic-key"

    def test_falls_back_to_llm_api_key(self):
        with env(LLM_PROVIDER="anthropic", LLM_API_KEY="shared-key", CV_PROVIDER="anthropic"):
            from jobfit.llm import resolve_key
            assert resolve_key(command_prefix="CV") == "shared-key"

    def test_raises_with_command_prefix_hint(self):
        with env(LLM_PROVIDER="openai-compat", CV_PROVIDER="anthropic"):
            from jobfit.llm import resolve_key
            with pytest.raises(RuntimeError, match="CV_API_KEY or LLM_API_KEY not set"):
                resolve_key(command_prefix="CV")


class TestCVProviderRouting:
    def test_cv_generation_uses_anthropic_while_classify_uses_gemini(self):
        from anthropic.types import TextBlock

        mock_anthropic = MagicMock()
        block = TextBlock(type="text", text="ok")
        mock_anthropic.messages.create.return_value.content = [block]

        mock_openai = _make_openai_mock("ok")

        with env(
            LLM_PROVIDER="openai-compat",
            LLM_BASE_URL="https://generativelanguage.googleapis.com/v1beta/openai/",
            LLM_API_KEY="google-key",
            LLM_MODEL="gemini-2.5-flash",
            CV_PROVIDER="anthropic",
            CV_API_KEY="anthropic-key",
            CV_MODEL="claude-sonnet-4-6",
        ):
            with patch("openai.OpenAI", return_value=mock_openai) as openai_cls:
                with patch("anthropic.Anthropic", return_value=mock_anthropic) as anthropic_cls:
                    from jobfit.llm import complete

                    complete(
                        [{"role": "user", "content": "classify"}],
                        system="sys",
                        model="gemini-2.5-flash",
                        api_key="google-key",
                    )
                    complete(
                        [{"role": "user", "content": "cv"}],
                        system="sys",
                        model="claude-sonnet-4-6",
                        api_key="anthropic-key",
                        command_prefix="CV",
                    )

        openai_cls.assert_called_once()
        anthropic_cls.assert_called_once()
        assert openai_cls.call_args.kwargs["api_key"] == "google-key"
        assert anthropic_cls.call_args.kwargs["api_key"] == "anthropic-key"


# ── openai-compat call shape ──────────────────────────────────────────────────

def _make_openai_mock(text: str = "{}") -> MagicMock:
    choice = MagicMock()
    choice.message.content = text
    response = MagicMock()
    response.choices = [choice]
    client = MagicMock()
    client.chat.completions.create.return_value = response
    return client


class TestOpenAICompatCall:
    def _call(self, mock_client: MagicMock, **kwargs) -> dict:
        model = kwargs.pop("model", "gemini-2.5-flash")
        with env(LLM_PROVIDER="openai-compat", LLM_BASE_URL="https://example.com",
                 LLM_API_KEY="key", LLM_MODEL="gemini-2.5-flash"):
            with patch("openai.OpenAI", return_value=mock_client):
                from jobfit.llm import complete
                complete(
                    [{"role": "user", "content": "test"}],
                    system="sys",
                    model=model,
                    api_key="key",
                    **kwargs,
                )
        return mock_client.chat.completions.create.call_args.kwargs

    def test_no_extra_body_sent_for_non_gemini(self):
        kwargs = self._call(mock_client=_make_openai_mock(), model="gpt-4o-mini")
        assert "extra_body" not in kwargs

    def test_gemini_gets_thinking_disabled(self):
        kwargs = self._call(mock_client=_make_openai_mock(), model="gemini-2.5-flash")
        assert kwargs["reasoning_effort"] == "none"
        assert "extra_body" not in kwargs

    def test_json_mode_sets_response_format(self):
        kwargs = self._call(mock_client=_make_openai_mock(), json_mode=True)
        assert kwargs["response_format"] == {"type": "json_object"}

    def test_reasoning_effort_env_override(self):
        mock = _make_openai_mock()
        with env(LLM_PROVIDER="openai-compat", LLM_BASE_URL="https://example.com",
                 LLM_API_KEY="key", LLM_MODEL="gemini-2.5-flash",
                 LLM_REASONING_EFFORT="low"):
            with patch("openai.OpenAI", return_value=mock):
                from jobfit.llm import complete
                complete(
                    [{"role": "user", "content": "test"}],
                    system="sys", model="gemini-2.5-flash", api_key="key",
                )
        assert mock.chat.completions.create.call_args.kwargs["reasoning_effort"] == "low"
        assert "extra_body" not in mock.chat.completions.create.call_args.kwargs

    def test_empty_reasoning_effort_env_uses_gemini_default(self):
        mock = _make_openai_mock()
        with env(LLM_PROVIDER="openai-compat", LLM_BASE_URL="https://example.com",
                 LLM_API_KEY="key", LLM_MODEL="gemini-2.5-flash",
                 LLM_REASONING_EFFORT=""):
            with patch("openai.OpenAI", return_value=mock):
                from jobfit.llm import complete
                complete(
                    [{"role": "user", "content": "test"}],
                    system="sys", model="gemini-2.5-flash", api_key="key",
                )
        assert mock.chat.completions.create.call_args.kwargs["reasoning_effort"] == "none"

    def test_max_retries_zero(self):
        with env(LLM_PROVIDER="openai-compat", LLM_BASE_URL="https://example.com",
                 LLM_API_KEY="key", LLM_MODEL="gemini-2.5-flash"):
            with patch("openai.OpenAI", return_value=_make_openai_mock()) as mock_cls:
                from jobfit.llm import complete
                complete(
                    [{"role": "user", "content": "test"}],
                    system="sys", model="gemini-2.5-flash", api_key="key",
                )
        assert mock_cls.call_args.kwargs.get("max_retries") == 0

    def test_max_tokens_passed(self):
        kwargs = self._call(mock_client=_make_openai_mock(), max_tokens=3000)
        assert kwargs["max_tokens"] == 3000

    def test_anthropic_does_not_receive_extra_body(self):
        from anthropic.types import TextBlock
        mock_anthropic = MagicMock()
        block = TextBlock(type="text", text="{}")
        mock_anthropic.messages.create.return_value.content = [block]
        with env(LLM_PROVIDER="anthropic", LLM_API_KEY="key"):
            with patch("anthropic.Anthropic", return_value=mock_anthropic):
                from jobfit.llm import complete
                complete(
                    [{"role": "user", "content": "test"}],
                    system="sys",
                    model="claude-haiku-4-5",
                    api_key="key",
                )
        call_kwargs = mock_anthropic.messages.create.call_args.kwargs
        assert "extra_body" not in call_kwargs


# ── fallback ──────────────────────────────────────────────────────────────────

class TestFallback:
    def test_fallback_used_when_primary_fails(self):
        from anthropic.types import TextBlock
        mock_anthropic = MagicMock()
        block = TextBlock(type="text", text="ok")
        mock_anthropic.messages.create.return_value.content = [block]

        failing_client = MagicMock()
        failing_client.chat.completions.create.side_effect = RuntimeError("quota")

        with env(LLM_PROVIDER="openai-compat", LLM_BASE_URL="https://x.com",
                 LLM_API_KEY="key", LLM_MODEL="gemini-2.5-flash",
                 LLM_FALLBACK_PROVIDER="anthropic", LLM_FALLBACK_API_KEY="ant-key",
                 LLM_FALLBACK_MODEL="claude-haiku-4-5"):
            with patch("openai.OpenAI", return_value=failing_client):
                with patch("anthropic.Anthropic", return_value=mock_anthropic):
                    from jobfit.llm import complete
                    result = complete(
                        [{"role": "user", "content": "test"}],
                        system="sys", model="gemini-2.5-flash", api_key="key",
                    )
        assert result == "ok"
        mock_anthropic.messages.create.assert_called_once()

    def test_no_fallback_reraises(self):
        failing_client = MagicMock()
        failing_client.chat.completions.create.side_effect = RuntimeError("quota")

        with env(LLM_PROVIDER="openai-compat", LLM_BASE_URL="https://x.com",
                 LLM_API_KEY="key", LLM_MODEL="gemini-2.5-flash"):
            with patch("openai.OpenAI", return_value=failing_client):
                from jobfit.llm import complete
                with pytest.raises(RuntimeError, match="quota"):
                    complete(
                        [{"role": "user", "content": "test"}],
                        system="sys", model="gemini-2.5-flash", api_key="key",
                    )

    def test_fallback_uses_default_model_when_not_set(self):
        from anthropic.types import TextBlock
        mock_anthropic = MagicMock()
        block = TextBlock(type="text", text="ok")
        mock_anthropic.messages.create.return_value.content = [block]

        failing_client = MagicMock()
        failing_client.chat.completions.create.side_effect = RuntimeError("quota")

        with env(LLM_PROVIDER="openai-compat", LLM_BASE_URL="https://x.com",
                 LLM_API_KEY="key", LLM_MODEL="gemini-2.5-flash",
                 LLM_FALLBACK_PROVIDER="anthropic", LLM_FALLBACK_API_KEY="ant-key"):
            with patch("openai.OpenAI", return_value=failing_client):
                with patch("anthropic.Anthropic", return_value=mock_anthropic):
                    from jobfit.llm import complete
                    complete(
                        [{"role": "user", "content": "test"}],
                        system="sys", model="gemini-2.5-flash", api_key="key",
                    )
        call_kwargs = mock_anthropic.messages.create.call_args.kwargs
        assert call_kwargs["model"] == "claude-haiku-4-5"

    def test_fallback_model_var_takes_priority_over_llm_fallback_model(self):
        from anthropic.types import TextBlock
        mock_anthropic = MagicMock()
        block = TextBlock(type="text", text="ok")
        mock_anthropic.messages.create.return_value.content = [block]

        failing_client = MagicMock()
        failing_client.chat.completions.create.side_effect = RuntimeError("quota")

        with env(LLM_PROVIDER="openai-compat", LLM_BASE_URL="https://x.com",
                 LLM_API_KEY="key", LLM_MODEL="gemini-2.5-flash",
                 LLM_FALLBACK_PROVIDER="anthropic", LLM_FALLBACK_API_KEY="ant-key",
                 LLM_FALLBACK_MODEL="claude-haiku-4-5",
                 CLASSIFY_FALLBACK_MODEL="claude-sonnet-4-6"):
            with patch("openai.OpenAI", return_value=failing_client):
                with patch("anthropic.Anthropic", return_value=mock_anthropic):
                    from jobfit.llm import complete
                    complete(
                        [{"role": "user", "content": "test"}],
                        system="sys", model="gemini-2.5-flash", api_key="key",
                        fallback_model_var="CLASSIFY_FALLBACK_MODEL",
                    )
        call_kwargs = mock_anthropic.messages.create.call_args.kwargs
        assert call_kwargs["model"] == "claude-sonnet-4-6"
