# Cloud Run job 用イメージ。seed-csv / load-bq / register-fs / batch-read の
# 単一イメージ。job 側 args で分岐する。
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# 依存だけ先にインストール (レイヤキャッシュ)
COPY pyproject.toml ./
RUN uv pip install --system --no-cache \
    "google-cloud-bigquery>=3.25" \
    "google-cloud-storage>=2.18" \
    "google-auth>=2.30"

# アプリ本体
COPY src/app ./app
# CSV (seed-csv で上書きされるが初期値として同梱)
COPY src/data ./data

ENTRYPOINT ["python", "-m", "app.main"]
CMD ["seed-csv"]
