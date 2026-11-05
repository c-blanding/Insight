# Insight AI Agent

Insight AI Agent is a LangGraph application that takes a URL and a bug description, plans how to reproduce the issue in a real browser, runs that plan through Playwright MCP, and produces a structured QA report. Browser reproduction stays grounded in browser evidence. When a GitHub repository and immutable commit SHA are supplied, an optional read-only diagnosis stage inspects source code and adds likely cause locations to the report; it does not modify code.

Evidence (screenshots, video, console/network/snapshot logs, timeline events) and a full run summary (plan, findings, timeline, report) can be persisted to Neon Postgres and Object Storage via SQLAlchemy when configured.

**Programmatic entry point:** [`InsightAgent`](src/insightai/agent.py) (`arun` / `acontinue`).  
**Studio entry point:** graph id `insightaiagent` via [`insightaiagent_graph.py`](src/insightai/insightaiagent_graph.py).  
**FastAPI integration notes:** [`docs/FASTAPI_HANDOFF.md`](docs/FASTAPI_HANDOFF.md).  
**MVP scope and deployment assumptions:** [`docs/PRODUCT_SCOPE.md`](docs/PRODUCT_SCOPE.md).

## Pipeline

The main graph **`insightaiagent`** flow:

1. **Create plan** — LLM outputs a structured `Plan`: ordered steps that are browser interactions only (aligned with Playwright MCP tools).
2. **Execute plan** — A tool-using agent connects to Playwright MCP, opens the URL, works through plan steps, and returns `StepFindings` per step (with screenshots, console/network/snapshot logs, and timeline events). Loops until all steps complete.
3. **Assess browser evidence** — LLM determines the browser verdict from `step_findings`, optional `expected_behavior`, timeline, and plan completion.
4. **Diagnose source (optional)** — When `github_repo` and `github_commit_sha` are supplied, a read-only GitHub MCP toolset inspects likely source locations at that commit. The browser verdict remains authoritative.
5. **Finalize report** — LLM combines the browser assessment and optional source hypotheses into a `Report`, then upserts a `runs` row.

Optional side path: if a step hits a login wall (`auth_expired`), **wait_for_login** interrupts for Continue, saves the session, then returns to **execute_plan**. Most runs never enter that node.

```text
START
  │
  ▼
create_plan
  │
  ▼
execute_plan ◄──────────────┐
  │                         │
  ├── more steps ───────────┘
  │
  ├── auth_expired only ──► wait_for_login ──► execute_plan
  │                         (interrupt → Continue)
  │
  └── done / error
        │
        ▼
  assess_browser
        │
        ├── GitHub context ──► diagnose_source
        │                         │
        └── no GitHub ────────────┤
                                  ▼
                          finalize_report ──► Report + runs upsert
        │
        ▼
       END
```

## Graphs

Registered in `langgraph.json`:

| Graph ID | Module | Use |
|----------|--------|-----|
| `insightaiagent` | `src/insightai/insightaiagent_graph.py` | End-to-end plan → execute → report |
| `create_plan` | `src/insightai/create_plan.py` | Plan generation only |
| `execute_plan` | `src/insightai/execute_plan.py` | Execution with conditional loop until complete |

## Programmatic API (`InsightAgent`)

Prefer this over calling the raw Studio `graph` from application code. The class validates input, assigns a `thread_id`, uses a checkpointer (default in-memory) so login interrupts can resume, and returns typed outcomes.

```python
from insightai import InsightAgent, NeedsLogin

agent = InsightAgent()

async def main():
    outcome = await agent.arun({
        "url": "http://localhost:5500/products.html",
        "bug_description": "Searching for mug returns no products",
        "expected_behavior": "Search matches product names case-insensitively",
        "max_tools_turns": 30,
    })
    if isinstance(outcome, NeedsLogin):
        # Sign in in the headed Playwright window, then:
        outcome = await agent.acontinue(outcome.thread_id)
    print(outcome.report)
```

