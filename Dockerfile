# OntoPoc in one image: the built page and the service on one port (8767, loopback inside the container; a proxy in the
# same network namespace, such as the Caddy service in deploy/demo, is what the outside world reaches).
FROM node:22-slim AS page
WORKDIR /page
COPY landing-page/package.json landing-page/package-lock.json ./
RUN npm ci --no-audit --no-fund --loglevel=error
COPY landing-page/ ./
RUN npm run build --silent

FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN useradd --create-home --uid 10001 ontopoc
WORKDIR /app
COPY pyproject.toml README.md LICENSE NOTICE.md ./
COPY src/ ./src/
RUN pip install --no-cache-dir '.[sources]'
COPY docs/pilot/ ./docs/pilot/
COPY --from=page /page/dist/client ./page
COPY deploy/demo/entrypoint.sh /usr/local/bin/ontopoc-entrypoint
RUN chmod 755 /usr/local/bin/ontopoc-entrypoint && mkdir -p /data && chown ontopoc /data
USER ontopoc
VOLUME /data
ENV ONTOPOC_DATA_DIR=/data ONTOPOC_PORT=8767
ENTRYPOINT ["ontopoc-entrypoint"]
