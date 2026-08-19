FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY pyproject.toml README.md ./
COPY backend ./backend
COPY frontend ./frontend
RUN pip install --upgrade pip && pip install ".[openai]"

RUN useradd --create-home --uid 10001 praxis \
    && mkdir -p /data/workspaces \
    && chown -R praxis:praxis /data /app
USER praxis

ENV PRAXISMESH_DATA_DIR=/data \
    PRAXISMESH_DATABASE=/data/praxismesh.db \
    PRAXISMESH_WORKSPACE=/data/workspaces

EXPOSE 8000
HEALTHCHECK --interval=20s --timeout=3s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=2)"

CMD ["uvicorn", "praxismesh.api:app", "--app-dir", "backend", "--host", "0.0.0.0", "--port", "8000"]