| Method | Role |
|--------|------|
| `arun(state, *, thread_id=None, timeout=None)` | Run the full pipeline (async) |
| `acontinue(thread_id, *, cancel=False)` | Resume after a login wall |
| `astream(state, ...)` | Yield LangGraph progress chunks |
| `get_timeline(thread_id)` / `get_run(thread_id)` | Load persisted evidence / run row |
| `run` / `continue_after_login` | Sync wrappers — **do not** use inside FastAPI/uvicorn |

Outcomes:

- **`NeedsLogin`** — paused for human Continue (`thread_id`, `message`, `login_url`, `origin`, `auth_profile_id`)
- **`InsightResult`** — terminal state (`report`, `plan`, `step_findings`, `timeline`, `error`, `completed`, `ok`)

Terminal results expose `run_status` (`completed`, `failed`, `cancelled`, or `unknown`),
`evidence_status` (`available`, `partial`, `unavailable`, or `unknown`), and a report
`verdict` (`bug_confirmed`, `not_reproduced`, or `inconclusive`). The verdict is based
on browser evidence; infrastructure failure is represented separately by `error`.

Never put passwords, cookies, or storage-state JSON in `arun` / `acontinue` payloads — validation rejects those keys.

> **Production note:** default checkpointer is `MemorySaver`. Multi-worker or durable login resume needs a shared LangGraph checkpointer (e.g. Postgres). See the FastAPI handoff.

## Inputs and state

Typical Studio or `InsightAgent.arun` input (`CreateGraphState`):

```json
{
  "url": "http://localhost:5500/products.html",
  "bug_description": "Searching for mug returns no products",
  "expected_behavior": "Search matches product names case-insensitively",
  "max_tools_turns": 30
}
```

| Field | Role |
|-------|------|
| `url` | Application under test (required, absolute `http(s)` URL) |
| `bug_description` | What is going wrong (required) |
| `expected_behavior` | Optional; used when writing the final report |
| `auth_profile_id` | Optional name of a saved browser session. The password is not an input. |
| `max_tools_turns` | Budget for tool use during a step (default 30, max 200) |
| `github_repo` | Optional GitHub repository in `owner/name` format for source diagnosis. |
| `github_commit_sha` | Required with `github_repo`; immutable 40- or 64-character commit SHA for source inspection. |

`thread_id` is **not** graph state — pass it to `arun(..., thread_id=...)` (or let the agent generate one). It keys evidence, Playwright session reuse, and DB rows.

Important runtime fields: `plan`, `current_step`, `step_findings` (append-only list), `completed`, `error`, `report`, `timeline`.

State typing lives in `src/insightai/utils/states.py`:

| TypedDict | Role |
|-----------|------|
| `CreateGraphState` | Caller input to `create_plan` / `arun` |
| `InsightGraphState` | Full LangGraph channel (superset) |
| `ExecutionState` | Execute / loop fields |
| `ReportState` | Inputs to `finalize_report` (report is output-only) |

Domain models live in `src/insightai/utils/objects.py`:

| Model | Role |
|-------|------|
| `Plan`, `Steps`, `StepFindings`, `ArtifactRef` | Plan + per-step findings / media refs |
| `BrowserAssessment` | Browser-only verdict and evidence summary |
| `SourceDiagnosis`, `SourceCandidate` | Optional commit-pinned code hypotheses |
| `Report` | Final QA write-up with optional source diagnosis |
| `Timeline`, `TimelineEvent`, … | Merged timeline / action-log view |
| `Run` | Persisted run summary (inputs + plan + findings + timeline + report) |

## Repository layout

