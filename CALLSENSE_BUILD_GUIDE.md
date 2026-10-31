# CallSense — Build it yourself, from scratch

This guide is written so **you** create every file and every commit — I'm not touching your
git history, so nothing in here shows up as authored or co-authored by Claude. Read each
explanation, then create the file with the code under it.

---

## 0. Architecture (read this first)

```
Browser (phone/laptop) -> FastAPI backend -> SQLite
    record / upload audio   | Sarvam saaras:v3  (STT, visible in UI)
    dashboard + mind map    | Claude Haiku       (classify, hidden)
                             | Claude Sonnet x3   (AI Courtroom, hidden)
```

Flow for every call: **transcript → classify into Category::Subcategory → check if a
verdict already exists for that exact pair → if yes, return it instantly (cheap) → if no,
run the "AI Courtroom" (Advocate proposes a fix, Challenger attacks it, Judge issues the
final verdict) → store that verdict so the next identical complaint is free.**

Three DB tables do all the work:
- `calls` — a row per call: transcript, category, risk, whether it hit the cache or ran the courtroom.
- `verdicts` — one row per Category::Subcategory, the resolution, and a hit_count.
- `transcript_cache` — audio hash → transcript, so re-running the same clip never costs Sarvam credits twice.

---

## 1. Create the repo and folder structure

```bash
mkdir callsense
cd callsense
git init
git branch -m main
mkdir web
```

Go to [github.com/new](https://github.com/new), create an empty **public** repo named
`callsense` under your account (don't check README/.gitignore/license — avoids a conflict).
You'll push to it at the very end, once everything works.

---

## 2. Backend files

All of these live directly in the `callsense/backend folder (not inside `web/`).

### `taxonomy.json`

The list of Paytm complaint categories the classifier is allowed to choose from. Edit this
freely to add more categories for your demo.

```json
{
  "Failed Transactions": [
    "Bank server downtime",
    "UPI timeout",
    "Wallet debited but not credited",
    "Merchant not credited",
    "Transaction stuck in pending"
  ],
  "KYC": [
    "Document rejected",
    "Video KYC failed",
    "Limit not upgraded",
    "KYC pending for too long"
  ],
  "Fraud": [
    "Unauthorized transaction",
    "Account hacked",
    "Phishing SMS or link",
    "Fake customer care call"
  ],
  "Refunds": [
    "Refund delayed",
    "Refund not initiated",
    "Wrong amount refunded",
    "Refund credited to wrong account"
  ],
  "Recharge & Bill Payments": [
    "Recharge failed but amount deducted",
    "Bill payment not reflected",
    "Wrong plan activated",
    "Duplicate bill payment"
  ],
  "Account & Login": [
    "OTP not received",
    "App login failure",
    "Account locked",
    "Mobile number change request"
  ],
  "Merchant & QR": [
    "QR code not scanning",
    "Merchant payment not settled",
    "Soundbox not working",
    "Settlement delay to merchant bank account"
  ]
}
```

### `db.py`

All SQLite access lives here: creating the three tables, and small helper functions the API
calls. `insert_verdict` has a `UNIQUE(category, subcategory)` constraint — that's what makes
"has this exact problem been solved before?" a simple lookup.

```python
"""SQLite helpers for CallSense: calls, verdicts, transcript_cache."""
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

DB_PATH = "callsense.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    transcript TEXT NOT NULL,
    language_code TEXT,
    category TEXT NOT NULL,
    subcategory TEXT NOT NULL,
    summary TEXT,
    verdict_text TEXT,
    risk_level TEXT,
    escalate_to_human INTEGER DEFAULT 0,
    source TEXT NOT NULL,          -- 'courtroom' | 'cache'
    verdict_id INTEGER
);

CREATE TABLE IF NOT EXISTS verdicts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    subcategory TEXT NOT NULL,
    verdict_text TEXT NOT NULL,
    advocate_text TEXT,
    challenger_text TEXT,
    judge_text TEXT,
    risk_level TEXT,
    escalate_to_human INTEGER DEFAULT 0,
    hit_count INTEGER DEFAULT 1,
    created_at TEXT NOT NULL,
    UNIQUE(category, subcategory)
);

