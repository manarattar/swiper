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

- Set `SECRET_KEY`, `ADMIN_PASSWORD`, and `DATABASE_PATH` as environment variables.
- Do not use the default development password.
- Keep `swipeeat.db` outside the web root and back it up.
- Run behind a production WSGI server such as Waitress or Gunicorn depending on host OS.
- Use HTTPS so session cookies and admin login are protected in transit.
- Run `python -m unittest discover -v` before deploying.

## Operational routes

- `/menu` customer ordering
- `/qr/<table>` table QR entry
- `/admin` admin dashboard
- `/kitchen` kitchen mode
- `/order/<trackingToken>` customer tracking