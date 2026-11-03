FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_LINK_MODE=copy \
    PATH="/opt/venv/bin:${PATH}"

WORKDIR /app

RUN pip install --no-cache-dir uv

# Install locked dependencies before copying source so source edits do not
# invalidate the dependency layer.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY langgraph.json ./
COPY src ./src
RUN uv sync --frozen --no-dev

# The graph CLI reads the env file named in langgraph.json. Secrets are injected
# by Compose at runtime; this empty file keeps the CLI config valid in the image.
RUN touch .env \
    && useradd --create-home --uid 1000 --shell /usr/sbin/nologin app \
    && mkdir -p /data/media \
    && chown -R app:app /app /opt/venv /data

USER app

EXPOSE 2024

CMD ["langgraph", "dev", "--host", "0.0.0.0", "--port", "2024", "--no-browser"]