```text
InsightAIAgent/
├── langgraph.json
├── pyproject.toml
├── neon.ts                     # Neon config (Auth, Object Storage buckets)
├── .env.example
├── docs/
│   └── FASTAPI_HANDOFF.md      # Backend API integration guide
├── scripts/
│   └── start-playwright-mcp.bat
├── src/
│   ├── insightai/              # installable Python package
│   │   ├── agent.py            # InsightAgent (programmatic API)
│   │   ├── insightaiagent_graph.py
│   │   ├── create_plan.py
│   │   ├── execute_plan.py
│   │   ├── runtime_paths.py
│   │   ├── auth/               # encrypted session store + capture CLI
│   │   ├── db/                 # SQLAlchemy models, Database helper, schema SQL
│   │   ├── evidence/           # session, capture, uploads, timeline, save_run
│   │   ├── mcp_clients/playwright.py
│   │   └── utils/              # nodes, prompts, states, edges, model, logging
│   ├── api/                    # FastAPI service (WIP)
│   ├── web/                    # Frontend (WIP)
│   └── test_web/               # LumenShop demo storefront (optional QA target)
└── README.md
```

Import the package after `uv sync`:

```python
from insightai import InsightAgent, NeedsLogin
```

Playwright integration: `PlaywrightMCP` talks to `http://localhost:8931/mcp` (or `PLAYWRIGHT_MCP_URL`), sanitizes tool schemas for OpenAI, and keeps cookie/storage/evaluate tools off the model tool list.

### Optional GitHub source diagnosis

Provide both `github_repo` (`owner/name`) and `github_commit_sha` to an `InsightAgent` run to enable post-reproduction source diagnosis. Configure `GITHUB_MCP_URL` to an HTTPS GitHub MCP endpoint (HTTP is allowed only on loopback) exposing `get_repository`, `search_code`, `get_commit`, and `get_file_contents` with the expected repository and revision fields. `GITHUB_MCP_TOKEN` is optional and is used only for MCP authentication; credential-like agent input keys are rejected, and the token is never placed in graph state or sent to the model. The agent exposes only this allowlisted read-only toolset, caps tool output, pins file reads and commit lookups to the supplied SHA, and only retains candidate paths and line ranges verified from file responses. Code search results are discovery hints and must be verified by reading the file at that SHA. If GitHub MCP is unavailable or the source revision cannot be verified, browser findings and verdict still return with the diagnosis marked unavailable or mismatched.

## Requirements

- Docker Desktop (recommended, with Docker Compose), or for local development: `uv` and Node.js ≥ 20
- OpenAI API key
- Neon Postgres (`DATABASE_URL`) — optional; enables persisted runs, logs, timelines, and auth sessions
- Optional: Neon Object Storage (`AWS_*` S3-compatible vars) for screenshot/video uploads
- Optional: LangSmith for tracing

## Quick start (Docker Desktop)

This is the recommended path for a fresh checkout. It runs the graph server and browser MCP in separate containers.

```powershell
git clone https://github.com/c-blanding/InsightAIAgent.git
cd InsightAIAgent
Copy-Item .env.example .env
# Edit .env and set OPENAI_API_KEY. DATABASE_URL is optional.
docker compose up --build
```

