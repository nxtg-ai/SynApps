# SynApps Self-Hosted Deployment Guide

## Quick Start (Docker Compose)

One command — no configuration required for a working local instance:

```bash
git clone https://github.com/nxtg-ai/SynApps.git
cd SynApps
cp .env.example .env          # add your API keys
docker-compose -f infra/docker/docker-compose.yml up --build
```

Open [http://localhost:3000](http://localhost:3000).

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | Yes | OpenAI API key for LLM and ImageGen nodes |
| `SECRET_KEY` | Yes | Random 32-character string used to sign JWTs — generate with `openssl rand -hex 32` |
| `DATABASE_URL` | No | Defaults to `sqlite+aiosqlite:///./synapps.db`. Switch to PostgreSQL for production (see below). |

Copy `.env.example` to `.env` and fill in the values before starting the stack.

---

## Production Deployment

### Option 1 — Managed (Fly.io + Vercel)

This is the recommended path for teams who want low operational overhead.

**Backend (Fly.io)**

```bash
# Install flyctl: https://fly.io/docs/hands-on/install-flyctl/
fly auth login
fly launch --name synapps-api --region lax
fly secrets set SECRET_KEY="$(openssl rand -hex 32)"
fly secrets set OPENAI_API_KEY="sk-..."
fly secrets set DATABASE_URL="postgres://..."
fly deploy
```

**Frontend (Vercel)**

```bash
# Install Vercel CLI: npm i -g vercel
cd apps/web-frontend
vercel --prod
# Set env var in Vercel dashboard: VITE_API_URL=https://synapps-api.fly.dev
```

---

### Option 2 — Self-Hosted VPS

Suitable for teams with infrastructure requirements or data-residency constraints.

**1. Provision a server** (Ubuntu 22.04 LTS recommended, 2 vCPU / 4 GB RAM minimum).

**2. Install Docker and Docker Compose:**

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
```

**3. Clone the repository and configure environment variables:**

```bash
git clone https://github.com/nxtg-ai/SynApps.git
cd SynApps
cp .env.example .env
# Edit .env — set SECRET_KEY, OPENAI_API_KEY, DATABASE_URL (PostgreSQL)
```

**4. Start the stack:**

```bash
docker-compose -f infra/docker/docker-compose.yml up -d --build
```

**5. Set up a reverse proxy (nginx example):**

```nginx
server {
    listen 80;
    server_name yourdomain.com;

    location / {
        proxy_pass http://localhost:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /api/ {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        # SSE support
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 3600s;
    }
}
```

Obtain a TLS certificate via Certbot:

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d yourdomain.com
```

---

## Scaling

### Horizontal scaling

Run multiple orchestrator replicas behind a load balancer. Because execution state is stored in PostgreSQL, replicas are stateless:

```bash
docker-compose -f infra/docker/docker-compose.yml up -d --scale orchestrator=3
```

Point a load balancer (nginx `upstream`, HAProxy, or a cloud LB) at the replica ports.

### Database

Switch `DATABASE_URL` from SQLite to PostgreSQL for any multi-user or production deployment:

```
DATABASE_URL=postgresql+asyncpg://user:password@host:5432/synapps
```

Apply migrations after updating the URL:

```bash
PYTHONPATH=. alembic upgrade head
```

### Redis (optional — SSE pub/sub at scale)

When running multiple orchestrator replicas, SSE events must be broadcast across all instances. Add a Redis URL to enable the distributed `SSEEventBus`:

```
REDIS_URL=redis://localhost:6379/0
```

Without `REDIS_URL`, the bus falls back to an in-process implementation — correct for single-replica deployments, but SSE streams will miss events on multi-replica setups.

---

## Security Checklist

- [ ] Set a strong, unique `SECRET_KEY` (`openssl rand -hex 32`)
- [ ] Use PostgreSQL, not SQLite, in production
- [ ] Enable HTTPS via a reverse proxy (nginx or Caddy)
- [ ] Restrict outbound SSRF targets using `SSRF_ALLOWLIST` env var
- [ ] Rotate `OPENAI_API_KEY` regularly and use least-privilege API keys
- [ ] Run the orchestrator container as a non-root user (`user: "1000:1000"` in Compose)
- [ ] Set `ALLOWED_ORIGINS` to your frontend domain (default allows `localhost` only)
- [ ] Enable PostgreSQL connection SSL (`?ssl=require` in `DATABASE_URL`)
