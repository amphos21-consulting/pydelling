FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy
WORKDIR /app
COPY pyproject.toml uv.lock README.md LICENSE.txt ./
COPY pydelling pydelling
RUN uv sync --locked --group dev --group docs --extra cloud \
    && cp "$(command -v uv)" /tmp/uv

FROM python:3.12-slim-bookworm AS runtime
ENV VIRTUAL_ENV=/app/.venv \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1
WORKDIR /app
COPY --from=builder /tmp/uv /usr/local/bin/uv
COPY --from=builder /app /app
COPY justfile Makefile mkdocs.yml ./
COPY docs docs
CMD ["bash"]
