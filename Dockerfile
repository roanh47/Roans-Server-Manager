# Single-page control panel for one server.
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY servermanager ./servermanager
COPY web ./web

# Runs as root on purpose: reading /proc/<pid>/cgroup and /proc/<pid>/fd to
# attribute a listening port to a process, and talking to the Docker socket,
# both need it. The container only ever binds 127.0.0.1 (see docker-compose.yml).
EXPOSE 8303

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8303/healthz', timeout=4).status == 200 else 1)"

CMD ["uvicorn", "servermanager.web.app:app", "--host", "127.0.0.1", "--port", "8303"]
