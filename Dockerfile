FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN apt-get update && apt-get install -y --no-install-recommends iputils-ping ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --upgrade pip && pip install -r /app/requirements.txt

COPY src /app/src
COPY .env /app/.env

ENV PYTHONPATH=/app/src

EXPOSE 8080


CMD ["python", "-m", "perfwatch.main"]
