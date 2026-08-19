# Day 5 — FastAPI gateway image (pure Python, no native build).
FROM python:3.11-slim

WORKDIR /app
ENV PYTHONPATH=/app

RUN pip install --no-cache-dir \
    "fastapi>=0.110" "uvicorn[standard]>=0.29" "httpx>=0.27" \
    "redis>=5.0" "pydantic>=2.6" "prometheus_client>=0.20" "PyYAML>=6.0"

COPY configs/gateway.yaml configs/gateway.yaml
COPY src/ src/

EXPOSE 8000
CMD ["uvicorn", "src.gateway.app:app", "--host", "0.0.0.0", "--port", "8000"]
