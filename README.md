# CareerPilot AI — Agent

IBM SkillsBuild working model for the **CareerPilot AI** Lean Canvas (Team: DUO DYNAMICS).
This is the flagship feature from the pitch —built as a real, autonomous AI agent rather than a single prompt.

## Why this satisfies the "Working Model" requirement

| Requirement | How this meets it |
|---|---|
| Working AI agent that performs a useful task | Scores a resume against a real job description and returns a match score, keyword gaps, and rewritten bullet points |
| Autonomous, minimal manual intervention | One API call triggers a 4-step pipeline (Parse → Match → Generate → Self-review) with no human in the loop between steps |
| Any framework allowed | FastAPI + the Google Gemini API via the `google-genai` SDK (backend), React + Vite (frontend) |
| Vercel / Render / GitHub stack | Frontend → Vercel, Backend → Render, this repo → GitHub |

## How the agent works

```
job description ─▶ [1. PARSE, LLM]      structured requirements spec
                          │
resume text     ─▶ [2. MATCH, code]     deterministic keyword/section scoring
                          │
                    [3. GENERATE, LLM]   suggestions + rewritten bullets
                          │
                    [4. SELF-REVIEW, LLM] drops fabricated/vague suggestions
                          │
                          ▼
                    final JSON result
```

Step 2 is plain Python, not an LLM call — the match score needs to be the same
every time you re-run it on the same inputs. The LLM (Google Gemini) is used
only where it adds real value: reading messy unstructured text (step 1) and
writing tailored advice (steps 3–4).

## Project structure

```
careerpilot-agent/
├── backend/            FastAPI app + the agent (deploy to Render)
│   ├── agent.py         the 4-step pipeline (CareerPilotAgent class)
│   ├── main.py          API routes
│   ├── requirements.txt
│   └── render.yaml       one-click Render config
└── frontend/           React + Vite UI (deploy to Vercel)
    └── src/
        ├── App.jsx
        └── components/
            ├── ScoreGauge.jsx     cockpit-dial score visual
            └── KeywordChips.jsx
```

## Run it locally

### 1. Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# edit .env and paste your key from https://aistudio.google.com/apikey
uvicorn main:app --reload --port 8000
```

Test it's alive: `curl http://localhost:8000/health` → `{"status":"ok"}`

You can also test the agent directly without the API:
```bash
python agent.py
```

### 2. Frontend

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

Open the printed `localhost` URL, click **Load sample data**, then **Run CareerPilot Agent**.

## Deploying

### Backend → Render
1. Push this repo to GitHub.
2. On [Render](https://render.com): New → Web Service → connect the repo → root
   directory `backend`.
3. Render will pick up `render.yaml` automatically (or set manually):
   - Build command: `pip install -r requirements.txt`
   - Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
4. Add environment variable `GEMINI_API_KEY` (Render dashboard → Environment).
5. Once deployed, copy the Render URL (e.g. `https://careerpilot-ai-agent.onrender.com`).

### Frontend → Vercel
1. On [Vercel](https://vercel.com): New Project → import the same repo → root
   directory `frontend`.
2. Framework preset: Vite (auto-detected via `vercel.json`).
3. Add environment variable `VITE_API_URL` = your Render URL from above.
4. Deploy. Then go back to Render and set `ALLOWED_ORIGINS` to your Vercel URL
   so CORS allows it.

## Notes / next steps

- The model defaults to `gemini-2.5-flash` (cheap, fast, fine for a
  keyword-matching task). Swap `CAREERPILOT_MODEL` to a stronger Gemini model
  in Render's env vars if you want noticeably sharper rewritten bullets for a
  demo.
- Currently takes plain text input. If you want resume file upload (PDF/DOCX),
  that's a separate, well-scoped addition to `main.py` — say the word and I'll
  add it.
- This is one module from the full CareerPilot AI vision (planner, syllabus
  tracker, nudges, etc.) — deliberately scoped down to one working agent rather
  than ten half-built features, per the assignment's "working model" bar.
