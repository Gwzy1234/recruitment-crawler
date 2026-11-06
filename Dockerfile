FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY web_backend/requirements.txt /app/requirements.txt
RUN python -m pip install --no-cache-dir -r /app/requirements.txt \
    && groupadd -g 10001 appuser \
    && useradd -u 10001 -g 10001 -M -s /usr/sbin/nologin appuser

COPY --chown=10001:10001 frontend /app/frontend
COPY --chown=10001:10001 web_backend /app/web_backend
COPY --chown=10001:10001 team-task.py /app/team-task.py
RUN mkdir -p /app/web_backend/data && chown -R 10001:10001 /app/web_backend/data
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)" || exit 1
CMD ["python", "-m", "uvicorn", "web_backend.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips", "*"]
