"""LLM narration layer. Narrates the scorer's structured output in plain
English — never scores, never invents a factor absent from the input
(verdict pipeline split, Approach A).

If ANTHROPIC_API_KEY is unset or the call fails, falls back to the raw
structured verdict rather than failing the whole request (the one
critical gap flagged in the Test Review: a narration failure must not
produce a silent wrong answer).
"""

from __future__ import annotations

import json
import os

SYSTEM_PROMPT = """You narrate a wildfire-insurability verdict for a real estate \
agent or title company. You are given a JSON object with a verdict, driving \
factors, and a mitigation list — narrate it in 3-5 plain-English sentences.

Rules, no exceptions:
- Only reference facts present in the JSON. Never invent a risk factor, \
mitigation, or cost that isn't in the input.
- Never claim this determines actual insurer underwriting, non-renewal, or \
pricing outcomes — the disclaimer field in the input already says this; \
reflect that caveat, don't soften or drop it.
- If verdict is "out_of_scope" or "low_confidence", say so plainly and explain \
why in one sentence — don't imply a hazard finding that isn't there.
- Lead with the verdict, then the top 1-2 driving factors, then the single \
most cost-effective mitigation if any are listed."""


def narrate(scorer_output: dict) -> str:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return _fallback_narration(scorer_output, reason="ANTHROPIC_API_KEY not set")

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": json.dumps(scorer_output)}],
        )
        text = "".join(
            block.text for block in response.content if block.type == "text"
        ).strip()
        return text or _fallback_narration(scorer_output, reason="empty LLM response")
    except Exception as exc:  # noqa: BLE001 — narration failure must degrade, not crash
        return _fallback_narration(scorer_output, reason=str(exc))


def _fallback_narration(scorer_output: dict, reason: str) -> str:
    """Plain-text rendering of the raw structured output. Used whenever the
    LLM path is unavailable or fails — the scorer's real answer must still
    reach the user, per the Test Review's one critical gap."""
    verdict = scorer_output.get("verdict", "unknown")
    factors = scorer_output.get("driving_factors", [])
    mitigations = scorer_output.get("mitigations", [])
    disclaimer = scorer_output.get("disclaimer", "")

    lines = [
        f"[Narration unavailable: {reason} — showing raw scorer output]",
        f"Verdict: {verdict}",
    ]
    if factors:
        lines.append("Driving factors: " + "; ".join(factors))
    if mitigations:
        top = mitigations[0]
        lines.append(f"Top mitigation action: {top['action']}")
    if disclaimer:
        lines.append(disclaimer)
    return "\n".join(lines)
