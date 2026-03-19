
![SynApps Logo](logo192.png)

# SynApps [![Star on GitHub](https://img.shields.io/github/stars/nxtg-ai/SynApps-v0.4.0?style=social)](https://github.com/nxtg-ai/SynApps-v0.4.0/stargazers)

A web-based visual AI workflow builder where users drag-and-drop AI agent nodes, connect them on a canvas, and execute workflows in real-time.

## Introduction

SynApps is a **web-based visual platform for modular AI agents called Snaplets**. Its mission is to let indie creators build autonomous AI snaplets like LEGO blocks -- each snaplet is a small agent with a specialized skill. A lightweight **SynApps Orchestrator** routes messages between these snaplets, sequencing their interactions to solve tasks collaboratively. SynApps connects AI "synapses" (snaplets) in real time, forming an intelligent network that can tackle complex workflows.

## Features

- **Visual Workflow Builder:** Drag-and-drop AI nodes onto a canvas and connect them to build workflows.
- **Autonomous & Collaborative Snaplets:** Each snaplet runs autonomously but can pass data to others via the orchestrator.
- **Real-Time Visual Feedback:** See the AI snaplets at work with an animated graph of nodes and connections.
- **Background Execution & Notifications:** Snaplets run in the background once triggered, with notifications for status changes.
- **Extensibility:** 9 built-in node types (LLM, ImageGen, Code, HTTP Request, Transform, IfElse, Merge, ForEach, Memory) with support for custom logic via the Code node.
- **Universal API Connector:** The HTTP Request node (N-18) supports GET/POST/PUT/PATCH/DELETE, bearer/basic/API-key auth, SSRF protection, retry with exponential backoff, and response header capture.
- **Inbound Webhook Trigger:** The Webhook Trigger node (N-19) exposes a unique URL per trigger. Any external service can POST to that URL to start the workflow. Optional HMAC-SHA256 signature verification rejects unsigned or tampered requests.

## Quick Start

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/)
- For local development: Node.js 20+ and Python 3.13+

### Running with Docker

1. Clone the repository:
   ```bash
   git clone https://github.com/nxtg-ai/synapps.git
   cd synapps
   ```

2. Create a `.env` file in the root of the project:
   ```
   OPENAI_API_KEY=your_openai_api_key
   STABILITY_API_KEY=your_stability_api_key
   ```

3. Build and run the containers (PostgreSQL + orchestrator + frontend):
   ```bash
   docker-compose -f infra/docker/docker-compose.yml up --build
   ```

