# SynApps — Deployment Guide

## Architecture Overview

SynApps runs as three Docker services behind a shared network:

| Service | Image | Port | Role |
|---------|-------|------|------|
| `db` | `postgres:16-alpine` | 5432 | Primary data store |
| `redis` | `redis:7-alpine` | 6379 | Scheduler state + task queue |
| `orchestrator` | multi-stage Python 3.13 | 8000 | FastAPI backend |
| `frontend` | nginx + React build | 3000 | Static frontend |

## Quick Start (Docker Compose)

```bash
# 1. Clone the repository
git clone https://github.com/nxtg-ai/SynApps.git
cd SynApps

# 2. Copy and configure environment variables
cp .env.example .env
# Edit .env — at minimum set JWT_SECRET_KEY, OPENAI_API_KEY

# 3. Start all services
docker compose up --build

# Open http://localhost:3000
```

## Environment Variables

### Required for production

| Variable | Description |
|----------|-------------|
| `JWT_SECRET_KEY` | HS256 signing key — use `openssl rand -hex 32` |
| `DATABASE_URL` | PostgreSQL DSN — e.g. `postgresql+asyncpg://user:pass@host/db` |
| `FERNET_KEY` | Fernet encryption key for secrets at rest — use `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |

### Optional

| Variable | Default | Description |
|----------|---------|-------------|
| `PRODUCTION` | `false` | Set `true` to enable production hardening |
| `REDIS_URL` | `redis://redis:6379/0` | Redis DSN |
| `OPENAI_API_KEY` | — | OpenAI API key for LLM/ImageGen nodes |
| `STABILITY_API_KEY` | — | Stability AI key for ImageGen |
| `BACKEND_CORS_ORIGINS` | `http://localhost:3000` | Comma-separated allowed origins |
| `ENGINE_MAX_CONCURRENCY` | `10` | Max parallel node execution |
| `SCHEDULER_TICK_SECONDS` | `30` | Scheduler polling interval |
| `SMTP_HOST` | — | SMTP host for email notifications |
| `SENDGRID_API_KEY` | — | SendGrid key (alternative to SMTP) |
| `LOG_LEVEL` | `info` | Logging level (`debug`/`info`/`warning`) |

## Production Deployment

### Minimum viable production `.env`

```env
PRODUCTION=true
JWT_SECRET_KEY=<openssl rand -hex 32>
DATABASE_URL=postgresql+asyncpg://synapps:<password>@db:5432/synapps
FERNET_KEY=<python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())">
POSTGRES_PASSWORD=<strong-password>
BACKEND_CORS_ORIGINS=https://your-domain.com
VITE_API_URL=https://api.your-domain.com/api/v1
VITE_WEBSOCKET_URL=wss://api.your-domain.com/api/v1/ws
```

### Start in production mode

```bash
PRODUCTION=true docker compose up -d
docker compose logs -f orchestrator   # Tail backend logs
```

### Database migrations

Migrations run automatically on startup via `alembic upgrade head`. To run manually:

```bash
docker compose exec orchestrator alembic upgrade head
```

### Health checks

```bash
# Backend
curl http://localhost:8000/api/v1/health

# All services
docker compose ps
```

## Cloud Deployment

### Fly.io (backend)

```bash
fly launch --dockerfile infra/docker/Dockerfile.orchestrator
fly secrets set JWT_SECRET_KEY=$(openssl rand -hex 32)
fly secrets set DATABASE_URL="postgresql+asyncpg://..."
fly secrets set FERNET_KEY="..."
fly deploy
```

### Vercel (frontend)

```bash
cd apps/web-frontend
vercel deploy
# Set environment variables in Vercel dashboard:
#   VITE_API_URL=https://your-fly-app.fly.dev/api/v1
#   VITE_WEBSOCKET_URL=wss://your-fly-app.fly.dev/api/v1/ws
```

## Docker Image Details

### Orchestrator (`infra/docker/Dockerfile.orchestrator`)

Multi-stage build:
- **Stage 1 (builder)**: Installs Python dependencies with build tools (gcc, libpq-dev)
- **Stage 2 (runtime)**: Copies only installed packages into a slim Python 3.13 image

Final image size: ~150 MB. Runs as non-root user `synapps`.

### Frontend (`infra/docker/Dockerfile.frontend`)

Multi-stage build:
- **Stage 1**: Node.js 20 + Vite build
- **Stage 2**: nginx serving the compiled static assets

## Scaling

- **Horizontal scaling**: The orchestrator is stateless (all state in PostgreSQL + Redis). Run multiple replicas behind a load balancer.
- **Database**: Point `DATABASE_URL` at a managed PostgreSQL instance (AWS RDS, Supabase, Neon, etc.).
- **Redis**: Point `REDIS_URL` at a managed Redis instance (Upstash, Redis Cloud, etc.).
- **Scheduler**: The in-memory `SchedulerService` will be replaced by a Redis-backed distributed scheduler in a future release.

## Monitoring

The `/api/v1/health` endpoint returns `{"status": "ok"}` — suitable for load balancer health checks and uptime monitors.

Execution analytics are available at:
- `GET /api/v1/analytics/workflows` — per-workflow run metrics
- `GET /api/v1/analytics/nodes` — per-node execution metrics

## Troubleshooting

### Database connection errors

Ensure `DATABASE_URL` is correct and the `db` service is healthy:

```bash
docker compose logs db
docker compose exec db psql -U synapps -d synapps -c '\dt'
```

### Fernet key errors ("Invalid token")

Generate a fresh key and update `FERNET_KEY`:

```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Note: changing the Fernet key invalidates all encrypted secrets stored via N-26. Re-set any workflow secrets after rotating the key.

### CORS errors

Add your frontend origin to `BACKEND_CORS_ORIGINS`:

```env
BACKEND_CORS_ORIGINS=https://your-domain.com,http://localhost:3000
```
