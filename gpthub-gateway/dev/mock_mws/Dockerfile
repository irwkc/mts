# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm
RUN pip install --no-cache-dir fastapi==0.115.6 uvicorn[standard]==0.34.0
WORKDIR /app
COPY app.py silent.mp3 /app/
EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