4. Open your browser and navigate to [http://localhost:3000](http://localhost:3000)

### Local Development

#### Backend (Orchestrator)

```bash
# From the repo root
cd apps/orchestrator && pip install -e . && cd ../..

# Set up your environment variables
cp .env.example .env
# Then edit .env with your actual API keys

# Run database migrations
alembic upgrade head

# Start the dev server
PYTHONPATH=. uvicorn apps.orchestrator.main:app --reload --port 8000
```

#### Frontend

```bash
cd apps/web-frontend
npm install
npm run dev    # Starts Vite dev server on :3000
```

## Architecture

SynApps follows a microkernel architecture:

- **Orchestrator:** A FastAPI backend that routes messages between applets and manages workflow execution. All applet logic, auth, and WebSocket handlers live in `apps/orchestrator/main.py`.
- **Applets (Nodes):** Self-contained AI micro-agents implementing a standard `BaseApplet` interface.
- **Frontend:** React 18 + TypeScript app with a visual workflow editor built on @xyflow/react, styled with Tailwind CSS, state managed by Zustand.
- **Database:** SQLite (dev via aiosqlite) / PostgreSQL (prod via asyncpg) with async SQLAlchemy 2.0 ORM.

## Node Types

| Node | Description |
|------|-------------|
| **LLM** | Text generation via LLM (e.g. GPT-4o) |
| **ImageGen** | Image generation from text prompts |
| **Code** | Execute custom Python/JavaScript logic |
| **HTTP** | Make HTTP requests to external APIs (GET/POST/PUT/PATCH/DELETE, bearer/basic/API-key auth, SSRF protection, retry with exponential backoff) |
| **Webhook Trigger** | Start a workflow from an inbound HTTP POST — unique URL per trigger, optional HMAC-SHA256 signature verification |
| **Scheduler** | Start a workflow on a cron schedule — 5-field cron expression, pause/resume, configurable tick interval |
| **Error Handler** | Catch pipeline errors — `fallback_content` output substitution, `suppress_error` to continue silently, dead letter queue integration |
| **Marketplace** | Publish flows to a shared marketplace, search/discover by name/tags/category, install listings into your workspace (`/api/v1/marketplace/`) |
| **Analytics** | Per-workflow and per-node execution metrics — run count, success/error rates, avg duration (`/api/v1/analytics/`) |
| **Variables** | Per-workflow key-value variables (`{{var.name}}` in node fields) + encrypted secrets (`{{secret.name}}`, masked in API responses) |
| **Notifications** | Email (SMTP/SendGrid), Slack Incoming Webhook, custom webhook — on_complete/on_failure per workflow (`/api/v1/workflows/:id/notifications`) |
| **Comments** | Threaded node comments + workflow activity feed — edits, runs, and comments (`/api/v1/workflows/:id/nodes/:nodeId/comments`, `/api/v1/workflows/:id/activity`) |
| **Permissions** | Workflow ownership + team access control — owner/editor/viewer roles, share/revoke per user, enforced on edit + execute (`/api/v1/workflows/:id/share`, `/api/v1/workflows/:id/permissions`) |
| **Transform** | Transform and reshape data between nodes |
| **IfElse** | Conditional branching based on expressions |
| **Merge** | Combine outputs from multiple branches |
| **ForEach** | Iterate over collections |
| **Memory** | Store/retrieve context using SQLite FTS or ChromaDB vector store |

## Initiatives

All 25 shipped N-series initiatives — the complete SynApps v1.0 roadmap:

| # | Initiative | Pillar | Description |
|---|-----------|--------|-------------|
| N-01 | Visual Workflow Editor MVP | VISUAL | React Flow canvas with drag-and-drop node creation, WebSocket execution feedback, status indicators |
| N-02 | Writer Applet (GPT-4o) | NODES | GPT-4o text generation with system prompt configuration |
| N-03 | Artist Applet (Stable Diffusion) | NODES | Stable Diffusion image generation with model selection |
| N-04 | Memory Applet (SQLite FTS + ChromaDB) | NODES | Persistent memory with dual backends: SQLite FTS5 full-text search and ChromaDB vector store |
| N-05 | Sequential Execution Engine | EXECUTION | Single-threaded node execution, basic error handling — foundation for parallel engine |
| N-06 | Database Persistence | STACK | SQLAlchemy async ORM, Alembic migrations, workflow/node/edge/run storage |
| N-07 | Backend Stack Upgrade | STACK | Python 3.13, FastAPI 0.115+, Pydantic v2, SQLAlchemy 2.0 — full modernization from Python 3.9/Pydantic v1 |
| N-08 | Frontend Stack Migration | STACK | CRA → Vite 6, CSS modules → Tailwind 4 + shadcn/ui, Zustand state, TypeScript strict, @xyflow/react v12 |
| N-09 | Universal LLM Node | NODES | OpenAI, Anthropic, Google, Ollama, Custom endpoints — per-node provider/model selection, streaming via SSE |
| N-10 | Parallel Execution Engine | EXECUTION | Topological sort with parallel group detection, fan-out/fan-in, configurable concurrency limits |
| N-11 | Conditional Routing (If/Else) | EXECUTION | If/Else node with equals/contains/regex/json_path operations, negate flag, template expression evaluation |
| N-12 | JWT Authentication | SECURITY | Email/password + refresh tokens, bcrypt password hashing, Fernet-encrypted API key storage, rate limiting |
| N-13 | Code Node with Sandboxing | NODES | Python/JavaScript execution in subprocess with resource limits, filesystem restrictions, timeout enforcement |
| N-14 | Execution Visualization | VISUAL | CSS-driven node glow, animated edge particles, progress spinners, success/error badges, mini-output preview |
| N-15 | Comprehensive Test Suite | STACK | pytest + pytest-asyncio (backend), Vitest + React Testing Library (frontend), Playwright E2E, GitHub Actions CI |
| N-16 | 2Brain Dogfood Template | DOGFOOD | "2Brain Inbox Triage" template: Start → LLM classifier → Code structurer → Memory store → End |
| N-17 | Workflow Export/Import + UX Polish | VISUAL | Export/import workflows as portable JSON, run button UX fix, version strings updated to v1.0 |
| N-18 | HTTP Request Node | NODES | GET/POST/PUT/PATCH/DELETE, bearer/basic/API-key auth, SSRF protection, retry with exponential backoff |
| N-19 | Webhook Trigger Node | NODES | Inbound event trigger — unique URL per trigger, HMAC-SHA256 signature verification, Fernet-encrypted secrets |
| N-20 | Scheduler Node | NODES | Cron-triggered workflows — 5-field cron expression, pause/resume, 30s tick loop via croniter |
| N-21 | Template Marketplace Enhancements | PLATFORM | Credential scrubbing on export (18 field variants), `GET /templates/search` with q/tags/category filters |
| N-22 | Error Handling + Retry Logic + Workflow Versioning | EXECUTION | ErrorHandlerNode, DeadLetterQueue, retry_on conditions, FlowVersionRegistry snapshots, rollback, diff |
| N-23 | Workflow Marketplace API | PLATFORM | Publish, search (paginated), featured listings, install with ID remapping — `POST/GET /marketplace/...` |
| N-24 | Execution Analytics | PLATFORM | Per-workflow and per-node metrics — run count, success/error rates, avg duration — `GET /analytics/...` |
| N-25 | Execution Logs + Debug Console | PLATFORM | Structured per-node logs (input, output, duration, errors, retry attempts), `GET /executions/:id/logs`, debug mode |
| N-26 | Workflow Variables + Environment Secrets | PLATFORM | Per-workflow `{{var.name}}` key-value store + Fernet-encrypted `{{secret.name}}` secrets (masked in API responses + logs), `GET/PUT /workflows/:id/variables|secrets` |
| N-27 | Workflow Notifications | PLATFORM | Email (SMTP/SendGrid), Slack webhook, custom webhook — on_complete/on_failure per flow, fire-and-forget dispatch, `GET/PUT /workflows/:id/notifications` |
| N-28 | Workflow Comments + Collaboration | PLATFORM | Threaded node comments (`parent_id`), workflow activity feed (edits, runs, comments) — `POST/GET /workflows/:id/nodes/:nodeId/comments`, `GET /workflows/:id/activity` |
| N-29 | Workflow Permissions — Team Access Control | PLATFORM | Ownership on create, `viewer`/`editor` roles, enforced on edit + execute, share/revoke per user — `POST /workflows/:id/share`, `GET /workflows/:id/permissions` |
| N-30 | Audit Trail — Compliance Logging | PLATFORM | Global compliance log (actor, action, resource, timestamp), 90-day retention with auto-purge, query filters — `GET /audit?actor=&action=&resource_id=&since=&limit=` |
| N-31 | Workflow Import from External Tools | PLATFORM | Import n8n and Zapier workflows; auto-detects format, maps 20+ node types, optional `save=true` — `POST /workflows/import` |
| N-32 | Real-Time Execution Streaming — SSE Progress | EXECUTION | Node-by-node execution progress via Server-Sent Events; `SSEEventBus` pub/sub, `useExecutionStream` React hook — `GET /executions/:id/stream` |
| N-33 | Workflow Analytics Dashboard — Execution Insights | PLATFORM | Top workflows by executions, avg duration by node type, 24h error rate trends, peak usage hours; CSV export — `GET /analytics/dashboard` |
| N-34 | Workflow Testing Framework — Automated Validation | EXECUTION | Assertion DSL (`output.field == value`, `output.count > 5`, `type(output.x) == list`), test history per version — `POST /workflows/:id/test` |

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.13+, FastAPI 0.115+, Pydantic v2, SQLAlchemy 2.0 (async) |
| Frontend | React 18, TypeScript (strict), Vite 6, Tailwind CSS 4, Zustand, @xyflow/react v12 |
| Database | SQLite (dev), PostgreSQL (prod) |
| Testing | pytest + pytest-asyncio (backend), Vitest + React Testing Library (frontend), Playwright (E2E) |
| Linting | Ruff (Python), ESLint 9 flat config + Prettier (TypeScript) |
| CI/CD | GitHub Actions, Codecov, Docker |
| Deploy | Fly.io (backend), Vercel (frontend) |

## Portfolio Templates

SynApps ships with workflow templates that validate the platform against real NXTG.AI portfolio use cases.

| Template | Consumer | Pipeline | Nodes |
|----------|----------|----------|-------|
| **2Brain Inbox Triage** | 2Brain (P-13) | Capture → Classify → Structure → Store | Start → LLM → Code → Memory → End |
| **Content Engine Pipeline** | nxtg-content-engine (P-14) | Research → Summarize → Format → Store | Start → HTTP → LLM → Code → Memory → End |

Templates are available in the frontend gallery (`apps/web-frontend/src/templates/`) and as standalone YAML definitions (`templates/`).

## Pricing

| Plan | Price | Workflows | Executions/mo |
|------|-------|-----------|---------------|
| Free | $0 | 5 | 100 |
| Pro | $29/mo | Unlimited | Unlimited |
| Enterprise | Custom | Unlimited | Unlimited |

See [Pricing Page](https://synapps.nxtg.ai/pricing) or [self-host for free](docs/DEPLOY.md).

## Deployment

- **Frontend:** Vercel
- **Backend:** Fly.io

CI/CD pipelines are set up using GitHub Actions.

See [DEPLOY.md](docs/DEPLOY.md) for the complete self-hosted deployment guide.

## Testing

**2,094 tests** (1,981 backend + 109 frontend unit + 4 E2E) — all passing.

### Backend

```bash
# Run all tests (from repo root)
PYTHONPATH=. pytest apps/orchestrator/tests/ -v

# With coverage
PYTHONPATH=. pytest apps/orchestrator/tests/ --cov=apps/orchestrator --cov-report=term-missing
```

### Frontend

```bash
cd apps/web-frontend
npm test                        # Vitest (single run)
npm run typecheck               # TypeScript type checking
```

### E2E

```bash
cd apps/web-frontend
npx playwright test             # Run all E2E tests
npx playwright test --headed    # Run with browser visible
```

## Linting & Formatting

```bash
# Backend (from repo root)
ruff check apps/orchestrator --config apps/orchestrator/pyproject.toml
ruff format apps/orchestrator --config apps/orchestrator/pyproject.toml

# Frontend (from apps/web-frontend/)
npm run lint
npm run format:check

# All at once via pre-commit
pre-commit run --all-files
```

## Development Scripts

A convenience script starts both servers (requires `concurrently` and `kill-port` installed globally):

```bash
.scripts/start-dev.sh
```

> **Note:** The script may use older invocation patterns. If you encounter import errors, use the manual backend/frontend commands documented above.

## Development Workflow

1. Create a feature branch from `master`
2. Make your changes
3. Write tests for your changes
4. Run `pre-commit run --all-files` to check linting
5. Submit a pull request to `master`

## Contributing

Contributions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed guidelines.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgements

- [@xyflow/react](https://reactflow.dev/) for the workflow visualization
- [anime.js](https://animejs.com/) for animations
- [FastAPI](https://fastapi.tiangolo.com/) for the backend
- [Monaco Editor](https://microsoft.github.io/monaco-editor/) for the code editor
- [Tailwind CSS](https://tailwindcss.com/) for styling
- [Zustand](https://zustand-demo.pmnd.rs/) for state management
