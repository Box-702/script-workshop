FROM python:3.11-slim

WORKDIR /app

COPY apps/api/pyproject.toml ./apps/api/
RUN pip install --no-cache-dir -U pip && \
    pip install --no-cache-dir -e ./apps/api

COPY apps/api/app ./apps/api/app
COPY schema ./schema

WORKDIR /app/apps/api

ENV PYTHONUNBUFFERED=1 \
    API_HOST=0.0.0.0 \
    API_PORT=8000

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
