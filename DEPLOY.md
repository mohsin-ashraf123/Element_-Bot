# PairFlow deployment

## Architecture

| Component | Host | Why |
|-----------|------|-----|
| **Frontend** (React/Vite) | Vercel | Static SPA + CDN |
| **Backend** (FastAPI + Matrix bot) | Fly.io / Render | Needs 24/7 process, PostgreSQL, persistent disk for E2EE keys |

The Matrix bot **cannot** run on Vercel serverless (no background scheduler, no persistent E2EE store, timeouts).

## Live URLs

- **Frontend (production):** https://frontend-rho-pied-deqalmapg4.vercel.app
- **Backend:** deploy using steps below, then set `VITE_API_URL` on Vercel

## 1. Frontend (Vercel) — done

Redeploy after backend URL is known:

```powershell
cd frontend
$env:VERCEL_TOKEN="your_vercel_token"
npx vercel env add VITE_API_URL production   # e.g. https://pairflow-api.fly.dev
npx vercel deploy --prod --yes --token $env:VERCEL_TOKEN
```

## 2. Backend (Fly.io — recommended)

```powershell
# One-time login
flyctl auth login

cd backend
flyctl launch --no-deploy --copy-config --name pairflow-api --region sin
flyctl volumes create pairflow_data --region sin --size 1

# Secrets (use your real .env values — never commit .env)
flyctl secrets set `
  APP_ENV=production `
  ADMIN_USERNAME=admin `
  ADMIN_PASSWORD=... `
  SESSION_SECRET=... `
  SECRETS_ENCRYPTION_KEY=... `
  DB_HOST=... DB_PORT=5432 DB_NAME=... DB_USER=... DB_PASSWORD=... `
  MATRIX_HOMESERVER_URL=... `
  MATRIX_BOT_USERNAME=... `
  MATRIX_BOT_PASSWORD=... `
  MATRIX_ROOM_ID=... `
  MATRIX_TASK_ROOM_ID=... `
  MATRIX_DEVICE_ID=PAIRFLOWBOT1 `
  MATRIX_RECOVERY_KEY="..." `
  MATRIX_PICKLE_KEY=... `
  FRONTEND_URL=https://frontend-rho-pied-deqalmapg4.vercel.app

flyctl deploy
```

Use **Neon** or **Supabase** free Postgres for `DB_*` vars if you don't run Postgres on Fly.

## 3. Backend (Render — alternative)

1. Push repo to GitHub (exclude `.env`).
2. Render Dashboard → **New Blueprint** → connect repo → uses root `render.yaml`.
3. Set secret env vars in Render dashboard (Matrix, admin, etc.).
4. Copy Render service URL → set as `VITE_API_URL` on Vercel.

## Security

- Never commit `backend/.env` or Vercel tokens.
- Rotate any token that was shared in chat.
