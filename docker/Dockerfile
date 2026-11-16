# syntax=docker/dockerfile:1
FROM python:3.13-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TERM=xterm-256color

RUN apt-get update && apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        curl \
        git \
    && rm -rf /var/lib/apt/lists/*

# The interactive TUI is a bundled Node program (ui/terminal_bundle/postal.mjs),
# so the image needs a Node 22+ runtime even though nothing is compiled here.
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*


FROM base AS build

WORKDIR /src

COPY pyproject.toml README.md LICENSE /stub/
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && cd /stub \
    && mkdir -p agent client config context prompts tools ui utils \
    && touch main.py \
    && /opt/venv/bin/pip install .

COPY . .
RUN /opt/venv/bin/pip install --no-deps .


FROM base AS runtime

COPY --from=build /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

ENV XDG_CONFIG_HOME=/config
RUN mkdir -p /config /workspace
VOLUME ["/config"]

WORKDIR /workspace

ENTRYPOINT ["postal"]