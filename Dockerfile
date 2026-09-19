# Linux 主机用。Mac mini 用 deploy/install_mini.sh(launchd),不走 Docker。
FROM node:22-alpine AS web
WORKDIR /app/web
RUN corepack enable
COPY web/package.json web/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY web ./
RUN pnpm build

FROM python:3.12-slim
RUN pip install --no-cache-dir uv && useradd -m app && mkdir /data && chown app /data
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY server ./server
RUN uv sync --frozen --no-dev
COPY --from=web /app/web/dist ./web/dist
USER app
ENV WEB_DIST=/app/web/dist DB_PATH=/data/mail2leads.sqlite3
VOLUME /data
EXPOSE 8900
CMD ["uv", "run", "--no-sync", "python", "-m", "mail2leads", "serve"]
