FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 APP_DATA_DIR=/data
WORKDIR /opt/groupbrief
COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock && useradd --create-home --uid 10001 groupbrief && mkdir /data && chown groupbrief:groupbrief /data
COPY --chown=groupbrief:groupbrief app ./app
COPY --chown=groupbrief:groupbrief static ./static
USER groupbrief
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)" || exit 1
CMD ["uvicorn", "app.server:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
