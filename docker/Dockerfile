# lmstudio-agent — bridge, local agent, and MCP server runtime
FROM python:3.12-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app/lmstudio
COPY lmstudio/pyproject.toml lmstudio/uv.lock ./
RUN uv sync --frozen --no-dev

COPY lmstudio/ ./
COPY docker/scripts/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
COPY docker/scripts/test_docker_e2e.py /app/docker/scripts/test_docker_e2e.py
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

ENV PYTHONPATH=/app/lmstudio \
    VECTOR_MEMORY_DB=/data/memory/vector/vector-memory.db \
    MEMORY_FILE_PATH=/data/memory/graph/agent-memory.json \
    SKILLS_DIR=/data/memory/skills \
    WORKSPACE_ROOTS=/data/workspace \
    LMSTUDIO_URL=http://host.docker.internal:1234 \
    BRIDGE_PORT=8765

EXPOSE 8765

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["bridge"]
