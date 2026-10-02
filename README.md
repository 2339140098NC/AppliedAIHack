
# Proximate

### Evidence-aware AI workspace for complex case records

**Proximate** transforms fragmented case records into a structured,
source-linked workspace where teams can understand what happened,
identify conflicts, track unresolved work, and review evidence without
losing provenance.

> **Evidence → Timeline → Conflicts → Actions**

## 🚀 Live Demo

**Live application:**
https://appliedaihack.vercel.app/?view=firm&provider=sportscare&tab=timeline

**GitHub repository:** https://github.com/2339140098NC/AppliedAIHack

------------------------------------------------------------------------

## 🎯 The Problem

Complex cases contain PDFs, emails, phone calls, notes, medical records,
expert reports, billing records, and discovery communications.

The challenge is not simply finding information. Teams need to answer:

-   What actually happened?
-   When did it happen?
-   Which source supports the fact?
-   Do different records disagree?
-   What evidence is still missing?
-   What work is still unresolved?
-   What changed since the last review?

**Proximate turns fragmented records into a connected case workspace.**

------------------------------------------------------------------------

## 💡 What Proximate Does

Proximate combines document extraction, Clio communications, evidence
provenance, timeline intelligence, validation checks, and role-aware
views.

``` text
                 CASE RECORDS
                      │
          ┌───────────┴───────────┐
          │                       │
       PDFs                    Clio
          │               emails / calls /
          │                  notes
          └───────────┬───────────┘
                      ↓
             AI EXTRACTION
                      ↓
            STRUCTURED STORE
                      ↓
        ┌─────────────┼─────────────┐
        ↓             ↓             ↓
     Timeline      Evidence      Validations
        │             │             │
        └─────────────┼─────────────┘
                      ↓
              CASE WORKSPACE
                      ↓
             ACTIONABLE TO-DOS
```

The key design principle is **traceability**: generated or normalized
information remains connected to its underlying source.

------------------------------------------------------------------------

## ✨ Key Features

### 1. Unified Case Timeline

The Timeline combines:

-   Clio emails, phone calls, notes, and messages
-   PDF-derived events
-   Expert records
-   Discovery activity
-   Court activity
-   Insurance activity
-   Surgery / treatment events
-   Billing activity

The current live case displays **44 events for 2026**, including Clio
activity and document-backed events.

### 2. Evidence & Source Provenance

Evidence can retain:

-   Document name
-   Page number
-   Source type
-   Provider
-   Clio communication
-   Firm-only visibility

PDF-derived events can point back to the relevant document page.

### 3. Conflict Detection

The live workspace currently surfaces findings such as:

-   Addresses disagree
-   Location disagrees
-   Scene report says no injury
-   Defense exam contradicts treatment
-   Two index numbers
-   Expert report has two dates
-   Date of birth is blank
-   Imagers missing from HIPAA
-   Documents named but missing

Conflicts are surfaced for human review rather than silently resolved.

### 4. Validation → To-Do Workflow

Python validations run against the structured document store.

``` text
Structured evidence
       ↓
Validation checks
       ↓
Finding
       ↓
To-do
       ↓
Human review
       ↓
Resolved
```

Running validations rebuilds the To-do list from the current case state.
A checked-off finding remains resolved if the same validation finding
appears again.

### 5. Firm View

The Firm workspace provides the full case picture:

-   Overview
-   Timeline
-   Evidence
-   To-do items
-   Extractions
-   Validation controls
-   Clio communications
-   Firm-only information

The current case dashboard includes **31 PDFs, 361 pages, 9 treating
providers, 15 to-dos, and 11 critical to-dos**.

### 6. Provider View

Provider mode limits the workspace to records belonging to the selected
provider.

Supported provider examples include:

-   Montefiore Nyack
-   Advanced Rockland Chiropractic
-   SportsCare
-   New Horizon

Provider view removes firm-only controls and limits the visible clinical
record to the selected provider's information.

