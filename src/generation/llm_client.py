"""
LLM client abstraction for the generation layer.

Design note (see docs/PRD.md Section 8, decision log item #6, and
docs/SOLUTION_CRITIQUE.md Section 2): the project's original free-tool
constraint pointed at Groq (Llama 3) or Google Gemini Flash. Both are
network-blocked in this build sandbox (only api.anthropic.com and package
registries are allow-listed — see docs/TRADE_OFFS.md Section 4), so neither
could be exercised end-to-end here. Nish confirmed using the Anthropic API
(Claude Haiku) instead: it's the one provider this sandbox can actually reach,
which means real generation + refusal-gate transcripts can be produced and
inspected in this environment rather than only unit-tested against a mock.

This module defines a small `LLMClient` protocol rather than hard-wiring the
Anthropic SDK everywhere, so:
  - tests can use `FakeLLMClient` (deterministic, no network, no API key) to
    exercise the refusal-gate logic in `refusal_gates.py` / `generate.py`
  - swapping providers later (e.g. adding Groq/Gemini back in for a
    cost comparison) means implementing this one interface, not rewriting
    the generation pipeline.
"""

from __future__ import annotations

import os
from typing import Protocol

from dotenv import load_dotenv


class LLMClient(Protocol):
    def complete(self, system: str, user: str) -> str:
        """Return the raw text completion for a given system + user prompt."""
        ...


class AnthropicClient:
    """Real LLM client backed by the Anthropic API.

    Requires ANTHROPIC_API_KEY to be set (e.g. via a local .env file — see
    .env.example). Not usable inside this build sandbox without that key
    (see module docstring); intended to be run from Nish's own machine, CI,
    or a deployed environment that has it configured.
    """

    def __init__(self, model: str = "claude-haiku-4-5", max_tokens: int = 1024, api_key: str | None = None):
        import anthropic  # imported lazily so the rest of the package works without the dependency installed

        # Bug found 2026-10-21: app.py calls load_dotenv() itself (Streamlit's entrypoint), but
        # any OTHER entrypoint that constructs AnthropicClient directly — eval/run_eval.py chief
        # among them — never did, so a real .env file sat there unread and this always raised
        # "ANTHROPIC_API_KEY is not set" even with a real key in .env. Loading it here, in the one
        # place that actually needs the variable, means every entrypoint gets it for free instead
        # of each one having to remember to call load_dotenv() itself. Safe to call repeatedly —
        # python-dotenv does not override a variable already set in the real environment.
        load_dotenv()
        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and fill it in, "
                "or export the variable before running generation for real."
            )
        self._client = anthropic.Anthropic(api_key=key)
        self.model = model
        self.max_tokens = max_tokens

    def complete(self, system: str, user: str) -> str:
        response = self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(block.text for block in response.content if getattr(block, "type", None) == "text")


class FakeLLMClient:
    """Deterministic stand-in for tests and for exercising the pipeline without
    an API key or network access. Construct with a fixed string, or a callable
    that inspects the prompts, so tests can control exactly what the "model"
    says and verify the refusal-gate logic reacts correctly."""

    def __init__(self, response):
        self._response = response
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        if callable(self._response):
            return self._response(system, user)
        return self._response
