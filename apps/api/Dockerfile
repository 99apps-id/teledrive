FROM python:3.11-slim

WORKDIR /app

COPY apps/api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && groupadd --system teledrive \
    && useradd --system --gid teledrive --create-home --home-dir /app teledrive

COPY apps/api/app /app/app
COPY apps/api/alembic.ini /app/alembic.ini
COPY apps/api/migrations /app/migrations
RUN mkdir -p /app/storage /app/server-files \
    && chown -R teledrive:teledrive /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

USER teledrive

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
