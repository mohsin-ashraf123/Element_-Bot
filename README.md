# Element_-Bot

PairFlow — Element team pairing & daily review automation (Matrix bot + control panel).

## Stack

- **Frontend:** React + Vite → [Vercel](https://vercel.com)
- **Backend:** FastAPI + Matrix E2EE → [Fly.io](https://fly.io) (free tier)
- **Database:** PostgreSQL ([Neon](https://neon.tech) free tier recommended)

## Live

| Service | URL |
|---------|-----|
| Frontend | https://frontend-rho-pied-deqalmapg4.vercel.app |
| Backend API | https://pairflow-api-production.up.railway.app |

## Local dev

```bash
# Backend
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 5000

# Frontend
cd frontend
npm install
npm run dev
```

Login: `admin` / (see `backend/.env`)

## Deploy backend (Fly.io free)

1. Install [flyctl](https://fly.io/docs/hands-on/install-flyctl/) and run `flyctl auth login`
2. Create free Postgres on [Neon](https://neon.tech) — copy connection details
3. From `backend/`:

```bash
flyctl launch --no-deploy --copy-config --name element-bot-api --region sin
flyctl volumes create element_bot_data --region sin --size 1
flyctl secrets set APP_ENV=production ADMIN_USERNAME=... DB_HOST=... # etc.
flyctl deploy
```

4. Set Vercel env `VITE_API_URL=https://element-bot-api.fly.dev` and redeploy frontend.

See [DEPLOY.md](./DEPLOY.md) for full env variable list.

## Repo

https://github.com/mohsin-ashraf123/Element_-Bot
