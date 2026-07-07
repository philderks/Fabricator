# syntax=docker/dockerfile:1

# ---- Stage 1: build the frontend ----
# Pinned to the build host arch ($BUILDPLATFORM): the dist output is
# arch-independent, so this avoids emulating the whole Node toolchain under
# QEMU on the linux/arm64 build (the slow, flaky part).
FROM --platform=$BUILDPLATFORM node:20-slim AS frontend
WORKDIR /app/frontend
COPY apps/frontend/package.json apps/frontend/package-lock.json ./
RUN npm ci
COPY apps/frontend/ ./
RUN npm run build

# ---- Stage 2: install Python dependencies ----
FROM python:3.11-slim AS python-deps

ENV VIRTUAL_ENV=/opt/venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

WORKDIR /app

COPY requirements.txt ./
RUN python -m venv "$VIRTUAL_ENV" \
    && pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# ---- Stage 3: Python runtime ----
FROM python:3.11-slim AS runtime

# Java is managed at runtime by Fabricator into the /data volume (JAVA_ROOT),
# not baked into the image. slim lacks libs a downloaded JRE touches for
# fonts/AWT (some server jars reach for them). tini = clean PID 1 so the
# Minecraft / playit subprocesses are reaped and signals are forwarded.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates fontconfig libfreetype6 gosu tini \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV VIRTUAL_ENV=/opt/venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

COPY --from=python-deps /opt/venv /opt/venv

COPY apps/backend/ ./backend/
COPY run.py ./
COPY --from=frontend /app/frontend/dist ./frontend/dist

ARG VERSION=unknown
RUN echo "$VERSION" > .fabricator_version

ENV FLASK_ENV=production \
    HOST=0.0.0.0 \
    PORT=5000 \
    FABRICATOR_NO_TRAY=1 \
    FABRICATOR_DISABLE_SELF_UPDATE=1 \
    SERVER_ROOT=/data/servers \
    SERVER_INDEX_FILE=/data/servers.json \
    JAVA_ROOT=/data/java \
    BACKUPS_DIR=/data/backups \
    PLAYIT_RUNTIME_DIR=/data/playit
# Every persistent path is pinned onto /data (the only VOLUME). FLASK_ENV=
# production otherwise hardcodes them under /var/lib/fabricator (off-volume,
# ephemeral). FABRICATOR_APPDATA is deliberately NOT set: ProductionConfig
# ignores appdata for these paths and run.py's chdir-into-appdata is frozen
# (.exe) only, so it would be dead weight here.

# Run as a dedicated unprivileged user (parity with the systemd install's
# --system 'fabricator' user; root in the container would be a regression).
# uid is pinned so ownership on the /data volume is stable across rebuilds.
RUN useradd --system --no-create-home --shell /usr/sbin/nologin --uid 10001 fabricator

COPY docker/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

VOLUME ["/data"]
EXPOSE 5000

# HOST=0.0.0.0 binds all interfaces *inside* the container netns (required to
# reach the panel through a published port). Restrict exposure on the host side
# via the compose port mapping, not by changing HOST.
#
# The entrypoint starts as root only to chown the freshly-mounted /data volume,
# then drops to 'fabricator' via gosu and execs tini (PID 1) -> python.
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["python", "run.py"]