### 7. Clio Synchronization

Proximate can synchronize:

-   Phone calls
-   Emails
-   Notes
-   Messages

The synchronization compares Clio's PDF list with PDFs already stored by
the application. This lets the Timeline update without waiting for full
PDF extraction.

### 8. Incremental PDF Extraction

PDF extraction uses Gemini. Only new or updated files are sent for
extraction. Unchanged files are left alone.

The application also tracks extraction state and can identify when a
schema or prompt change requires re-extraction.

------------------------------------------------------------------------

## 🧠 AI + Deterministic Architecture

Proximate separates AI extraction from deterministic validation.

**AI is used for:** - Extracting structured information from PDFs -
Converting unstructured documents into usable case data - Identifying
events and evidence for the workspace

**Application logic is used for:** - Persistence - Validation checks -
Case state - To-do state - Provider filtering - Source tracking -
Incremental extraction decisions

``` text
AI extracts evidence
        ↓
Application stores evidence
        ↓
Rules validate the evidence
        ↓
Human reviews findings
```

------------------------------------------------------------------------

## 🏗️ Architecture

``` text
                    ┌──────────────────────┐
                    │       Clio Manage    │
                    │ emails / calls /     │
                    │ notes / messages     │
                    └──────────┬───────────┘
                               │
                               ↓
┌───────────────┐      ┌───────────────────┐
│ Case PDFs     │ ───→ │ Gemini Extraction │
└───────────────┘      └─────────┬─────────┘
                                 │
                                 ↓
                       ┌──────────────────┐
                       │ Document Store   │
                       │ SQLite / JSON    │
                       └────────┬─────────┘
                                │
              ┌─────────────────┼─────────────────┐
              ↓                 ↓                 ↓
        ┌──────────┐      ┌───────────┐     ┌────────────┐
        │ Timeline │      │ Evidence  │     │ Validation │
        └────┬─────┘      └─────┬─────┘     └──────┬─────┘
             │                  │                  │
             └──────────────────┼──────────────────┘
                                ↓
                     ┌────────────────────┐
                     │ Case Workspace     │
                     │ Firm / Provider    │
                     └────────────────────┘
```

------------------------------------------------------------------------

## 🛠️ Technology Stack

  Layer                    Technology
  ------------------------ ------------------------------
  Backend                  FastAPI
  AI extraction            Google Gemini / Google GenAI
  PDF processing           PyMuPDF
  Data validation          Python
  Data modeling            Pydantic
  Frontend interaction     HTMX + Jinja2
  Local persistence        SQLite / JSON
  Production persistence   Upstash Redis
  HTTP / integrations      HTTPX
  Server                   Uvicorn
  Deployment               Vercel
  Testing                  Pytest

The repository targets **Python 3.12+**.

------------------------------------------------------------------------

## 📁 Repository Structure

``` text
AppliedAIHack/
├── caseboard/
│   ├── caseboard/                     # FastAPI application
│   ├── tests/                         # Validation tests
│   ├── design_handoff_case_workspace/ # Workspace visual specification
│   ├── .env.example
│   ├── pyproject.toml
│   └── Taskfile.yml
├── app.py                             # Vercel FastAPI entrypoint
├── requirements.txt
├── vercel.json
└── README.md
```

Sample case PDFs are kept outside Git.

------------------------------------------------------------------------

## ⚙️ Run Locally

### Requirements

-   Python 3.12+
-   Gemini API key
-   Clio Manage credentials if using Clio synchronization
-   Task (optional)

### Clone

``` bash
git clone https://github.com/2339140098NC/AppliedAIHack.git
cd AppliedAIHack
```

### Enter the application

``` bash
cd caseboard
```

### Configure environment

``` bash
cp .env.example .env
```

Configure the required environment variables.

### Install

With Task:

``` bash
task install
```

Without Task:

``` bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

### Run

With Task:

``` bash
task up
```

Without Task:

``` bash
.venv/bin/uvicorn caseboard.main:app --host 127.0.0.1 --port 8765
```

Open `http://127.0.0.1:8765/`.

------------------------------------------------------------------------

## 🧪 Testing

Run:

``` bash
task test
```

or:

``` bash
.venv/bin/pytest
```

------------------------------------------------------------------------

## 🔐 Configuration

Important environment variables:

  Variable                     Purpose
  ---------------------------- ----------------------------
  `GEMINI_API_KEY`             Gemini PDF extraction
  `CLIO_CLIENT_ID`             Clio application client ID
  `CLIO_CLIENT_SECRET`         Clio application secret
  `CLIO_REDIRECT_URI`          OAuth callback URL
  `CLIO_REGION_HOST`           Clio region / host
  `CLIO_MATTER_ID`             Matter to synchronize
  `CORPUS_DIR`                 PDF corpus location
  `UPSTASH_REDIS_REST_URL`     Production Redis URL
  `UPSTASH_REDIS_REST_TOKEN`   Production Redis token

**Never commit credentials or `.env` files.**

------------------------------------------------------------------------

## ☁️ Deployment

The application is deployed on Vercel.

The repository uses `app.py` as the Vercel FastAPI entry point and
installs production dependencies from `requirements.txt`.

For production persistence, Upstash Redis stores case records and the
Clio token so application instances can retain timeline, extraction, and
authentication state.

------------------------------------------------------------------------

## 🔭 Future Roadmap

### Evidence Intelligence

-   Semantic search across the case
-   Citation-backed natural-language questions
-   Evidence confidence and source quality indicators
-   Evidence graph connecting facts, sources, providers, dates, and
    treatments

### Timeline Intelligence

-   Automatic event clustering
-   Chronology generation
-   Timeline anomaly detection
-   "What changed since last review?"
-   Gap detection in treatment and case activity

### Validation

-   More cross-document consistency checks
-   Temporal consistency checks
-   Missing-evidence detection
-   Provider / treatment consistency checks
-   Duplicate and stale-record detection
-   Configurable validation rules

### Workflow Automation

-   Deadline and obligation detection
-   Automatic task creation
-   Follow-up reminders
-   Outstanding discovery tracking
-   Provider follow-up workflows

### AI-Assisted Case Work

-   Citation-backed case chronology
-   Medical chronology
-   Evidence summaries
-   Review checklists
-   Document request drafts
-   Case-review briefing generation

### Platform

-   Multi-matter support
-   Multi-tenant architecture
-   Role-based access control
-   Document-level permissions
-   Audit logs
-   Enterprise security controls

------------------------------------------------------------------------

## 🌟 Why Proximate?

Most AI document tools focus on:

> **"Summarize this document."**

Proximate focuses on:

> **"Connect the evidence, understand the timeline, surface what
> conflicts, and show what needs attention."**

The goal is not to replace human review. The goal is to make human
review **faster, more traceable, and more actionable**.

------------------------------------------------------------------------

## 🎬 Demo Flow

Open the live Timeline:

https://appliedaihack.vercel.app/?view=firm&provider=sportscare&tab=timeline

Recommended demo:

1.  Open the case overview.
2.  Show PDFs, pages, providers, and to-dos.
3.  Open **Timeline**.
4.  Show Clio events alongside document-backed events.
5.  Open a conflict and trace it to its source.
6.  Switch to **Provider** view.
7.  Show provider-specific visibility.
8.  Open **To-do** and show validation findings.
9.  Run validations.
10. Show how resolved findings persist.

------------------------------------------------------------------------

## 📌 Project Status

**Working prototype / hackathon project**

The current implementation demonstrates evidence ingestion, timeline
construction, validation, provenance, incremental extraction, and
role-aware workspace concepts.

Production deployment would require additional security, privacy,
access-control, reliability, and compliance hardening.

------------------------------------------------------------------------

## 📄 License

No license has currently been specified for this repository.
