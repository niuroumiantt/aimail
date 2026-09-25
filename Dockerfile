# Linux 主机用。Mac mini 用 deploy/install_mini.sh(launchd),不走 Docker。
FROM node:22-alpine AS web
WORKDIR /app/web
COPY web/package.json web/pnpm-lock.yaml ./
# corepack 按 package.json 的 packageManager 装同一个 pnpm 版本:锁文件在哪儿生成的,就用哪个版本装
RUN corepack enable && corepack prepare --activate
RUN pnpm install --frozen-lockfile
COPY web ./
ENV VITE_DATA_SOURCE=api
RUN pnpm build

FROM python:3.12-slim
ARG VCS_REF=unknown
LABEL org.opencontainers.image.source="https://github.com/niuroumiantt/aimail" \
      org.opencontainers.image.revision="$VCS_REF"
RUN pip install --no-cache-dir uv && useradd -m app && mkdir /data && chown app /data
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY server ./server
RUN uv sync --frozen --no-dev
COPY --from=web /app/web/dist ./web/dist
USER app
ENV WEB_DIST=/app/web/dist DB_PATH=/data/mail2leads.sqlite3 LISTEN_HOST=0.0.0.0
VOLUME /data
EXPOSE 8900
CMD ["uv", "run", "--no-sync", "python", "-m", "aimail", "serve"]
