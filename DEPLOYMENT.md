# Deploying SwipeEat

**Live at `swipeat.manarattar.com`.**

## How it is put together

Flask app rendering its own Jinja templates and serving its own static files,
so Caddy proxies the **whole host**. Routes: `/` (welcome), `/menu`, `/admin`,
`/kitchen`, `/qr/<table>`.

## Where this runs

Everything is on a single Contabo VPS. There is no Vercel, Render, or other
PaaS involved any more.

| | |
|---|---|
| Server | `194.163.176.183` — `ssh ubuntu@194.163.176.183` (key only, no password) |
| Stack | `/srv/stack/docker-compose.yml` + `/srv/stack/Caddyfile` |
| App sources | `/srv/apps/<name>` |
| Built static sites | `/srv/www/<name>` |
| Secrets | `/srv/stack/env/<name>.env` (0600, root-owned) |
| Database | one `postgres:18-alpine` container, internal network only |
| TLS | Caddy, automatic Let's Encrypt |
| Backups | nightly 03:17 to `/srv/backup/nightly`, 14-day rotation |

Caddy terminates TLS for every hostname and routes by host. Postgres has no
published port — it is reachable only on the internal Docker network.

## Secrets

Never commit them. Each app reads `/srv/stack/env/<name>.env` on the server,
which compose injects via `env_file`. `DATABASE_URL` is set by compose, not by
that file, so an app cannot accidentally point at an old database.

## Deploying a change

```bash
tar czf - --exclude=.git --exclude=__pycache__ --exclude=.env . \
  | ssh ubuntu@194.163.176.183 'tar xzf - -C /srv/apps/swipeat'
ssh ubuntu@194.163.176.183 'cd /srv/stack && sudo docker compose up -d --build swipeat'
```

## Things that will catch you out

- **Run gunicorn with `--preload`.** `backend.py` calls `init_database()` at
  import time, so without it multiple workers race to create `schema_migrations`
  and one dies with a `UniqueViolation`, taking the master down. Against a fresh
  database this fails on first boot.
- `SECRET_KEY` and `ADMIN_PASSWORD` were generated on the server and exist
  nowhere else. Read the admin password with
  `sudo grep ADMIN_PASSWORD /srv/stack/env/swipeat.env`.
- Do not hardcode absolute URLs in templates. The landing page previously linked
  to a Render host and sent visitors off-site to a dead server.
- Vercel cannot build this app: it uses CPython 3.14, and `psycopg[binary]`
  publishes no cp314 wheel.

## Routes

| Route | Purpose |
|---|---|
| `/` | Welcome page |
| `/landingpage` | Marketing landing page |
| `/menu` | Customer ordering |
| `/qr/<table>` | Table entry via QR code |
| `/order/<trackingToken>` | Customer order tracking |
| `/admin` | Admin dashboard (login required) |
| `/kitchen` | Kitchen mode |

## Local development

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:SECRET_KEY="replace-with-a-long-random-value"
$env:ADMIN_PASSWORD="replace-with-a-strong-password"
python -m flask --app server run --host 127.0.0.1 --port 5000 --no-reload
```

SQLite is fine locally — set `DATABASE_PATH`. Production uses `DATABASE_URL`
against the Postgres container.

Run the tests before deploying:

```
python -m unittest discover -v
```

## Rolling back

Rebuild from the previous commit and redeploy. There is no rollback to a
previous provider — the old Vercel and Render deployments were deleted in
September 2026. Database backups are on the server at
`/srv/backup/nightly` (nightly, 14-day rotation).
