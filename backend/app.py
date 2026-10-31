"""CallSense backend: Browser -> FastAPI -> SQLite.

Pipeline: transcript -> category (Sarvam AI / Claude fallback) -> verdict store check
-> AI Courtroom (Sarvam AI / Claude fallback) if new -> action + trend -> dashboard.
"""
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import ai
import db
import sarvam_client

app = FastAPI(title="CallSense API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

TAXONOMY_PATH = Path(__file__).parent / "taxonomy.json"
TAXONOMY = json.loads(TAXONOMY_PATH.read_text(encoding="utf-8"))


@app.on_event("startup")
def startup():
    db.init_db()


class TextCallIn(BaseModel):
    transcript: str
    language_code: str | None = None


def _convert_to_wav(raw_bytes: bytes, src_suffix: str) -> bytes:
    """Convert browser webm/ogg recordings to 16kHz mono wav via ffmpeg, if available."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return raw_bytes
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / f"in{src_suffix}"
        dst = Path(tmp) / "out.wav"
        src.write_bytes(raw_bytes)
        subprocess.run(
            [ffmpeg, "-y", "-i", str(src), "-ar", "16000", "-ac", "1", str(dst)],
            check=True, capture_output=True,
        )
        return dst.read_bytes()


def _resolve_verdict(conn, category: str, subcategory: str, transcript: str):
    """Look up a stored verdict for this category::subcategory, or run the AI Courtroom."""
    existing = db.find_verdict(conn, category, subcategory)
    if existing:
        db.bump_verdict_hit(conn, existing["id"])
        return {
            "source": "cache",
            "verdict_id": existing["id"],
            "verdict_text": existing["verdict_text"],
            "risk_level": existing["risk_level"],
            "escalate_to_human": bool(existing["escalate_to_human"]),
            "courtroom": None,
        }

    result = ai.run_courtroom(transcript, category, subcategory)
    verdict_id = db.insert_verdict(
        conn, category, subcategory,
        result["verdict_text"], result["advocate_text"],
        result["challenger_text"], result["judge_text"],
        result["risk_level"], result["escalate_to_human"],
    )
    return {
        "source": "courtroom",
        "verdict_id": verdict_id,
        "verdict_text": result["verdict_text"],
        "risk_level": result["risk_level"],
        "escalate_to_human": result["escalate_to_human"],
        "courtroom": {
            "advocate": result["advocate_text"],
            "challenger": result["challenger_text"],
            "judge": result["judge_text"],
        },
    }


def _handle_transcript(transcript: str, language_code: str | None):
    classification = ai.classify_call(transcript, TAXONOMY)
    category = classification["category"]
    subcategory = classification["subcategory"]
    summary = classification.get("summary", "")

    with db.get_conn() as conn:
        resolution = _resolve_verdict(conn, category, subcategory, transcript)
        call_id = db.insert_call(
            conn, transcript, language_code, category, subcategory, summary,
            resolution["verdict_text"], resolution["risk_level"],
            resolution["escalate_to_human"], resolution["source"],
            resolution["verdict_id"],
        )

    return {
        "call_id": call_id,
        "transcript": transcript,
        "language_code": language_code,
        "category": category,
        "subcategory": subcategory,
        "summary": summary,
        "verdict": resolution["verdict_text"],
        "risk_level": resolution["risk_level"],
        "escalate_to_human": resolution["escalate_to_human"],
        "source": resolution["source"],
        "courtroom": resolution["courtroom"],
    }


@app.post("/api/calls/text")
def post_call_text(body: TextCallIn):
    """Dev/demo path that skips Sarvam entirely (no credits spent)."""
    return _handle_transcript(body.transcript, body.language_code)


@app.post("/api/calls")
async def post_call_audio(file: UploadFile = File(...)):
    raw = await file.read()
    audio_hash = hashlib.sha256(raw).hexdigest()

    with db.get_conn() as conn:
        cached = db.get_cached_transcript(conn, audio_hash)

    if cached:
        transcript = cached["transcript"]
        language_code = cached["language_code"]
    else:
        suffix = Path(file.filename or "call.webm").suffix or ".webm"
        wav_bytes = _convert_to_wav(raw, suffix)
        try:
            stt = sarvam_client.transcribe(wav_bytes, filename="call.wav")
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Sarvam STT failed: {exc}") from exc
        transcript = stt["transcript"]
        language_code = stt["language_code"]
        with db.get_conn() as conn:
            db.store_transcript_cache(conn, audio_hash, transcript, language_code)

    return _handle_transcript(transcript, language_code)


@app.get("/api/dashboard")
def get_dashboard():
    with db.get_conn() as conn:
        total_calls = conn.execute("SELECT COUNT(*) c FROM calls").fetchone()["c"]
        courtroom_runs = conn.execute(
            "SELECT COUNT(*) c FROM calls WHERE source = 'courtroom'"
        ).fetchone()["c"]
        reused = conn.execute(
            "SELECT COUNT(*) c FROM calls WHERE source = 'cache'"
        ).fetchone()["c"]

        by_category = [
            dict(row) for row in conn.execute(
                "SELECT category, COUNT(*) count FROM calls GROUP BY category ORDER BY count DESC"
            ).fetchall()
        ]
        by_risk = [
            dict(row) for row in conn.execute(
                "SELECT risk_level, COUNT(*) count FROM calls GROUP BY risk_level"
            ).fetchall()
        ]
        recurring = [
            dict(row) for row in conn.execute(
                """SELECT category, subcategory, COUNT(*) count
                   FROM calls GROUP BY category, subcategory
                   HAVING count > 1 ORDER BY count DESC"""
            ).fetchall()
        ]
        recent = [
            dict(row) for row in conn.execute(
                """SELECT id, created_at, category, subcategory, summary, risk_level,
                          escalate_to_human, source
                   FROM calls ORDER BY id DESC LIMIT 20"""
            ).fetchall()
        ]

    return {
        "total_calls": total_calls,
        "courtroom_runs": courtroom_runs,
        "reused": reused,
        "calls_saved": reused,  # courtroom calls skipped thanks to the verdict store
        "by_category": by_category,
        "by_risk": by_risk,
        "recurring_issues": recurring,
        "recent_calls": recent,
    }


@app.get("/api/mindmap")
def get_mindmap():
    with db.get_conn() as conn:
        rows = conn.execute(
            """SELECT category, subcategory, COUNT(*) count,
                      SUM(CASE WHEN source = 'cache' THEN 1 ELSE 0 END) reused_count
               FROM calls GROUP BY category, subcategory"""
        ).fetchall()

    tree = {}
    for row in rows:
        cat = tree.setdefault(row["category"], {"name": row["category"], "children": []})
        cat["children"].append({
            "name": row["subcategory"],
            "count": row["count"],
            "reused_count": row["reused_count"],
        })

    return {"name": "Paytm Complaints", "children": list(tree.values())}


@app.get("/api/taxonomy")
def get_taxonomy():
    return TAXONOMY


@app.post("/api/reset")
def post_reset():
    """Wipe demo calls/verdicts; keep the transcript cache so re-running a clip is free."""
    with db.get_conn() as conn:
        db.reset_demo_data(conn)
    return {"status": "reset"}
