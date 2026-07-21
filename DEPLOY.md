# Fly.io free-tier backend deploy (Element_-Bot)

## Free stack (recommended)

| Service | Free plan | Purpose |
|---------|-----------|---------|
| **Fly.io** | shared-cpu-1x, 256MB RAM allowance* | FastAPI + Matrix bot |
| **Neon** | Free PostgreSQL | Database (required — local Postgres won't work on Fly) |
| **Vercel** | Hobby | Frontend (already deployed) |

\* Matrix + Playwright need ~512MB. Fly may charge a few $/mo above free allowance if you use 512MB + 1GB volume (~$0.15/mo for volume).

---

## Step 1 — GitHub push

Repo: https://github.com/mohsin-ashraf123/Element_-Bot

Git commit is done locally. Push needs your GitHub login (403 = wrong/expired credentials):

```powershell
cd "d:\Mohsin Work\element_bot"
git push -u origin main
```

If 403, create a **Personal Access Token** (GitHub → Settings → Developer settings → Tokens) and:

```powershell
git remote set-url origin https://YOUR_GITHUB_USERNAME:YOUR_TOKEN@github.com/mohsin-ashraf123/Element_-Bot.git
git push -u origin main
```

---

## Step 2 — Free PostgreSQL (Neon)

1. Go to https://neon.tech → Sign up free
2. Create project `element-bot`
3. Copy connection details → update `backend/.env`:
   - `DB_HOST=ep-xxx.region.aws.neon.tech`
   - `DB_USER=...`
   - `DB_PASSWORD=...`
   - `DB_NAME=neondb`
   - `DB_PORT=5432`

---

## Step 3 — Fly.io login (one time)

```powershell
# Install: https://fly.io/docs/hands-on/install-flyctl/
flyctl auth login
```

---

## Step 4 — Deploy backend

```powershell
cd "d:\Mohsin Work\element_bot\backend"

# Create app (Singapore — close to Pakistan)
flyctl launch --no-deploy --copy-config --name element-bot-api --region sin --yes

# Persistent disk for Matrix E2EE keys (~$0.15/mo for 1GB)
flyctl volumes create element_bot_data --region sin --size 1 -a element-bot-api

# Set secrets from your .env (after Neon DB values are in .env)
cd ..
powershell -ExecutionPolicy Bypass -File scripts/fly-set-secrets.ps1

cd backend
flyctl deploy -a element-bot-api
```

Backend URL: **https://element-bot-api.fly.dev**

Check health: https://element-bot-api.fly.dev/api/health

---

## Step 5 — Connect Vercel frontend

```powershell
cd frontend
$env:VERCEL_TOKEN="your_vercel_token"
npx vercel env add VITE_API_URL production
# Enter: https://element-bot-api.fly.dev

npx vercel deploy --prod --yes --token $env:VERCEL_TOKEN
```

Also set Fly secret:
```powershell
flyctl secrets set FRONTEND_URL=https://frontend-rho-pied-deqalmapg4.vercel.app -a element-bot-api
```

---

## Free tier tips

- `fly.toml` uses `auto_stop_machines = "stop"` — app sleeps when idle (saves free hours)
- First request after sleep may take ~10s to wake
- Use **512mb** RAM in fly.toml; if bill is concern, try 256mb (may OOM with Playwright reports)

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Git push 403 | Use GitHub PAT in remote URL |
| Fly auth error | Run `flyctl auth login` |
| DB connection failed | Use Neon host, not `localhost` |
| Matrix E2EE errors | Ensure volume mounted at `/app/data` |
