FROM python:3.11-slim

WORKDIR /app

RUN sed -i 's|http://deb.debian.org|http://mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get update && apt-get install -y --no-install-recommends \
    gcc curl \
    && rm -rf /var/lib/apt/lists/*

# Install Kingdee K3Cloud SDK
COPY sdk/python_sdk_v8.2.0/kingdee.cdp.webapi.sdk-8.2.0-py3-none-any.whl /tmp/
RUN pip install --no-cache-dir /tmp/kingdee.cdp.webapi.sdk-8.2.0-py3-none-any.whl

COPY pyproject.toml ./
RUN pip install --no-cache-dir .

COPY src/ ./src/
COPY config/ ./config/
# NOTE: conf.ini is NOT copied - credentials must come from environment variables
COPY sync_config.json ./

RUN mkdir -p /app/data /app/reports

RUN adduser --disabled-password --gecos '' --uid 1001 appuser \
    && chown -R appuser:appuser /app
USER appuser

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
