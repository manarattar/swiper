FROM python:3.11-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# DEPLOYMENT.md specifies a production WSGI server; requirements already
# pins gunicorn. FLASK_APP=server, so the callable is server:app.
CMD ["sh", "-c", "gunicorn -b 0.0.0.0:${PORT:-8000} -w 2 --preload --timeout 60 server:app"]
