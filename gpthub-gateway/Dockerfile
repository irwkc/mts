FROM python:3.11-slim-bookworm

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    ffmpeg \
    libreoffice-impress \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# PyPI в CI иногда даёт SSL: DECRYPTION_FAILED_OR_BAD_RECORD_MAC — длинный таймаут,
# много ретраев pip и при необходимости повтор всего шага.
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=180

RUN python -m pip install --upgrade pip setuptools wheel \
    && set -eu; \
    attempt=1; \
    max=5; \
    while [ "$attempt" -le "$max" ]; do \
      if python -m pip install --no-cache-dir \
          --retries 20 \
          --default-timeout=180 \
          -r requirements.txt; then \
        break; \
      fi; \
      if [ "$attempt" -eq "$max" ]; then exit 1; fi; \
      echo "pip install failed (attempt $attempt/$max), retry in 20s..."; \
      attempt=$((attempt + 1)); \
      sleep 20; \
    done

COPY app ./app

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
