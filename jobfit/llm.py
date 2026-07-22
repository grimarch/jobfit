"""Provider-agnostic LLM client.

Routing (controlled via env vars):
  LLM_PROVIDER=anthropic     → Anthropic SDK,       key from LLM_API_KEY  (default)
  LLM_PROVIDER=openai-compat → OpenAI-compat SDK,   key from LLM_API_KEY, URL from LLM_BASE_URL

Per-command overrides (optional):
  CV_*           — CV generate + Anschreiben
  CV_EXTRACT_*   — CV profile extract (falls back to CV_* when unset)

Fallback (optional):
  LLM_FALLBACK_PROVIDER      → provider to use when primary fails (any non-200 / exception)
  LLM_FALLBACK_MODEL         → model for fallback (optional, uses provider default)
  LLM_FALLBACK_API_KEY       → API key for fallback (optional, falls back to LLM_API_KEY)
  LLM_FALLBACK_BASE_URL      → base URL for fallback openai-compat (required if FALLBACK_PROVIDER=openai-compat)
"""
from __future__ import annotations

import os
from typing import Any

import anthropic
from anthropic.types import TextBlock
from loguru import logger


def _prefix_chain(command_prefix: str | None) -> list[str]:
    if not command_prefix:
        return []
    if command_prefix == "CV_EXTRACT":
        return [command_prefix, "CV"]
    return [command_prefix]


def _first_env(names: list[str]) -> str:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


def _env_for_command(command_prefix: str | None, name: str) -> str:
    """Return command-specific env value, or empty string if unset."""
    if not command_prefix:
        return ""
    return os.environ.get(f"{command_prefix}_{name}", "").strip()


def resolve_provider(command_prefix: str | None = None) -> str:
    """Return provider: {PREFIX}_PROVIDER (with CV_EXTRACT → CV fallback) → LLM_PROVIDER."""
    names = [f"{prefix}_PROVIDER" for prefix in _prefix_chain(command_prefix)]
    return _first_env(names) or os.environ.get("LLM_PROVIDER", "anthropic")


def resolve_base_url(command_prefix: str | None = None) -> str:
    """Return base URL: {PREFIX}_BASE_URL (with CV_EXTRACT → CV fallback) → LLM_BASE_URL."""
    names = [f"{prefix}_BASE_URL" for prefix in _prefix_chain(command_prefix)]
    return _first_env(names) or os.environ.get("LLM_BASE_URL", "")


def resolve_model(command_var: str) -> str:
    """Return model name: command-specific var → LLM_MODEL → anthropic default.

    Raises RuntimeError if no model is configured for openai-compat provider.
    """
    model = os.environ.get(command_var) or os.environ.get("LLM_MODEL")
    if not model:
        provider = resolve_provider(command_var.removesuffix("_MODEL"))
        if provider == "anthropic":
            return "claude-haiku-4-5"
        raise RuntimeError(
            f"LLM_MODEL not set. Required when LLM_PROVIDER={provider!r}. "
            "Set LLM_MODEL in .env (or a command-specific override)."
        )
    return model


def resolve_key(fallback: str | None = None, command_prefix: str | None = None) -> str:
    """Return the API key for the configured provider. Raises RuntimeError if missing."""
    if fallback:
        return fallback
    names = [f"{prefix}_API_KEY" for prefix in _prefix_chain(command_prefix)]
    key = _first_env(names) or os.environ.get("LLM_API_KEY", "")
    provider = resolve_provider(command_prefix)
    if not key:
        if command_prefix:
            hint = " or ".join(names + ["LLM_API_KEY"])
            raise RuntimeError(
                f"{hint} not set. Required for provider={provider!r}."
            )
        raise RuntimeError(
            f"LLM_API_KEY not set. Required for LLM_PROVIDER={provider}. "
            "Copy .env.example to .env and set your key."
        )
    return key


def _resolve_fallback_provider(command_prefix: str | None) -> str:
    names = [f"{prefix}_FALLBACK_PROVIDER" for prefix in _prefix_chain(command_prefix)]
    return _first_env(names) or os.environ.get("LLM_FALLBACK_PROVIDER", "")


def _resolve_fallback_key(command_prefix: str | None) -> str:
    names = [
        *[f"{prefix}_FALLBACK_API_KEY" for prefix in _prefix_chain(command_prefix)],
        "LLM_FALLBACK_API_KEY",
        *[f"{prefix}_API_KEY" for prefix in _prefix_chain(command_prefix)],
        "LLM_API_KEY",
    ]
    return _first_env(names)


def _resolve_fallback_base_url(command_prefix: str | None) -> str:
    names = [f"{prefix}_FALLBACK_BASE_URL" for prefix in _prefix_chain(command_prefix)]
    return _first_env(names) or os.environ.get("LLM_FALLBACK_BASE_URL", "")


def ping(command_prefix: str | None = None) -> list[str]:
    """Verify connectivity and API key by listing available models (no tokens consumed)."""
    provider = resolve_provider(command_prefix)
    api_key = resolve_key(command_prefix=command_prefix)
    base_url = resolve_base_url(command_prefix)

    if provider == "anthropic":
        client = anthropic.Anthropic(api_key=api_key)
        return [m.id for m in client.models.list().data]

    if provider == "openai-compat":
        if not base_url:
            raise RuntimeError(
                "LLM_BASE_URL not set. Required when LLM_PROVIDER=openai-compat."
            )
        import openai
        client = openai.OpenAI(api_key=api_key, base_url=base_url, max_retries=0)
        return [m.id for m in client.models.list().data]

    raise RuntimeError(f"Unknown provider: {provider!r}")


