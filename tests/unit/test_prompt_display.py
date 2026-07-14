"""Unit tests for jobfit.prompt_display."""

import io
import textwrap

from jobfit.prompt_display import (
    estimate_tokens,
    print_llm_prompt,
    split_prompt_sections,
)

_SAMPLE_USER = textwrap.dedent("""\
    ## JOB CONTEXT

    Position:      DevOps Engineer
    Company:       Example GmbH

    ## JOB DESCRIPTION

    We are looking for a **DevOps Engineer**.

    ## CANDIDATE CV (source of truth — do not add anything not present here)

    [CANDIDATE_NAME]
    DevOps Engineer – [WORK_COMP_1]

    ## CANDIDATE PROFILE (structured metadata)

    {
      "experience_years": 5
    }
""")


def test_split_prompt_sections() -> None:
    sections = dict(split_prompt_sections(_SAMPLE_USER))
    assert sections["JOB CONTEXT"].startswith("Position:")
    assert "DevOps Engineer" in sections["JOB DESCRIPTION"]
    assert (
        "[WORK_COMP_1]"
        in sections[
            "CANDIDATE CV (source of truth — do not add anything not present here)"
        ]
    )
    assert (
        '"experience_years": 5' in sections["CANDIDATE PROFILE (structured metadata)"]
    )


def test_estimate_tokens() -> None:
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("a" * 400) == 100


def test_print_llm_prompt_plain_mode(capsys) -> None:
    print_llm_prompt(
        system="SYSTEM RULES",
        user=_SAMPLE_USER,
        refnr="10001-TEST-S",
        doc_label="CV generate",
        model="claude-sonnet-4-6",
        provider="anthropic",
    )
    captured = capsys.readouterr().out
    assert "CV generate" in captured
    assert "10001-TEST-S" in captured
    assert "--- SYSTEM ---" in captured
    assert "SYSTEM RULES" in captured
    assert "## JOB CONTEXT" in captured
    assert "[WORK_COMP_1]" in captured


def test_print_llm_prompt_rich_mode() -> None:

    from rich.console import Console

    from jobfit.prompt_display import _print_rich_prompt

    buffer = io.StringIO()
    console = Console(file=buffer, width=120, force_terminal=True)
    _print_rich_prompt(
        system="SYSTEM RULES",
        user=_SAMPLE_USER,
        refnr="10001-TEST-S",
        doc_label="CV generate",
        model="claude-sonnet-4-6",
        provider="anthropic",
        console=console,
    )
    output = buffer.getvalue()
    assert "LLM Prompt Preview" in output
    assert "SYSTEM RULES" in output
    assert "JOB CONTEXT" in output
