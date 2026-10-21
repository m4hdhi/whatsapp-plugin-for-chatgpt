FROM python:3.12-slim-bookworm
WORKDIR /app
COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock && useradd -u 10001 -m worker && mkdir /data && chown worker:worker /data
COPY app ./app
COPY native/mcp_link.py native/__init__.py ./native/
COPY static ./static
COPY cloud ./cloud
USER worker
ENV WA_CLOUD_CONFIG=/config/config.json WA_CLOUD_DATA=/data PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["uvicorn", "cloud.server:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log", "--no-proxy-headers"]
