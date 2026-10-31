"""Sarvam AI wrapper: STT (saaras:v3) and Chat Completion (sarvam-105b)."""
import io
import json
import os
import urllib.request

from sarvamai import SarvamAI

STT_MODEL = os.environ.get("SARVAM_STT_MODEL", "saaras:v3")
CHAT_MODEL = os.environ.get("SARVAM_CHAT_MODEL", "sarvam-105b-conversations")

_client = None


def client() -> SarvamAI:
    global _client
    if _client is None:
        api_key = os.environ.get("SARVAM_API_KEY")
        if not api_key:
            raise ValueError("SARVAM_API_KEY environment variable is not set")
        _client = SarvamAI(api_subscription_key=api_key)
    return _client


def transcribe(audio_bytes: bytes, filename: str = "call.wav") -> dict:
    """Short-audio (~<30s) sync transcription. Returns {"transcript": ..., "language_code": ...}."""
    file_obj = io.BytesIO(audio_bytes)
    file_obj.name = filename
    res = client().speech_to_text.transcribe(file=file_obj, model=STT_MODEL)
    return {
        "transcript": res.transcript,
        "language_code": getattr(res, "language_code", None),
    }


def chat_completion(prompt: str, max_tokens: int = 500, model: str | None = None) -> str:
    """Run chat completion with Sarvam AI using SDK or direct REST API."""
    target_model = model or CHAT_MODEL
    api_key = os.environ.get("SARVAM_API_KEY")
    if not api_key:
        raise ValueError("SARVAM_API_KEY environment variable is not set")

    # 1. Try SDK if available
    try:
        c = client()
        if hasattr(c, "chat") and callable(getattr(c.chat, "completions", None)):
            res = c.chat.completions(
                model=target_model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=0.2,
            )
            return res.choices[0].message.content.strip()
    except Exception:
        # Fall back to direct HTTP request
        pass

    # 2. Direct REST request to Sarvam chat completions endpoint
    url = "https://api.sarvam.ai/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "api-subscription-key": api_key,
    }
    payload = {
        "model": target_model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": max_tokens,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"].strip()
