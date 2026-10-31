"""AI logic for CallSense: classification and the AI Courtroom.

Primary provider: Sarvam AI (sarvam-105b)
Fallback provider: Anthropic Claude (Haiku for classification, Sonnet for courtroom)
"""
import json
import logging
import os

from anthropic import Anthropic
import sarvam_client

logger = logging.getLogger("callsense.ai")

SARVAM_CHAT_MODEL = os.environ.get("SARVAM_CHAT_MODEL", "sarvam-105b-conversations")
CLASSIFY_MODEL = os.environ.get("CLASSIFY_MODEL", "claude-haiku-4-5")
COURTROOM_MODEL = os.environ.get("COURTROOM_MODEL", "claude-sonnet-4-5")

_anthropic_client = None


def anthropic_client() -> Anthropic:
    global _anthropic_client
    if _anthropic_client is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable is not set")
        _anthropic_client = Anthropic(api_key=api_key)
    return _anthropic_client


def _call_llm(prompt: str, max_tokens: int, claude_model: str, expect_json: bool = False) -> str:
    """Execute LLM generation via Sarvam AI, with automatic fallback to Claude."""
    # 1. Attempt Primary: Sarvam AI
    if os.environ.get("SARVAM_API_KEY"):
        try:
            text = sarvam_client.chat_completion(
                prompt=prompt,
                max_tokens=max_tokens,
                model=SARVAM_CHAT_MODEL,
            )
            if expect_json:
                _parse_json(text)  # Ensure valid JSON output
            return text
        except Exception as exc:
            logger.warning(
                "Sarvam AI call failed or returned invalid output (%s). Falling back to Claude (%s).",
                exc,
                claude_model,
            )

    # 2. Fallback: Anthropic Claude
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError(
            "Primary provider (Sarvam AI) failed or is unconfigured, and ANTHROPIC_API_KEY is not set for fallback."
        )

    resp = anthropic_client().messages.create(
        model=claude_model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text.strip()


def classify_call(transcript: str, taxonomy: dict) -> dict:
    """Map a transcript to a Category::Subcategory from the taxonomy, plus a one-line summary."""
    taxonomy_text = "\n".join(
        f"- {cat}: {', '.join(subs)}" for cat, subs in taxonomy.items()
    )
    prompt = f"""You classify Paytm customer-support call transcripts (often Hindi/Hinglish/English mixed).

Allowed categories and subcategories:
{taxonomy_text}

Transcript:
\"\"\"{transcript}\"\"\"

Pick the single best-matching category and subcategory from the list above (use the exact
strings given, do not invent new ones unless truly nothing fits, in which case use category
"Other" and a short subcategory). Also write a one-sentence summary of the complaint.

Respond with ONLY compact JSON, no markdown fences:
{{"category": "...", "subcategory": "...", "summary": "..."}}"""

    text = _call_llm(
        prompt=prompt,
        max_tokens=300,
        claude_model=CLASSIFY_MODEL,
        expect_json=True,
    )
    return _parse_json(text)


def run_courtroom(transcript: str, category: str, subcategory: str) -> dict:
    """Advocate proposes a resolution, Challenger attacks it, Judge issues the final verdict."""

    advocate_prompt = f"""You are the Advocate in an AI Courtroom that resolves Paytm customer
support complaints. Complaint category: {category} :: {subcategory}.

Transcript:
\"\"\"{transcript}\"\"\"

Propose a clear, specific resolution for the customer and the steps Paytm support should take.
Keep it to 4-6 sentences."""
    advocate_text = _call_llm(
        prompt=advocate_prompt,
        max_tokens=500,
        claude_model=COURTROOM_MODEL,
        expect_json=False,
    )

    challenger_prompt = f"""You are the Challenger in an AI Courtroom. The Advocate proposed this
resolution for a Paytm complaint ({category} :: {subcategory}):

\"\"\"{advocate_text}\"\"\"

Original transcript:
\"\"\"{transcript}\"\"\"

Attack the proposal: point out anything risky, incomplete, non-compliant, or likely to upset
the customer or break policy (e.g. financial risk, fraud risk, missing verification steps).
Keep it to 3-5 sentences."""
    challenger_text = _call_llm(
        prompt=challenger_prompt,
        max_tokens=400,
        claude_model=COURTROOM_MODEL,
        expect_json=False,
    )

    judge_prompt = f"""You are the Judge in an AI Courtroom resolving a Paytm complaint
({category} :: {subcategory}).

Advocate's proposal:
\"\"\"{advocate_text}\"\"\"

Challenger's objections:
\"\"\"{challenger_text}\"\"\"

Weigh both sides and issue a final verdict: the resolution to give the customer, a risk_level
("low", "medium", or "high"), and whether this case must be escalated to a human agent
(true for anything involving fraud, account security, or money where you are not fully certain).

Respond with ONLY compact JSON, no markdown fences:
{{"verdict": "...", "risk_level": "low|medium|high", "escalate_to_human": true|false}}"""
    judge_text = _call_llm(
        prompt=judge_prompt,
        max_tokens=400,
        claude_model=COURTROOM_MODEL,
        expect_json=True,
    )
    judge_json = _parse_json(judge_text)

    return {
        "advocate_text": advocate_text,
        "challenger_text": challenger_text,
        "judge_text": judge_text,
        "verdict_text": judge_json.get("verdict", "").strip(),
        "risk_level": judge_json.get("risk_level", "medium"),
        "escalate_to_human": bool(judge_json.get("escalate_to_human", False)),
    }


def _parse_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"No JSON object found in model output: {text!r}")
    return json.loads(text[start:end + 1])
