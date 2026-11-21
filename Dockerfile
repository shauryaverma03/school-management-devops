FROM python:3.12-slim AS dependencies
WORKDIR /build
COPY requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

FROM python:3.12-slim
ARG APP_VERSION=local
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 APP_VERSION=$APP_VERSION APP_ENV=container
WORKDIR /service
COPY --from=dependencies /wheels /wheels
COPY requirements.txt .
RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt && rm -rf /wheels && useradd --uid 10001 --create-home app
COPY --chown=10001:10001 app app
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/ready')"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