Open [LangSmith Studio connected to the local server](https://smith.langchain.com/studio/?baseUrl=http://localhost:2024) and sign in if prompted. Studio is the web UI; the graph server itself is running locally in Docker. Stop the services with `Ctrl+C` or `docker compose down`.

`DATABASE_URL` is optional. Without it, the agent can run but run summaries, logs, timelines, and saved auth sessions are not persisted. `AWS_*` object-storage values are also optional; configure them with `DATABASE_URL` to durably upload screenshots and video. Neon tables are created on first use.

## Local development setup (Windows PowerShell)

Requirements: `uv` and Node.js 20 or newer. Python 3.12 is selected by `.python-version` and installed by uv when needed. Run the bootstrap script from the repository root:

```powershell
.\scripts\setup.ps1
```

The script creates `.env` from `.env.example` only when `.env` does not already exist, then installs the locked Python dependencies with `uv sync`. Set `OPENAI_API_KEY` in `.env` before starting the agent. Add `DATABASE_URL` if you want persistent run data. Keep `.env` private; it is ignored by Git.

#### Install with pip instead of uv

`uv` is recommended because it installs from `uv.lock`, but pip can install the project from `pyproject.toml`. With Python 3.12 and Node.js 20 or newer installed, run:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Set `OPENAI_API_KEY` in `.env`, then verify the actual entry point imports:

```powershell
python -c "import insightai.main; print('Main module import OK')"
```

The pip install uses the dependency version ranges in `pyproject.toml`; it does not enforce the exact versions recorded in `uv.lock`. The `scripts/setup.ps1` helper currently uses uv, so follow these commands directly when setting up with pip.

Start Playwright MCP in one terminal and leave it running:

```powershell
.\scripts\start-playwright-mcp.bat
```

In a second terminal, start LangGraph Studio:

```powershell
# uv setup
uv run langgraph dev

# pip setup (activate the .venv first in this terminal)
langgraph dev
```

`--caps=devtools` is required for video. Without it, `browser_start_video` is missing
and runs continue with no recording. For hosted / sidecar deploys set `PLAYWRIGHT_MCP_URL`
to the MCP HTTP URL and point both processes at the same absolute `INSIGHT_MEDIA_DIR`
(and Neon `DATABASE_URL` / `AWS_*` for durable evidence). Local files under
`.playwright-mcp` are removed when the graph finishes and uploads succeed.

Browser target policy checks the scheme, embedded credentials, hostname, port, and
all DNS answers before planning and immediately before `browser_navigate`. Public
targets must be listed in `INSIGHT_ALLOWED_TARGET_HOSTS`. Non-public IP destinations
are rejected unless their exact hostname is listed in `INSIGHT_LOCAL_TARGETS`. DNS is
rechecked on each explicit navigation. Browser-level redirects are not yet blocked
before Chromium follows them. This is a known limitation of the local, human-supervised
MVP; run it only against applications you are authorized to test. Revisit network-level
redirect enforcement before supporting hosted runs against untrusted targets. Per-run
execution defaults to 15 minutes, MCP calls to 60 seconds, and local evidence to 512 MiB;
these limits are configurable in `.env.example`.

Open the Studio URL printed by `langgraph dev` (it normally opens automatically; the URL connects the Studio web app to the local server on port 2024), sign in if prompted, and invoke the `insightaiagent` graph. `--caps=devtools` is enabled for video capture. The browser MCP process uses the pinned `@playwright/mcp` version in `scripts/start-playwright-mcp.bat`; update that version intentionally when upgrading the integration.

### Local setup checks

From the repository root, these commands check the Python package import and graph CLI availability without starting a run:

```powershell
# uv setup
uv run python -c "from insightai import InsightAgent; print('InsightAgent import OK')"
uv run python -c "import insightai.main; print('Main module import OK')"
uv run langgraph --help

# pip setup (activate .venv first)
python -c "import insightai.main; print('Main module import OK')"
langgraph --help

node --version
```

If startup reports a missing `OPENAI_API_KEY`, fill it in `.env`. Add `DATABASE_URL` if you want persistence. Other optional settings for auth sessions, Object Storage, and tracing are documented in `.env.example`.

### Optional browser cursor overlay

To display an animated pointer and click pulse in the local browser and recordings, set this before starting the MCP process:

```powershell
$env:INSIGHT_SHOW_BROWSER_CURSOR = "1"
.\scripts\start-playwright-mcp.bat
```

Remove the setting to disable it:

```powershell
Remove-Item Env:INSIGHT_SHOW_BROWSER_CURSOR
```

### Manual Playwright MCP start

If you do not use the Windows helper script, start the pinned package directly:

```powershell
npx --yes @playwright/mcp@0.0.84 --port 8931 --caps=storage,devtools --isolated --output-dir .playwright-mcp
```

For hosted / sidecar deployments set `PLAYWRIGHT_MCP_URL` to the reachable MCP HTTP URL and point both processes at the same absolute `INSIGHT_MEDIA_DIR`.

## Docker Compose (private development deployment)

Compose runs the LangGraph dev server and Playwright MCP as separate containers. MCP is only reachable inside the Compose network; the graph API is bound to localhost on port 2024. Configure `.env` as in the quick start, then run:

```powershell
docker compose up --build
```

Open [LangSmith Studio connected to the local server](https://smith.langchain.com/studio/?baseUrl=http://localhost:2024) and sign in if prompted. Stop the stack with `docker compose down`. The `media` volume is temporary run staging; it is not the durable artifact store. To remove the volume too, run:

```powershell
docker compose down -v
```

That deletes any staged media that has not been uploaded.

This Compose setup uses `langgraph dev` and is for local or private evaluation. It does not add user authentication or tenant authorization, so do not expose port 2024 publicly as a multiuser service. A public deployment needs an authenticated API, user-scoped run access, and a production job/checkpointing strategy.

## First run with the demo storefront

In a third terminal, serve the included LumenShop sample app:

```powershell
python -m http.server 5500 --directory src/test_web
```

In Studio, submit a URL such as `http://host.docker.internal:5500/products.html` when running with Docker Compose, or `http://localhost:5500/products.html` for local development, plus a bug description. See `src/test_web/README.md` for sample scenarios.

To run the included `src/insightai/main.py` entry point directly, start the local Playwright MCP helper and demo storefront in separate terminals, then run:

```powershell
# uv setup
uv run python -m insightai.main

# pip setup (activate .venv first)
python -m insightai.main
```

This entry point targets `http://localhost:5500/rewards.html`. It needs `OPENAI_API_KEY`, the Playwright MCP server at `http://localhost:8931/mcp`, and the demo storefront at port 5500. `DATABASE_URL` is optional.

## Troubleshooting first setup

- **`uv` is not recognized:** install uv and restart PowerShell so its PATH is refreshed.
- **Node is missing or too old:** install Node.js 20 or newer; the local Playwright MCP helper uses `npx`.
- **Missing API key:** set `OPENAI_API_KEY` in `.env`; `DATABASE_URL` is optional. Do not paste credentials into graph input.
- **Playwright MCP is unreachable:** keep the MCP terminal open, then retry the graph; the default endpoint is `http://localhost:8931/mcp`.
- **Docker cannot reach the demo site:** use `host.docker.internal` in the URL from the graph container.

## Database (SQLAlchemy + Neon)

Connection and CRUD live in `src/insightai/db/`:

```python
from insightai.db import get_database, Run
from insightai.utils.objects import Run as RunModel  # pydantic summary

db = get_database()       # DATABASE_URL (pooled OK)
db.create_tables()        # idempotent; prefer DATABASE_URL_UNPOOLED for first DDL

db.upsert_run(...)
db.insert_run_artifact(...)
db.insert_run_log(...)
db.insert_run_event(...)
```

| Table | Purpose | Schema |
|-------|---------|--------|
| `runs` | Full run summary: bug, URL, expected behavior, plan, step_findings, timeline, report | `db/schema_runs.sql` |
| `run_artifacts` | Screenshot/video object-storage metadata (`bucket` + `object_key`) | `evidence/schema.sql` |
| `run_logs` | Console / network / snapshot / info text logs | `db/schema.sql` |
| `run_events` | Ordered timeline / action breadcrumbs | `evidence/schema_events.sql` |
| `auth_sessions` | Encrypted Playwright storage-state blobs | `auth/schema.sql` |

Helpers:

- `Database.from_env()` / `get_database()` — app traffic (`DATABASE_URL`)
- `Database.for_migrations()` — DDL (`DATABASE_URL_UNPOOLED` when set)
- `Database.for_auth()` / `get_auth_database()` — `AUTH_DATABASE_URL` or `DATABASE_URL`
- Pooled Neon hosts (`-pooler`) use `NullPool`

Tables are also created on first use via `create_tables()` when the process can reach Postgres.

## Auth sessions and security

Authenticated tests may use an optional `auth_profile_id`. That name is not a secret. The password, cookies, and storage-state JSON never go in graph input, checkpoints, or prompts.

**Login wall (Continue button)**

Auth is not requested up front. If a plan step hits a login page, the executor sets `error` to `auth_expired` without completing the step. The graph routes to `wait_for_login`, which calls LangGraph `interrupt` so Studio (or your frontend / `InsightAgent.acontinue`) can show **Continue**. Sign in in the headed Playwright window, then Continue with an empty resume or `{ "confirmed": true }` — never the password. After resume the node exports the browser storage state and retries the same step. When auth storage is configured, it also encrypts the captured state into Postgres for later runs. Without auth storage, the signed-in browser remains available for the current run, but the session is not saved for future runs.

**What must stay out of the graph**

- Do not put a password, cookie jar, `Authorization` header, or Playwright storage-state JSON in `bug_description`, `expected_behavior`, the Continue/resume payload, or any other state field. Those values are checkpointed and can be traced (including LangSmith if tracing is on).
- The model does not receive cookie tools, `localStorage` / `sessionStorage` tools, `browser_storage_state`, `browser_set_storage_state`, `browser_evaluate`, `browser_run_code_unsafe`, or video start/stop tools. Network and console tool output is redacted (cookies, auth headers, API keys, JWTs, and common password/token JSON fields) before it is stored on a step or sent to the report model.

**Where the session lives**

- Cookies and `localStorage` for one origin are encrypted with AES-GCM using `AUTH_DATA_KEY` (from `.env` on this machine). Only ciphertext, nonce, origin, and expiry are written to Postgres (`AUTH_DATABASE_URL`, or `DATABASE_URL` when unset).
- The ciphertext is bound to `profile_id` + `origin`, so swapping rows in the database fails decryption.
- A remote database URL must set `sslmode=require` (Neon), `verify-ca`, or `verify-full`. Prefer a role that can only `SELECT` / `INSERT` / `UPDATE` / `DELETE` on `auth_sessions`, not a superuser.
- Scratch files under `.playwright-mcp/auth` or `INSIGHT_AUTH_SCRATCH_DIR` (gitignored) exist only while Playwright restores or exports the session, then are deleted. On Windows the directory is locked to the current user with `icacls`.

**Optional CLI setup**

You can still pre-save a session without waiting for a login wall:

```powershell
.\.venv\Scripts\python.exe -m insightai.auth.capture generate-key
# put AUTH_DATA_KEY and AUTH_DATABASE_URL (or DATABASE_URL) in .env

.\.venv\Scripts\python.exe -m insightai.auth.capture save --profile my-app --origin https://app.example.com --login-url https://app.example.com/login
.\.venv\Scripts\python.exe -m insightai.auth.capture list
.\.venv\Scripts\python.exe -m insightai.auth.capture revoke --profile my-app
```

The capture command reads `.env`, saves the session, and then closes its browser when it exits. A later agent run opens a browser and restores the saved session. Set `auth_profile_id` to the same profile name (`my-app` in the example) so it can find that session. For a single run that signs in and then continues using the same open browser, use the graph's Continue login flow instead of the separate capture command. Changing `AUTH_DATA_KEY` does not re-encrypt old rows; revoke and save again.

**Limits**

Playwright storage state covers cookies and `localStorage` only. Sessions that live only in `sessionStorage` are not restored. The LumenShop static test fixture sets a demo cookie and `localStorage` marker on successful sign-in so Continue can capture it. `interrupt` requires a checkpointer (provided by `langgraph dev` / Studio, or by `InsightAgent`).

## Run evidence (screenshots, video, console, network, snapshots)

One Playwright MCP client is reused for the whole LangGraph thread. The harness (not the model) owns durable evidence:

| Kind | When | Where |
|------|------|--------|
| Screenshot | After navigate / click / type / fill / select / keypress | Neon bucket `insight-screenshots` + `run_artifacts` |
| Video | Continuous for the run (`browser_start_video` → stop on finish) | Neon bucket `insight-videos` + `run_artifacts` |
| Console | End of each step (errors + last lines, redacted, capped) | Postgres `run_logs` (`kind=console`) |
| Network | After navigate / form fill / submit-like clicks (failures and HTTP ≥ 400) | Postgres `run_logs` (`kind=network`) |
| Snapshot | After each `browser_snapshot` (a11y tree, redacted, capped) | Postgres `run_logs` (`kind=snapshot`) |

Screenshot and video bytes go to private Neon Object Storage. `run_artifacts` stores `thread_id`, `step`, `kind`, `bucket`, `object_key` only (`kind` is `screenshot` \| `video`). Console, network, and accessibility snapshots are logged via [`utils.logging.Logging`](src/insightai/utils/logging.py) into `run_logs` — not uploaded as objects and not listed on `StepFindings.artifacts`. `StepFindings.artifacts` carries screenshot/video keys into the report. Viewing media uses a short-lived presign (`evidence.store.presign_get`).

Login walls skip screenshots when the page looks like a password form, and `auth_expired` steps drop screenshot artifacts. Evidence upload/logging is best-effort: missing AWS env or tables logs a warning and the QA run continues.

Start MCP with `--output-dir .playwright-mcp` (gitignored). Screenshot pointers
(`bucket` + `object_key`) stay on `step_findings` for the whole run. Local PNGs/
video under that directory are removed when the graph finishes and uploads succeed.

### Timeline and action log

Every run writes structured breadcrumbs to Postgres `run_events` (session, steps,
tools, screenshots, snapshots, auth, uploads). Console/network/snapshot text stays
in `run_logs`; media pointers in `run_artifacts`.

`assemble_timeline(thread_id)` returns a `Timeline` model (events, actions, chapters, artifacts, logs). Dump a thread:

```powershell
.\.venv\Scripts\python.exe -m insightai.evidence.timeline_cli <thread_id> --pretty
.\.venv\Scripts\python.exe -m insightai.evidence.timeline_cli <thread_id> --actions-only --pretty
```

### Persisted runs

On `finalize_report`, `evidence.runs.save_run_from_state` upserts one `runs` row keyed by LangGraph `thread_id`, including:

- `bug_description`, `url`, `expected_behavior`
- `plan`, `step_findings`
- assembled `timeline`
- `report` (and `error` / `completed` when set)

Secrets in payloads are redacted before insert. Persistence is best-effort and must not fail report generation.

```python
from insightai.evidence import save_run_from_state, assemble_timeline
from insightai.db import get_database

# Manual save / load
save_run_from_state(state, config=config, report=report)
row = get_database().get_run(thread_id)
timeline = assemble_timeline(thread_id)
```

## Demo storefront

`src/test_web` is **LumenShop**, a static multi-page shop (catalog, cart, checkout, login, contact, account) meant for exercising the agent. Serve it while testing:

```powershell
python -m http.server 5500 --directory src/test_web
```

See `src/test_web/README.md` for run instructions and sample bug scenarios; `BUGS.md` lists planted defects for scoring runs.

## Development notes

Run the isolated agent contract checks with `python -m unittest discover -s tests`.
Existing package-local auth and evidence checks can be run with
`python -m unittest discover -s src -p 'test_*.py'`.

- Default chat model: `gpt-4o` in `src/insightai/utils/model.py` (override with `OPENAI_MODEL`).
- Do not add a top-level Python package named `mcp` under the agent source tree; it shadows the official MCP SDK. This repo uses `mcp_clients/`.
- After graph or state shape changes, start a new Studio thread so checkpointed state does not conflict with reducers (e.g. `step_findings` must be appended as lists).
- Keep schema SQL, SQLAlchemy models, and the live Neon schema in sync when changing tables.
- FastAPI lives under `src/api/` (scaffold); follow [`docs/FASTAPI_HANDOFF.md`](docs/FASTAPI_HANDOFF.md) when wiring routes to `InsightAgent`.

## Package metadata

Python project name: `insightaiagent` (`pyproject.toml`). Runtime code for the agent lives under `src/insightai/`.