def complete(
    messages: list[dict[str, str]],
    *,
    system: str,
    model: str,
    api_key: str,
    max_tokens: int = 8192,
    fallback_model_var: str | None = None,
    json_mode: bool = False,
    reasoning_effort: str | None = None,
    command_prefix: str | None = None,
) -> str:
    """Call configured LLM, return text response.

    On any exception from the primary provider, retries with the fallback provider
    if LLM_FALLBACK_PROVIDER is set. Raises if fallback also fails or is not configured.

    fallback_model_var: command-specific env var for fallback model
                        (e.g. "CLASSIFY_FALLBACK_MODEL"). Takes priority over
                        LLM_FALLBACK_MODEL when set.

    json_mode: request JSON object output (OpenAI-compat response_format).

    reasoning_effort: OpenAI-compat reasoning control (e.g. "none" for Gemini 2.5).
                      When omitted, auto-disables thinking for gemini-2.5/3 models,
                      or uses LLM_REASONING_EFFORT from the environment.

    command_prefix: optional env prefix for per-command provider routing (e.g. "CV").
    """
    provider = resolve_provider(command_prefix)
    base_url = resolve_base_url(command_prefix)

    try:
        return _dispatch(
            messages, system=system, model=model, api_key=api_key,
            provider=provider, base_url=base_url, max_tokens=max_tokens,
            json_mode=json_mode, reasoning_effort=reasoning_effort,
        )
    except Exception as primary_exc:
        fallback_provider = _resolve_fallback_provider(command_prefix)
        if not fallback_provider:
            raise

        fallback_model = (
            (os.environ.get(fallback_model_var) if fallback_model_var else None)
            or os.environ.get("LLM_FALLBACK_MODEL")
            or _provider_default_model(fallback_provider)
        )
        fallback_key = _resolve_fallback_key(command_prefix)
        fallback_base_url = _resolve_fallback_base_url(command_prefix)

        logger.warning(
            f"Primary LLM failed ({_fmt_exc(primary_exc)}), "
            f"switching to fallback: {fallback_provider}/{fallback_model}"
        )
        return _dispatch(
            messages, system=system, model=fallback_model, api_key=fallback_key,
            provider=fallback_provider, base_url=fallback_base_url, max_tokens=max_tokens,
            json_mode=json_mode, reasoning_effort=reasoning_effort,
        )


def _fmt_exc(exc: BaseException) -> str:
    """Return a short human-readable description of an LLM API exception."""
    status = getattr(exc, "status_code", None)
    if status:
        return f"{type(exc).__name__} {status}"
    return type(exc).__name__


def _provider_default_model(provider: str) -> str:
    if provider == "anthropic":
        return "claude-haiku-4-5"
    raise RuntimeError(
        f"LLM_FALLBACK_MODEL not set and no default for provider={provider!r}."
    )


def _default_reasoning_effort(model: str) -> str | None:
    """Gemini 2.5+ counts thinking tokens against max_tokens — disable by default."""
    if _is_gemini_model(model):
        return "none"
    return None


def _is_gemini_model(model: str) -> bool:
    name = model.lower()
    return "gemini-2.5" in name or "gemini-3" in name or "gemini2.5" in name


def _resolve_reasoning_effort(model: str, explicit: str | None) -> str | None:
    if explicit is not None:
        return explicit or None
    env = os.environ.get("LLM_REASONING_EFFORT", "").strip()
    if env:
        return env
    return _default_reasoning_effort(model)


def _dispatch(
    messages: list[dict[str, str]],
    *,
    system: str,
    model: str,
    api_key: str,
    provider: str,
    base_url: str,
    max_tokens: int,
    json_mode: bool = False,
    reasoning_effort: str | None = None,
) -> str:
    if provider == "openai-compat":
        if not base_url:
            raise RuntimeError(
                "LLM_BASE_URL not set. Required when LLM_PROVIDER=openai-compat."
            )
        return _complete_openai(
            messages, system=system, model=model, api_key=api_key,
            base_url=base_url, max_tokens=max_tokens,
            json_mode=json_mode, reasoning_effort=reasoning_effort,
        )
    if provider == "anthropic":
        return _complete_anthropic(
            messages, system=system, model=model, api_key=api_key, max_tokens=max_tokens,
        )
    raise RuntimeError(
        f"Unknown LLM provider={provider!r}. Valid values: anthropic, openai-compat."
    )


def _complete_anthropic(
    messages: list[dict[str, str]],
    *,
    system: str,
    model: str,
    api_key: str,
    max_tokens: int,
) -> str:
    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=messages,  # type: ignore[arg-type]
    )
    block = next((b for b in response.content if isinstance(b, TextBlock)), None)
    if block is None:
        raise TypeError(f"No TextBlock in response: {[type(b).__name__ for b in response.content]}")
    return block.text.strip()


def _complete_openai(
    messages: list[dict[str, str]],
    *,
    system: str,
    model: str,
    api_key: str,
    base_url: str,
    max_tokens: int,
    json_mode: bool = False,
    reasoning_effort: str | None = None,
) -> str:
    import openai
    client = openai.OpenAI(api_key=api_key, base_url=base_url, max_retries=0)
    full_messages: list[Any] = [{"role": "system", "content": system}, *messages]
    create_kwargs: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": full_messages,
    }
    if json_mode:
        create_kwargs["response_format"] = {"type": "json_object"}
    effort = _resolve_reasoning_effort(model, reasoning_effort)
    if effort:
        create_kwargs["reasoning_effort"] = effort
    response = client.chat.completions.create(**create_kwargs)
    choice = response.choices[0]
    content = (choice.message.content or "").strip()
    finish = getattr(choice, "finish_reason", None)
    if finish and finish != "stop" and len(content) < 200:
        logger.warning(
            f"LLM short response (finish_reason={finish!r}, len={len(content)}, model={model})"
        )
    return content
