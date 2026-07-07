# KAU-FPO Testing Server — Setup & Usage Guide

## Server Details

| Item | Value |
|---|---|
| Provider | AWS EC2 |
| IP | 35.169.38.1 |
| OS | Ubuntu 24.04 LTS |
| Instance Type | t3.small |
| PEM Key | `Server/kau.pem` |

---

## SSH Into Server

```bash
chmod 400 ~/Desktop/AGRI-THRISSUR/kau-fpo-backend/Server/kau.pem
ssh -i ~/Desktop/AGRI-THRISSUR/kau-fpo-backend/Server/kau.pem ubuntu@35.169.38.1
```

---

## Start / Stop Server (AWS Console)

1. Go to AWS Console → EC2 → Instances
2. Select instance `kau`
3. Click **Instance State → Start** or **Stop**

> Stop when not in use to save cost (~$2/month idle vs ~$15/month running)

---

## Branch Strategy

| Branch | Purpose |
|---|---|
| `develop` | Active development |
| `testing` | Testing server deployment |
| `main` | Production (future) |

### Flow
```
develop → testing (deploy to this EC2 for internal testing)
testing → main   (when approved, deploy to production)
```

---

## Deployment Steps (Testing Server)

### First Time Setup

```bash
# SSH into server
ssh -i Server/kau.pem ubuntu@35.169.38.1

# Clone the repo
git clone https://github.com/YOUR_ORG/kau-fpo-backend.git
cd kau-fpo-backend

# Switch to testing branch
git checkout testing

# Create .env file (never committed to git)
cp .env.example .env.testing
nano .env.testing
# Fill in all credentials (see Credentials section below)

# Start all services
docker-compose -f docker-compose.testing.yml up -d --build
```

### Update Deployment (After Code Changes)

```bash
# SSH into server
ssh -i Server/kau.pem ubuntu@35.169.38.1

cd kau-fpo-backend

# Pull latest changes from testing branch
git pull origin testing

# Rebuild and restart
docker-compose -f docker-compose.testing.yml up -d --build
```

---

## Credentials (.env.testing)

> This file lives on the server only — NEVER commit to git.

```
DJANGO_SETTINGS_MODULE=config.settings.production
SECRET_KEY=your-secret-key
DEBUG=False

DATABASE_URL=postgres://postgres:PASSWORD@db:5432/kau_fpo

REDIS_URL=redis://redis:6379/0

AWS_ACCESS_KEY_ID=your-key
AWS_SECRET_ACCESS_KEY=your-secret
AWS_STORAGE_BUCKET_NAME=kau-fpo-media
AWS_S3_REGION_NAME=ap-south-1

ALLOWED_HOSTS=35.169.38.1
CORS_ALLOWED_ORIGINS=https://your-vercel-app.vercel.app
```

---

## Useful Docker Commands (on server)

```bash
# View running containers
docker ps

# View logs
docker-compose -f docker-compose.testing.yml logs -f

# View logs for specific service
docker-compose -f docker-compose.testing.yml logs -f web

# Stop all services
docker-compose -f docker-compose.testing.yml down

# Start all services
docker-compose -f docker-compose.testing.yml up -d

# Restart a single service
docker-compose -f docker-compose.testing.yml restart web

# Run Django management commands
docker-compose -f docker-compose.testing.yml exec web python manage.py migrate
docker-compose -f docker-compose.testing.yml exec web python manage.py createsuperuser
```

---

## Services Running in Docker

| Service | Purpose | Port |
|---|---|---|
| `web` | Django + Gunicorn | 8000 (internal) |
| `celery` | Background tasks | — |
| `db` | PostgreSQL | 5432 (internal) |
| `redis` | Cache + broker | 6379 (internal) |
| `nginx` | Reverse proxy | 80 (public) |

---

## Access URLs

| URL | Purpose |
|---|---|
| `http://35.169.38.1/api/docs/` | Swagger API docs |
| `http://35.169.38.1/admin/` | Django admin |
| `http://35.169.38.1/api/` | API base |

---

## Important Notes

- The `.pem` file (`Server/kau.pem`) must never be committed to git
- The `.env.testing` file on the server must never be committed to git
- Always stop the EC2 instance when not in use to avoid unnecessary charges
- AWS auto-restarts stopped RDS instances after 7 days (if using RDS)
- Elastic IP `35.169.38.1` stays the same even after stop/start
