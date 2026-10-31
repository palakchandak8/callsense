# CallSense

**Paytm Build for India AI Hackathon — team paytm_karo.**

CallSense listens to a customer-support call and turns it into action:

1. **Listen + transcribe** (Sarvam, visible in the UI): Hindi / Hinglish / English audio becomes text.
2. **Map**: Claude (hidden, background) maps the call to a Category and Subcategory of Paytm problems, e.g. `Failed Transactions -> Bank server downtime`.
3. **Verdict store check**: has this exact `Category::Subcategory` been solved before?
   - **Yes:** return the stored verdict instantly. No AI courtroom. Cheap and eco-friendly.
   - **No (new problem):** run the AI Courtroom (Advocate proposes, Challenger attacks, Judge issues the verdict), then store it.
4. **Actions + trend**: risk level, escalate-to-human flag, recurring issues.
5. **Dashboard**: complaints by category, risk, what the courtroom solved vs what was reused, savings, and a mind map of how problems are grouped.

## Architecture

```
Browser (phone/laptop)  ->  FastAPI backend  ->  SQLite

record / upload audio   |  Sarvam saaras:v3   (STT, visible)
dashboard + mind map    |  Claude Haiku       (classify, hidden)
                        |  Claude Sonnet x3   (courtroom, hidden)
```

DB tables (`backend/db.py`):

- `calls` — every call (transcript, category, subcategory, summary, risk, source = courtroom | cache).
- `verdicts` — one row per `Category::Subcategory` with the verdict, full courtroom transcript, hit_count.
- `transcript_cache` — audio hash -> transcript, so the same audio never costs Sarvam credits twice.

## Backend setup

```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # paste ANTHROPIC_API_KEY and SARVAM_API_KEY
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000/docs` to try the API.

Test without spending Sarvam credits:

```bash
curl -X POST http://localhost:8000/api/calls/text \
  -H "Content-Type: application/json" \
  -d '{"transcript": "mera UPI payment fail ho gaya, bank server down bata raha hai"}'
```

Send a similar transcript again and `source` should switch from `courtroom` to `cache`.

## Frontend setup

```bash
cd web
npm install
cp .env.example .env            # VITE_API_BASE, defaults to http://localhost:8000
npm run dev
```

Three screens:

- **Live Call** — record button + transcript + verdict card with a "New problem: courtroom" or "Reused verdict" badge.
- **Dashboard** — complaints, risk, courtroom vs reused, savings.
- **Mind Map** — how problems are grouped, with reuse counts.

## Demo script (60 seconds)

1. Phone 1 reports a new problem -> courtroom runs live -> verdict appears.
2. Phone 2 reports the same kind of problem -> verdict returns instantly with a "Reused verdict" badge.
3. Dashboard mind map shows the branch with reuse count.

## Known limits

- Matching is by `Category::Subcategory` chosen by the classifier. A production version would add embedding similarity for finer-grained reuse and a human review step for stored verdicts.
- Fraud/money cases should be escalated to humans; the Judge outputs an `escalate_to_human` flag for that.
- The sync Sarvam endpoint is for short audio (~30s). Longer files need the Batch API.