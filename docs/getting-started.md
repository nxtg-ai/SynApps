# Getting Started with SynApps

SynApps is a visual AI workflow builder. Drag-and-drop AI agent nodes onto a canvas, connect them, and execute workflows in real time.

---

## Prerequisites

Choose one of the following setups:

**Option A — Docker (recommended for a quick start)**

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) 24+ (or Docker Engine 24+ with Docker Compose v2 plugin)

**Option B — Local development**

- Node.js 20+ (for the frontend)
- Python 3.13+ (for the backend)
- pip / virtualenv

---

## Quick Start with Docker

Four commands and you are running.

**1. Clone the repository**

```bash
git clone https://github.com/your-org/synapps.git
cd synapps
```

**2. Create a `.env` file**

Copy the example and fill in the required values:

```bash
cp .env.example .env
```

At minimum, set a `JWT_SECRET_KEY`. See the [Environment Variables](#environment-variables) section below for the full reference.

**3. Start all services**

```bash
docker compose up --build
```

Docker Compose starts three containers: `db` (PostgreSQL 16), `orchestrator` (FastAPI backend on port 8000), and `frontend` (Vite dev server on port 3000).

**4. Open the app in your browser**

Navigate to [http://localhost:3000](http://localhost:3000).

The API is available at [http://localhost:8000/api/v1](http://localhost:8000/api/v1). Interactive API docs are at [http://localhost:8000/docs](http://localhost:8000/docs).

---

## Local Development Setup

Use this path when you want to work on the code and see changes instantly.

### Backend

```bash
# 1. Create a virtual environment
python3.13 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 2. Install the orchestrator in editable mode
cd apps/orchestrator && pip install -e . && cd ../..

# 3. Start the dev server (auto-reloads on file changes)
PYTHONPATH=. uvicorn apps.orchestrator.main:app --reload --port 8000
```

### Frontend

```bash
cd apps/web-frontend

# 1. Install dependencies
npm install

# 2. Start the Vite dev server on port 3000
npm run dev
```

Both servers must be running at the same time for the full app to work.

### Running Tests

```bash
# Backend tests
PYTHONPATH=. pytest apps/orchestrator/tests/ -v

# Frontend unit tests
cd apps/web-frontend && npm test

# E2E tests (requires both servers running)
cd apps/web-frontend && npx playwright test
```

---

## Your First Workflow

This walkthrough creates a simple **Start → LLM → End** flow and runs it.

### 1. Open the editor

After starting the app, click **New Workflow** on the Dashboard. You will land on the canvas editor.

### 2. Add nodes

- In the node palette on the left, drag a **Start** node onto the canvas.
- Drag an **LLM** node onto the canvas and position it to the right of Start.
- Drag an **End** node to the right of LLM.

### 3. Connect the nodes

Click the output handle on the **Start** node and drag to the input handle on the **LLM** node. Repeat to connect **LLM** to **End**.

### 4. Configure the LLM node

Click the **LLM** node to open its configuration panel. Set:

- **Provider** — e.g., `openai`
- **Model** — e.g., `gpt-4o-mini`
- **Prompt** — e.g., `Summarize the following text: {{input}}`

### 5. Run the workflow

Click **Run** in the toolbar. SynApps will execute each node in order and stream results to the output panel on the right. A green border on each node indicates successful execution.

### 6. Save the workflow

Click **Save** (or press `Ctrl+S` / `Cmd+S`). Your workflow is stored and accessible from the **History** page.

---

## Environment Variables

Create a `.env` file at the repository root. Docker Compose and the backend both read from this file.

| Variable | Required | Default | Description |
|---|---|---|---|
| `JWT_SECRET_KEY` | Yes | — | Secret key used to sign auth tokens. Use a long random string in production. |
| `DATABASE_URL` | No | `sqlite+aiosqlite:///./synapps.db` | Database connection string. Use `postgresql+asyncpg://...` for production. |
| `OPENAI_API_KEY` | No | — | API key for the OpenAI provider. Required to run LLM nodes with OpenAI. |
| `ANTHROPIC_API_KEY` | No | — | API key for the Anthropic provider. |
| `POSTGRES_USER` | No | `synapps` | PostgreSQL username (Docker Compose only). |
| `POSTGRES_PASSWORD` | No | `synapps` | PostgreSQL password (Docker Compose only). |
| `POSTGRES_DB` | No | `synapps` | PostgreSQL database name (Docker Compose only). |
| `PRODUCTION` | No | `false` | Set to `true` to enable production-mode settings (HTTPS cookies, stricter CORS). |
| `VITE_API_URL` | No | `http://localhost:8000` | Backend URL for the frontend (must use `VITE_` prefix). |

---

## What's Next

- **[README](../README.md)** — High-level project overview, badge status, and contribution guidelines.
- **[Architecture](architecture.md)** — How the microkernel orchestrator works under the hood.
- **[API Reference](API.md)** — Full REST API documentation.
- **[User Guide](user-guide.md)** — Detailed guide to all node types and workflow patterns.
