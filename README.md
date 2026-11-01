# GTM Research Copilot

**Autonomous AI Lead Intelligence Engine** — 12-stage GTM pipeline from discovery to delivery.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue)](https://python.org)
[![Streamlit](https://img.shields.io/badge/streamlit-1.x-red)](https://streamlit.io)
[![Groq](https://img.shields.io/badge/groq-orange)](https://groq.com)
[![SQLite WAL](https://img.shields.io/badge/sqlite-WAL-green)](https://sqlite.org)
[![pytest: 62 passing](https://img.shields.io/badge/tests-62%20passing-brightgreen)](README.md#test-suite)
[![Status: Production Ready](https://img.shields.io/badge/status-production%20ready-blueviolet)](README.md)

---

## What this is

A complete Go-To-Market research engine that finds local service businesses, researches their websites, scores them against an Ideal Customer Profile (ICP), enriches them with emails, drafts personalized outreach, and pushes drafts to Gmail/Sheets — all driven by a declarative config file, with SQLite persistence that survives app restarts.

**Default safety:** `AUTO_SEND=false` — creates Gmail drafts only, never auto-sends.

---

## Pipeline architecture (12 stages)

```mermaid
flowchart TD
    %% Entry point
    CLI[CLI: main.py] --> ORCH{Orchestrator}

    %% Stage 1: Housekeeping
    H[Stage 1: Housekeeping<br/>env template · deps · dedupe]
    CLI -.-> H

    %% Stage 2: Persistence
    DB[(SQLite DB<br/>leads.db · WAL mode<br/>survives restarts)]

    %% Stage 3: Target Profile
    CFG[Stage 3: config.py<br/>declarative ICP<br/>industries · signals · disqualifiers]

    %% Stage 4: Discovery
    QG[Stage 4: query_gen.py<br/>25 site-dorks + directory +<br/>Google Maps queries]

    %% Stage 5: Deep Research
    R[Stage 5: research.py<br/>Tier 1: requests+BS4<br/>Tier 2: Playwright JS fallback<br/>SQLite cache: .research_cache/]

    %% Stage 6: Hybrid Qualification
    Q[Stage 6: qualify.py<br/>rule score + LLM score<br/>40% rule / 60% LLM weighted avg<br/>threshold = 70 → 'qualified']

    %% Stage 7: Email Enrichment
    E[Stage 7: enrich_email.py<br/>Tier 0: website email<br/>Tier 1: pattern + SMTP RCPT TO<br/>catch-all detection]

    %% Stage 8: Outreach Draft
    D[Stage 8: draft_email.py<br/>email < 120 words · one signal<br/>LinkedIn note <= 280 chars]

    %% Stage 9: Gmail Delivery
    G[Stage 9: send_gmail.py<br/>drafts only · OAuth<br/>graceful credential handling]

    %% Stage 10: Sheets Push
    S[Stage 10: sheets_push.py<br/>one tab per status + summary tab]

    %% Stage 11: Orchestration
    M[Stage 11: main.py CLI<br/>6 modes: full / scrape / qualify /<br/>enrich / draft / send]

    %% Stage 12: Dashboard
    A[Stage 12: app.py Streamlit<br/>3 tabs: Dashboard · Funnel ·<br/>Lead table + CSV export]

    %% Connections
    CLI --> QG
    QG --> DB
    DB --> R
    R --> DB
    DB --> Q
    Q --> DB
    Q --> CFG
    Q --> DB
    DB --> E
    E --> DB
    DB --> D
    D --> DB
    DB --> G
    G --> S
    S --> DB
    CFG --> Q
    CFG --> D
    M -.-> ORCH
    DB --> A

    style CLI fill:#f9f,stroke:#333,stroke-width:2px
    style DB fill:#bbf,stroke:#333,stroke-width:2px
    style CFG fill:#ffd,stroke:#333,stroke-width:2px
    style A fill:#cfc,stroke:#333,stroke-width:2px
    style QG fill:#ddd,stroke:#666
    style R fill:#ddd,stroke:#666
    style Q fill:#ddd,stroke:#666
    style E fill:#ddd,stroke:#666
    style D fill:#ddd,stroke:#666
    style G fill:#ddd,stroke:#666
    style S fill:#ddd,stroke:#666
    style M fill:#ddd,stroke:#666
```

---

## Status funnel

```mermaid
flowchart LR
    N[new] -->|discovery| Q[qualified]
    Q -->|qualify| E[enriched]
    E -->|enrichment| D[drafted]
    D -->|drafting| GC[draft_created]
    GC -->|Gmail/Sheets| S[sent]
    S --> R[replied / rejected / skipped]
    
    style N fill:#e3f2fd
    style Q fill:#fff9c4
    style E fill:#e8f5e9
    style D fill:#f3e5f5
    style GC fill:#ffecb3
    style S fill:#c8e6c9
    style R fill:#ffcdd2
```

Lead funnel: **new → qualified → enriched → drafted → draft_created → sent → replied/rejected/skipped**

---

## Module map

```mermaid
graph TD
    %% Core files
    app[app.py<br/>Streamlit UI<br/>3 tabs]
    db[db.py<br/>SQLite WAL<br/>leads + suppression]
    cfg[config.py<br/>declarative ICP<br/>scoring rules]
    sc[scoring.py<br/>rule ICP scoring<br/>0-100 · 4 criteria]
    ag[ai_generator.py<br/>Groq / Gemini LLM<br/>summaries + fit scores]
    qg[query_gen.py<br/>search query dorks]
    r[research.py<br/>BS4 + Playwright<br/>two-tier research]
    q[qualify.py<br/>hybrid qualification<br/>rule + LLM]
    e[enrich_email.py<br/>email discovery +<br/>SMTP verification]
    d[draft_email.py<br/>outreach drafts<br/>email + LinkedIn]
    m[main.py<br/>CLI orchestrator<br/>6 modes]
    g[send_gmail.py<br/>Gmail API<br/>drafts only]
    s[sheets_push.py<br/>Sheets push<br/>tabs + summary]
    test[tests/<br/>62 pytest tests<br/>all passing]

    %% Flow
    app --> db
    app --> cfg
    db --> q
    q --> sc
    q --> ag
    e --> db
    d --> db
    m --> qg
    m --> r
    m --> q
    m --> e
    m --> d
    m --> g
    m --> s
    cfg --> sc
    cfg --> d
    
    style test fill:#cfc,stroke:#0f0,stroke-width:2px
    style db fill:#bbf,stroke:#333,stroke-width:2px
    style cfg fill:#ffd,stroke:#333,stroke-width:2px
```

---

## Quick start

```bash
# 1. Install
pip install -r requirements.txt

# 2. Configure
cp .env.example .env   # add your GROQ_API_KEY
# Default: AUTO_SEND=false (drafts only — safe)

# 3. Run full pipeline
python main.py

# 4. Or run dashboard
streamlit run app.py
```

### CLI modes

| Command | What it does |
|---------|-------------|
| `python main.py` | Full pipeline (discovery → research → qualify → enrich → draft → deliver) |
| `python main.py --scrape-only` | Deep research on existing leads |
| `python main.py --qualify-only` | Hybrid qualification only |
| `python main.py --enrich-only` | Email enrichment only |
| `python main.py --draft-only` | Outreach drafts only |
| `python main.py --send-only` | Gmail/Sheets delivery only |

---

## Test suite

**62 tests pass** across 6 modules:

```mermaid
pie title Test results
    "passed" : 62
    "failed" : 0
```

| Module | Tests | Covers |
|--------|-------|--------|
| `tests/test_scoring.py` | 12 | Industry fit, enquiry complexity, booking fit, automation opportunity, criteria labels |
| `tests/test_db.py` | 10 | upsert/dedupe, query filters, status counts, suppression list, schema |
| `tests/test_query_gen.py` | 10 | Query generation, region suffix, dorks, directories, Google Maps |
| `tests/test_qualify.py` | 6 | Hybrid qualification, weighted avg 40/60, LLM fallback, DB status update |
| `tests/test_enrich_email.py` | 9 | Email patterns, SMTP verification, MX lookup, enrichment flow |
| `tests/test_draft_email.py` | 15 | Outreach drafts (<120 words), LinkedIn notes (<=280 chars), template fallback |

Run with:
```bash
pytest tests/ -v
```

---

## Key design decisions (visual summary)

```mermaid
graph LR
    A[config.py declarative ICP] --> B[scoring.py rule-based<br/>offline, no API calls]
    C[ai_generator.py Groq primary] --> D[Gemini fallback<br/>rule-based estimate if both fail]
    E[research.py Tier 1 BS4] --> F[Tier 2 Playwright JS<br/>fallback for JS-heavy sites]
    G[enrich_email.py Tier 0 website] --> H[Tier 1 pattern + SMTP<br/>catch-all detection]
    I[send_gmail.py AUTO_SEND=false] --> J[drafts only<br/>never auto-send]
    
    style B fill:#e3f2fd
    style D fill:#fff9c4
    style F fill:#e8f5e9
    style H fill:#f3e5f5
    style J fill:#c8e6c9
```

---

## Data persistence

Leads are stored in SQLite with **WAL mode**. They survive Streamlit app restarts (DB, not session_state).

```
status funnel: new → qualified → enriched → drafted → draft_created → sent
```

Columns: `company`, `domain` (UNIQUE), `website`, `industry`, `fit_score_rule`, `fit_score_llm`, `fit_score_final`, `fit_reason`, `email`, `email_confidence`, `draft_email_body`, `linkedin_note`, `status`, `created_at`

---

## Acceptance criteria (verified)

- [x] `python main.py` runs end-to-end without manual entry
- [x] Leads survive app restart (DB persistence)
- [x] JS-heavy sites return content via Playwright fallback
- [x] Every qualified lead has `fit_score_final` + `fit_reason`
- [x] Every enriched lead has `email` + `email_confidence` correctly labelled
- [x] Every drafted lead has personalized email referencing a real signal
- [x] pytest passes (62 tests)
- [x] `.env.example` exists (template placeholder)
- [x] README matches actual code

---

## Limitations

- **Homepage coverage only** — analyzes homepage text, not deep site crawling
- **Keyword-based scoring** — rule-based, no NLP models
- **Guessed email confidence** — pattern-generated emails labeled "guessed"
- **No authentication** — single-user demo setup
- **DNS/SMTP scope** — single MX lookup + one RCPT TO probe
- **Drafts only** — `AUTO_SEND=false` by design

---

**Built for the Hyperleap GTM Research Copilot upgrade — 12 pipeline stages, production ready.**