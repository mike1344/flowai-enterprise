FROM python:3.13-slim

# 镜像源可通过构建参数覆盖（网络不稳定时用镜像站）
ARG PIP_INDEX_URL=https://pypi.org/simple

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --index-url "${PIP_INDEX_URL}" --retries 10 --timeout 120 -r requirements.txt

COPY app ./app
COPY alembic.ini ./
COPY migrations ./migrations

EXPOSE 8002

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=10 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8002/health', timeout=3).status == 200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]