FROM node:22-bookworm-slim AS frontend

WORKDIR /build
RUN corepack enable && corepack prepare pnpm@11.18.0 --activate
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile --ignore-scripts
COPY babel.config.js vue.config.js ./
COPY public ./public
COPY src ./src
RUN pnpm build

FROM python:3.12-slim-bookworm AS runtime

ARG USER_ID=1000
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/alcali/.local/bin:${PATH}"

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates default-libmysqlclient-dev build-essential pkg-config \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid "${USER_ID}" --create-home --home-dir /opt/alcali --shell /usr/sbin/nologin alcali

WORKDIR /opt/alcali/code
COPY requirements ./requirements
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r requirements/prod.txt "mysqlclient>=2.2,<3"

COPY . .
COPY --from=frontend /build/dist ./dist
RUN chown -R alcali:alcali /opt/alcali

USER alcali
EXPOSE 8000
ENTRYPOINT ["/opt/alcali/code/docker/utils/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "-c", "/opt/alcali/code/docker/gunicorn_config.py"]