CREATE TABLE IF NOT EXISTS transcript_cache (
    audio_hash TEXT PRIMARY KEY,
    transcript TEXT NOT NULL,
    language_code TEXT,
    created_at TEXT NOT NULL
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)


def find_verdict(conn, category: str, subcategory: str):
    row = conn.execute(
        "SELECT * FROM verdicts WHERE category = ? AND subcategory = ?",
        (category, subcategory),
    ).fetchone()
    return row


def bump_verdict_hit(conn, verdict_id: int):
    conn.execute(
        "UPDATE verdicts SET hit_count = hit_count + 1 WHERE id = ?",
        (verdict_id,),
    )


def insert_verdict(conn, category, subcategory, verdict_text, advocate_text,
                    challenger_text, judge_text, risk_level, escalate_to_human):
    cur = conn.execute(
        """INSERT INTO verdicts
           (category, subcategory, verdict_text, advocate_text, challenger_text,
            judge_text, risk_level, escalate_to_human, hit_count, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?)""",
        (category, subcategory, verdict_text, advocate_text, challenger_text,
         judge_text, risk_level, int(escalate_to_human), now()),
    )
    return cur.lastrowid


def insert_call(conn, transcript, language_code, category, subcategory,
                 summary, verdict_text, risk_level, escalate_to_human, source, verdict_id):
    cur = conn.execute(
        """INSERT INTO calls
           (created_at, transcript, language_code, category, subcategory, summary,
            verdict_text, risk_level, escalate_to_human, source, verdict_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (now(), transcript, language_code, category, subcategory, summary,
         verdict_text, risk_level, int(escalate_to_human), source, verdict_id),
    )
    return cur.lastrowid


def get_cached_transcript(conn, audio_hash: str):
    row = conn.execute(
        "SELECT * FROM transcript_cache WHERE audio_hash = ?", (audio_hash,)
    ).fetchone()
    return row


def store_transcript_cache(conn, audio_hash, transcript, language_code):
    conn.execute(
        """INSERT OR REPLACE INTO transcript_cache (audio_hash, transcript, language_code, created_at)
           VALUES (?, ?, ?, ?)""",
        (audio_hash, transcript, language_code, now()),
    )


def reset_demo_data(conn):
    """Wipe calls and verdicts but keep the transcript cache (Sarvam credits already spent)."""
    conn.execute("DELETE FROM calls")
    conn.execute("DELETE FROM verdicts")
```

### `ai.py`

This is the two-part brain, both powered by Claude but never named in the UI:
- `classify_call` is one cheap call (Haiku) that runs on *every* call to pick a category.
- `run_courtroom` is three calls (Sonnet) that only run for a *new* category/subcategory —
  Advocate proposes, Challenger attacks, Judge decides. This is what gets skipped on a reuse.

```python
"""Claude-backed logic: classification (Haiku) and the AI Courtroom (Sonnet x3).

Branded "AI Courtroom" in the UI; never mention Claude/Anthropic to the user.
"""
import json
import os

from anthropic import Anthropic

CLASSIFY_MODEL = os.environ.get("CLASSIFY_MODEL", "claude-haiku-4-5")
COURTROOM_MODEL = os.environ.get("COURTROOM_MODEL", "claude-sonnet-4-5")

_client = None


def client() -> Anthropic:
    global _client
    if _client is None:
        _client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


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

    resp = client().messages.create(
        model=CLASSIFY_MODEL,
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    text = resp.content[0].text.strip()
    return _parse_json(text)


def run_courtroom(transcript: str, category: str, subcategory: str) -> dict:
    """Advocate proposes a resolution, Challenger attacks it, Judge issues the final verdict."""

    advocate_prompt = f"""You are the Advocate in an AI Courtroom that resolves Paytm customer
support complaints. Complaint category: {category} :: {subcategory}.

Transcript:
\"\"\"{transcript}\"\"\"

Propose a clear, specific resolution for the customer and the steps Paytm support should take.
Keep it to 4-6 sentences."""
    advocate_resp = client().messages.create(
        model=COURTROOM_MODEL, max_tokens=500,
        messages=[{"role": "user", "content": advocate_prompt}],
    )
    advocate_text = advocate_resp.content[0].text.strip()

    challenger_prompt = f"""You are the Challenger in an AI Courtroom. The Advocate proposed this
resolution for a Paytm complaint ({category} :: {subcategory}):

\"\"\"{advocate_text}\"\"\"

Original transcript:
\"\"\"{transcript}\"\"\"

Attack the proposal: point out anything risky, incomplete, non-compliant, or likely to upset
the customer or break policy (e.g. financial risk, fraud risk, missing verification steps).
Keep it to 3-5 sentences."""
    challenger_resp = client().messages.create(
        model=COURTROOM_MODEL, max_tokens=400,
        messages=[{"role": "user", "content": challenger_prompt}],
    )
    challenger_text = challenger_resp.content[0].text.strip()

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
    judge_resp = client().messages.create(
        model=COURTROOM_MODEL, max_tokens=400,
        messages=[{"role": "user", "content": judge_prompt}],
    )
    judge_text = judge_resp.content[0].text.strip()
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
```

### `sarvam_client.py`

Wraps the Sarvam SDK. This is the one piece you label "Transcribed by Sarvam AI" in the UI.

```python
"""Sarvam speech-to-text wrapper (visible in the UI as "Transcribed by Sarvam AI")."""
import io
import os

from sarvamai import SarvamAI

STT_MODEL = os.environ.get("SARVAM_STT_MODEL", "saaras:v3")

_client = None


def client() -> SarvamAI:
    global _client
    if _client is None:
        _client = SarvamAI(api_subscription_key=os.environ["SARVAM_API_KEY"])
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
```

### `app.py`

The FastAPI app that wires everything together: it loads `taxonomy.json`, exposes the API
routes, and runs the pipeline described in section 0 for every call (text or audio).

```python
"""CallSense backend: Browser -> FastAPI -> SQLite.

Pipeline: transcript -> category (Claude Haiku, hidden) -> verdict store check
-> AI Courtroom (Claude Sonnet x3, hidden) if new -> action + trend -> dashboard.
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

TAXONOMY = json.loads(Path("taxonomy.json").read_text(encoding="utf-8"))


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
```

### `requirements.txt`

```
fastapi
uvicorn[standard]
python-dotenv
python-multipart
anthropic
sarvamai
```

### `.env.example`

Copy this to `.env` and fill in your real keys — never commit `.env` itself.

```
ANTHROPIC_API_KEY=
SARVAM_API_KEY=

# Optional overrides
CLASSIFY_MODEL=claude-haiku-4-5
COURTROOM_MODEL=claude-sonnet-4-5
SARVAM_STT_MODEL=saaras:v3
```

### `.gitignore`

```
__pycache__/
*.pyc
venv/
.venv/
.env
callsense.db
node_modules/
dist/
.DS_Store
```

---

## 3. Scaffold the frontend

Run this from inside `callsense/` (it will fill the `web/` folder you already made):

```bash
npm create vite@latest web -- --template react
```

```bash
cd web
npm install
```

This generates `index.html`, `vite.config.js`, `package.json`, `src/main.jsx` — leave those
as they are. Now replace/add the files below inside `web/src/`.

### `web/.env.example`

```
VITE_API_BASE=http://localhost:8000
```

### `web/src/api.js`

Every network call the frontend makes goes through this one file.

```javascript
const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

async function request(path, options) {
  const res = await fetch(`${API_BASE}${path}`, options);
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}: ${text}`);
  }
  return res.json();
}

export function sendTextCall(transcript) {
  return request("/api/calls/text", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ transcript }),
  });
}

export function sendAudioCall(blob) {
  const form = new FormData();
  form.append("file", blob, "call.webm");
  return request("/api/calls", { method: "POST", body: form });
}

export function getDashboard() {
  return request("/api/dashboard");
}

export function getMindmap() {
  return request("/api/mindmap");
}

export function resetDemo() {
  return request("/api/reset", { method: "POST" });
}
```

### `web/src/screens/LiveCall.jsx`

The main demo screen: a record button (uses the browser's `MediaRecorder`), a text-input
fallback that skips Sarvam, and a result card that shows a "New problem: courtroom" or
"Reused verdict" badge plus tabs for the Advocate/Challenger/Judge transcript.

```jsx
import { useRef, useState } from "react";
import { sendAudioCall, sendTextCall } from "../api";

const TABS = ["advocate", "challenger", "judge"];

export default function LiveCall() {
  const [recording, setRecording] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);
  const [activeTab, setActiveTab] = useState("advocate");
  const [manualText, setManualText] = useState("");

  const mediaRecorderRef = useRef(null);
  const chunksRef = useRef([]);

  async function startRecording() {
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];
      recorder.ondataavailable = (e) => chunksRef.current.push(e.data);
      recorder.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(chunksRef.current, { type: "audio/webm" });
        submitAudio(blob);
      };
      recorder.start();
      mediaRecorderRef.current = recorder;
      setRecording(true);
    } catch (err) {
      setError(`Mic access failed: ${err.message}`);
    }
  }

  function stopRecording() {
    mediaRecorderRef.current?.stop();
    setRecording(false);
  }

  async function submitAudio(blob) {
    setBusy(true);
    setError(null);
    try {
      const data = await sendAudioCall(blob);
      setResult(data);
      setActiveTab("advocate");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function submitText() {
    if (!manualText.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const data = await sendTextCall(manualText.trim());
      setResult(data);
      setActiveTab("advocate");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="screen">
      <h2>Live Call</h2>

      <div className="card">
        <button
          className={recording ? "record-btn recording" : "record-btn"}
          onClick={recording ? stopRecording : startRecording}
          disabled={busy}
        >
          {recording ? "Stop recording" : "Start recording"}
        </button>

        <div className="manual-fallback">
          <textarea
            placeholder="...or paste/type a transcript (text endpoint, no Sarvam credits)"
            value={manualText}
            onChange={(e) => setManualText(e.target.value)}
            rows={3}
          />
          <button onClick={submitText} disabled={busy || !manualText.trim()}>
            Submit text
          </button>
        </div>

        {busy && <p className="status">Processing…</p>}
        {error && <p className="status error">{error}</p>}
      </div>

      {result && (
        <div className="card result">
          <div className="badge-row">
            <span className={`badge ${result.source}`}>
              {result.source === "cache" ? "Reused verdict" : "New problem: courtroom"}
            </span>
            <span className={`badge risk-${result.risk_level}`}>
              risk: {result.risk_level}
            </span>
            {result.escalate_to_human && (
              <span className="badge escalate">Escalate to human</span>
            )}
          </div>

          <p className="transcript">
            <strong>Transcribed by Sarvam AI{result.language_code ? ` (${result.language_code})` : ""}:</strong>{" "}
            {result.transcript}
          </p>

          <p className="category">
            {result.category} :: {result.subcategory}
          </p>
          <p className="summary">{result.summary}</p>

          <div className="verdict-card">
            <h3>Verdict</h3>
            <p>{result.verdict}</p>
          </div>

          {result.courtroom && (
            <div className="courtroom">
              <h3>AI Courtroom</h3>
              <div className="tabs">
                {TABS.map((tab) => (
                  <button
                    key={tab}
                    className={activeTab === tab ? "tab active" : "tab"}
                    onClick={() => setActiveTab(tab)}
                  >
                    {tab[0].toUpperCase() + tab.slice(1)}
                  </button>
                ))}
              </div>
              <p className="tab-content">{result.courtroom[activeTab]}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
```

### `web/src/screens/Dashboard.jsx`

Pulls `/api/dashboard` and renders tiles, a bar chart by category, risk split, recurring
issues, and a recent-calls table.

```jsx
import { useEffect, useState } from "react";
import { getDashboard } from "../api";

export default function Dashboard() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    load();
  }, []);

  function load() {
    setError(null);
    getDashboard().then(setData).catch((err) => setError(err.message));
  }

  if (error) return <div className="screen"><p className="status error">{error}</p></div>;
  if (!data) return <div className="screen"><p className="status">Loading…</p></div>;

  const maxCategoryCount = Math.max(1, ...data.by_category.map((c) => c.count));

  return (
    <div className="screen">
      <div className="dashboard-header">
        <h2>Dashboard</h2>
        <button onClick={load}>Refresh</button>
      </div>

      <div className="tiles">
        <Tile label="Total calls" value={data.total_calls} />
        <Tile label="Courtroom runs" value={data.courtroom_runs} />
        <Tile label="Reused verdicts" value={data.reused} />
        <Tile label="Courtroom calls saved" value={data.calls_saved} />
      </div>

      <div className="card">
        <h3>Complaints by category</h3>
        {data.by_category.length === 0 && <p className="status">No calls yet.</p>}
        {data.by_category.map((row) => (
          <div className="bar-row" key={row.category}>
            <span className="bar-label">{row.category}</span>
            <div className="bar-track">
              <div
                className="bar-fill"
                style={{ width: `${(row.count / maxCategoryCount) * 100}%` }}
              />
            </div>
            <span className="bar-count">{row.count}</span>
          </div>
        ))}
      </div>

      <div className="card">
        <h3>Risk split</h3>
        <div className="badge-row">
          {data.by_risk.map((row) => (
            <span className={`badge risk-${row.risk_level}`} key={row.risk_level}>
              {row.risk_level}: {row.count}
            </span>
          ))}
        </div>
      </div>

      <div className="card">
        <h3>Recurring issues</h3>
        {data.recurring_issues.length === 0 && <p className="status">None yet.</p>}
        <ul>
          {data.recurring_issues.map((row) => (
            <li key={`${row.category}-${row.subcategory}`}>
              {row.category} :: {row.subcategory} — {row.count} calls
            </li>
          ))}
        </ul>
      </div>

      <div className="card">
        <h3>Recent calls</h3>
        <table>
          <thead>
            <tr>
              <th>Time</th>
              <th>Category</th>
              <th>Risk</th>
              <th>Source</th>
            </tr>
          </thead>
          <tbody>
            {data.recent_calls.map((call) => (
              <tr key={call.id}>
                <td>{new Date(call.created_at).toLocaleTimeString()}</td>
                <td>{call.category} :: {call.subcategory}</td>
                <td>{call.risk_level}</td>
                <td>{call.source}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Tile({ label, value }) {
  return (
    <div className="tile">
      <div className="tile-value">{value}</div>
      <div className="tile-label">{label}</div>
    </div>
  );
}
```

### `web/src/screens/MindMap.jsx`

Pulls `/api/mindmap` (a category → subcategory tree with counts) and renders it as nested
boxes — no extra charting library needed.

```jsx
import { useEffect, useState } from "react";
import { getMindmap } from "../api";

export default function MindMap() {
  const [tree, setTree] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    load();
  }, []);

  function load() {
    setError(null);
    getMindmap().then(setTree).catch((err) => setError(err.message));
  }

  if (error) return <div className="screen"><p className="status error">{error}</p></div>;
  if (!tree) return <div className="screen"><p className="status">Loading…</p></div>;

  return (
    <div className="screen">
      <div className="dashboard-header">
        <h2>Mind Map</h2>
        <button onClick={load}>Refresh</button>
      </div>
      <div className="card mindmap">
        <MindMapNode node={tree} depth={0} />
      </div>
    </div>
  );
}

function MindMapNode({ node, depth }) {
  const isLeaf = !node.children;
  return (
    <div className={`mindmap-node depth-${depth}`}>
      <div className="mindmap-label">
        {node.name}
        {isLeaf && (
          <>
            {" "}
            <span className="badge">{node.count} call{node.count === 1 ? "" : "s"}</span>
            {node.reused_count > 0 && (
              <span className="badge cache">{node.reused_count} reused</span>
            )}
          </>
        )}
      </div>
      {node.children && node.children.length > 0 && (
        <div className="mindmap-children">
          {node.children.map((child) => (
            <MindMapNode node={child} depth={depth + 1} key={child.name} />
          ))}
        </div>
      )}
    </div>
  );
}
```

### `web/src/App.jsx`

Just a 3-button nav switching between the three screens above.

```jsx
import { useState } from "react";
import "./App.css";
import LiveCall from "./screens/LiveCall";
import Dashboard from "./screens/Dashboard";
import MindMap from "./screens/MindMap";

const SCREENS = {
  call: { label: "Live Call", component: LiveCall },
  dashboard: { label: "Dashboard", component: Dashboard },
  mindmap: { label: "Mind Map", component: MindMap },
};

function App() {
  const [screen, setScreen] = useState("call");
  const Active = SCREENS[screen].component;

  return (
    <div className="app">
      <header className="nav">
        <span className="brand">CallSense</span>
        <nav>
          {Object.entries(SCREENS).map(([key, { label }]) => (
            <button
              key={key}
              className={screen === key ? "nav-btn active" : "nav-btn"}
              onClick={() => setScreen(key)}
            >
              {label}
            </button>
          ))}
        </nav>
      </header>
      <main>
        <Active />
      </main>
    </div>
  );
}

export default App;
```

### `web/src/App.css`

All the styling — dark theme, badges, bars, tabs, the mind map tree.

```css
:root {
  --bg: #0f1115;
  --panel: #171a21;
  --border: #2a2f3a;
  --text: #e8eaed;
  --muted: #9aa3b2;
  --accent: #4c8bf5;
  --low: #2ea043;
  --medium: #d29922;
  --high: #f85149;
  color-scheme: dark;
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
}

.app {
  max-width: 900px;
  margin: 0 auto;
  min-height: 100vh;
}

.nav {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border);
}

.brand {
  font-weight: 700;
  font-size: 1.2rem;
}

.nav nav {
  display: flex;
  gap: 8px;
}

.nav-btn {
  background: transparent;
  border: 1px solid var(--border);
  color: var(--muted);
  padding: 8px 14px;
  border-radius: 8px;
  cursor: pointer;
}

.nav-btn.active {
  color: var(--text);
  border-color: var(--accent);
  background: rgba(76, 139, 245, 0.12);
}

.screen {
  padding: 20px;
}

.card {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 16px;
  margin-bottom: 16px;
}

button {
  font: inherit;
}

.record-btn {
  background: var(--accent);
  color: white;
  border: none;
  padding: 14px 24px;
  border-radius: 999px;
  font-size: 1rem;
  cursor: pointer;
}

.record-btn.recording {
  background: var(--high);
  animation: pulse 1.2s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.6; }
}

.manual-fallback {
  margin-top: 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.manual-fallback textarea {
  background: var(--bg);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px;
  resize: vertical;
}

.manual-fallback button {
  align-self: flex-start;
  background: var(--panel);
  border: 1px solid var(--border);
  color: var(--text);
  padding: 8px 14px;
  border-radius: 8px;
  cursor: pointer;
}

.status {
  color: var(--muted);
}

.status.error {
  color: var(--high);
}

.badge-row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}

.badge {
  display: inline-block;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 0.8rem;
  background: var(--border);
  color: var(--text);
}

.badge.courtroom {
  background: rgba(76, 139, 245, 0.2);
  color: var(--accent);
}

.badge.cache {
  background: rgba(46, 160, 67, 0.2);
  color: var(--low);
}

.badge.risk-low {
  background: rgba(46, 160, 67, 0.2);
  color: var(--low);
}

.badge.risk-medium {
  background: rgba(210, 153, 34, 0.2);
  color: var(--medium);
}

.badge.risk-high {
  background: rgba(248, 81, 73, 0.2);
  color: var(--high);
}

.badge.escalate {
  background: rgba(248, 81, 73, 0.25);
  color: var(--high);
}

.transcript {
  color: var(--muted);
}

.category {
  font-weight: 600;
  margin-bottom: 4px;
}

.verdict-card {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px;
  margin-top: 12px;
}

.courtroom {
  margin-top: 16px;
}

.tabs {
  display: flex;
  gap: 4px;
  margin-bottom: 8px;
}

.tab {
  background: transparent;
  border: 1px solid var(--border);
  color: var(--muted);
  padding: 6px 12px;
  border-radius: 6px;
  cursor: pointer;
}

.tab.active {
  color: var(--text);
  border-color: var(--accent);
}

.tab-content {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px;
  color: var(--muted);
}

.dashboard-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.dashboard-header button {
  background: var(--panel);
  border: 1px solid var(--border);
  color: var(--text);
  padding: 6px 14px;
  border-radius: 8px;
  cursor: pointer;
}

.tiles {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.tile {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 16px;
  text-align: center;
}

.tile-value {
  font-size: 1.8rem;
  font-weight: 700;
}

.tile-label {
  color: var(--muted);
  font-size: 0.85rem;
  margin-top: 4px;
}

.bar-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}

.bar-label {
  width: 180px;
  flex-shrink: 0;
  font-size: 0.9rem;
}

.bar-track {
  flex: 1;
  background: var(--bg);
  border-radius: 6px;
  height: 10px;
  overflow: hidden;
}

.bar-fill {
  background: var(--accent);
  height: 100%;
}

.bar-count {
  width: 28px;
  text-align: right;
  color: var(--muted);
}

table {
  width: 100%;
  border-collapse: collapse;
}

th, td {
  text-align: left;
  padding: 8px;
  border-bottom: 1px solid var(--border);
  font-size: 0.9rem;
}

th {
  color: var(--muted);
  font-weight: 500;
}

.mindmap-node {
  margin-bottom: 8px;
}

.mindmap-label {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 0;
}

.depth-0 > .mindmap-label {
  font-size: 1.1rem;
  font-weight: 700;
}

.depth-1 > .mindmap-label {
  font-weight: 600;
  color: var(--accent);
}

.depth-2 > .mindmap-label {
  color: var(--text);
}

.mindmap-children {
  margin-left: 20px;
  padding-left: 12px;
  border-left: 1px solid var(--border);
}
```

### `web/src/index.css`

Replace the generated one with this (App.css owns the theme):

```css
* {
  box-sizing: border-box;
}

body {
  margin: 0;
  font: 16px/145% system-ui, "Segoe UI", Roboto, sans-serif;
}

#root {
  min-height: 100svh;
}
```

Also delete `web/src/assets/react.svg`/`vite.svg` and `web/public/icons.svg` if you don't
want the default Vite logos (they aren't referenced by the files above).

---

## 4. Run it locally

**Terminal 1 — backend**, from `callsense/`:

```bash
python -m venv venv
```

```bash
venv\Scripts\activate
```

```bash
pip install -r requirements.txt
```

```bash
copy .env.example .env
```

Open `.env`, paste your `ANTHROPIC_API_KEY` (from console.anthropic.com — needs a few
dollars of credit, Claude Pro does not include API access) and `SARVAM_API_KEY` (from
dashboard.sarvam.ai, where your 500 hackathon credits live).

```bash
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

**Terminal 2 — frontend**, from `callsense/web/`:

```bash
copy .env.example .env
```

```bash
npm run dev
```

Open the URL it prints. Go to **Live Call**, use the text box with something like
`mera UPI payment fail ho gaya, bank server down bata raha hai` — expect
"New problem: courtroom". Submit a similar sentence again — expect "Reused verdict" instantly.

---

## 5. Commit and push — entirely as you

```bash
git add -A
```

```bash
git commit -m "CallSense: FastAPI + Sarvam STT + AI Courtroom, React frontend"
```

```bash
git remote add origin https://github.com/palakchandak8/callsense.git
```

```bash
git push -u origin main
```

Every commit here is authored by whatever identity `git config user.name`/`user.email` on
your machine resolve to — since you're the one running these commands, that's you, with
nothing from me in the message or the authorship.
