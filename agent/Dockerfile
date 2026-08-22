# Day 7 — LangGraph monitoring agent (Node C). Pure Python, no native build.
FROM python:3.11-slim

WORKDIR /app
ENV PYTHONPATH=/app PYTHONUNBUFFERED=1

RUN pip install --no-cache-dir \
    "langgraph>=0.2" "redis>=5.0" "requests>=2.31" \
    "prometheus_client>=0.20" "PyYAML>=6.0"

COPY configs/agent.yaml configs/agent.yaml
COPY src/ src/

EXPOSE 9108
CMD ["python", "-m", "src.agent.runner"]
