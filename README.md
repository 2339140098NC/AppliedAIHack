# Proximate

Workspace for the Sapini matter. Firm users read a timeline, compare facts that disagree, and work validation findings. A provider view shows only that provider's own records.

PDFs are extracted in one Gemini call per file. Phone calls, emails, and notes come from Clio. Both land in a SQLite document store, and Python validations run against that store.

```mermaid
flowchart LR
  pdfs[Sapini PDFs] --> gemini[Gemini extract]
  clio[Clio Manage] --> sync[Communications sync]
  gemini --> store[(SQLite JSON store)]
  sync --> store
  store --> checks[Validations]
  checks --> board[Firm / provider workspace]
  store --> board
```

## Run it

Requires Python 3.12.

```bash
cd caseboard
cp .env.example .env
task install
task up
```

The board is at http://127.0.0.1:8765/. `task test` runs the validation tests.

If `task` is not installed, the same commands are:

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/uvicorn caseboard.main:app --host 127.0.0.1 --port 8765
```

## Configuration

Copy `caseboard/.env.example` to `caseboard/.env`. None of those values are committed.

| Variable | What it does |
|---|---|
| `GEMINI_API_KEY` | Used when **Extract PDFs** or **Sync Clio** sends a file URL to Gemini. The model is `gemini-3.8-flash`. |
| `CLIO_CLIENT_ID` / `CLIO_CLIENT_SECRET` | Clio Manage app key and secret. |
| `CLIO_REDIRECT_URI` | Must match the redirect registered on the Clio app, including port and path. The app accepts `/callback` and `/clio/callback`. |
| `CLIO_REGION_HOST` | `https://app.clio.com` for the US firm. |
| `CLIO_MATTER_ID` | Matter to sync. If empty, the sync looks for the one Justin Sapini matter. |
| `CORPUS_DIR` | Folder of PDFs. Leave it blank to use `../Sapini documents`. |

The Clio app needs read access for Matters, Communications, and Notes. Permissions are fixed when someone approves the app, so turn them on and click **Save** before connecting. If a token still cannot read data, remove the app under Clio's My integrations and connect again.

The process has to listen on the same host and port as `CLIO_REDIRECT_URI`. `task up` uses port 8765.

## What the board does

**Firm** is the default. Timeline, Evidence, and To-do are the three tabs. The page on the right is the cited PDF.

- **Sync Clio** stores phone calls, emails, notes, and messages, then compares Clio's PDF list to the PDFs already saved. It records new names and drops files Clio no longer has. It does not send files to Gemini, so the timeline shows up without waiting on extraction.
- **Extract PDFs** sends only new or updated files to Gemini by Clio's file URL. Unchanged files are left alone. **Extractions** opens the list of those files, shows when each was extracted, and can re-extract one file even when Clio's version has not changed. A schema or prompt change marks a finished file "Schema changed" once it has been extracted with an older stamp. Nothing is uploaded or kept.
- **Run validations** rebuilds the to-do list from the store. Checking an item off keeps that finding resolved if the same check comes back.

**Provider** drops the firm tabs, the action buttons, and anything marked firm-only. Pick Montefiore Nyack, Advanced Rockland Chiropractic, SportsCare, or New Horizon. That view only includes clinical records that belong to the selected provider.

## Layout

```
caseboard/
├── caseboard/          # FastAPI app, HTMX templates, extract / Clio / validations
├── tests/
├── design_handoff_case_workspace/   # visual spec for the workspace
├── .env.example
└── Taskfile.yml
```

The sample PDFs stay outside git, in `Sapini documents/` next to `caseboard/`.

## Deploy

Pushes to `main` on [AppliedAIHack](https://github.com/2339140098NC/AppliedAIHack) deploy through Vercel. The repo root `app.py` is the FastAPI entry. Vercel installs `requirements.txt`.

On Vercel the filesystem is read-only except `/tmp`. Case records and the Clio token live in Upstash Redis when `UPSTASH_REDIS_REST_URL` and `UPSTASH_REDIS_REST_TOKEN` are set, so a new instance keeps the timeline, the extracts, and the Clio login. The browser cookie still carries the token as a backup. Without those two variables the app falls back to the local SQLite file and `clio-token.json`. Set these in the Vercel project (Project → Settings → Environment Variables), using the same values as `caseboard/.env`:

| Variable | Production value |
|---|---|
| `GEMINI_API_KEY` | Same key as local. |
| `CLIO_CLIENT_ID` / `CLIO_CLIENT_SECRET` | Same app key and secret. |
| `CLIO_REDIRECT_URI` | `https://<your-project>.vercel.app/callback` |
| `CLIO_REGION_HOST` | `https://app.clio.com` |
| `CLIO_MATTER_ID` | `1811189963` |
| `UPSTASH_REDIS_REST_URL` / `UPSTASH_REDIS_REST_TOKEN` | From the Upstash Redis database (REST). |

Register that callback URL on the Clio app as well. If `CLIO_REDIRECT_URI` is left blank, the app uses `https://$VERCEL_PROJECT_PRODUCTION_URL/callback`.

Every Clio communication is firm-only. With Upstash configured, a new instance keeps the saved timeline and extracts. **Extract PDFs** is the slow step: the first run reads every file, and a later run only reads files Clio has changed. A pass longer than the function limit can be cut off; the next extract continues with the files that were saved.
