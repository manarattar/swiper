# SwipeEat Deployment Notes

## Local setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:SECRET_KEY="replace-with-a-long-random-value"
$env:ADMIN_PASSWORD="replace-with-a-strong-password"
python -m flask --app server run --host 127.0.0.1 --port 5000 --no-reload
```

## Production checklist

- Set `SECRET_KEY`, `ADMIN_PASSWORD`, and either `DATABASE_URL` for Render Postgres or `DATABASE_PATH` for SQLite.
- Do not use the default development password.
- Prefer Render Postgres for production. SQLite is fine locally, but persistent production orders should use `DATABASE_URL`.
- Run behind a production WSGI server such as Waitress or Gunicorn depending on host OS.
- Use HTTPS so session cookies and admin login are protected in transit.
- Run `python -m unittest discover -v` before deploying.

## Operational routes

- `/menu` customer ordering
- `/qr/<table>` table QR entry
- `/admin` admin dashboard
- `/kitchen` kitchen mode
- `/order/<trackingToken>` customer tracking