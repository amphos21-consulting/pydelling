FROM python:3.12-trixie as builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_CACHE_DIR=/tmp/uv-cache \
    UV_PROJECT_ENVIRONMENT=/app/.venv

ARG USE_AUTH=true

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    gcc \
    g++ \
    make \
    && rm -rf /var/lib/apt/lists/*

# Install pip and uv
RUN pip install --upgrade pip
RUN pip install uv

# Copy necessary files
COPY pyproject.toml uv.lock justfile Makefile mkdocs.yml ./
COPY docs docs
COPY .git .git
COPY pydelling pydelling

# Create virtual environment and install dependencies
RUN uv venv
RUN uv python pin 3.12
RUN uv sync
RUN uv pip install --no-binary=h5py h5py

RUN mkdir -p /tmp/uv-cache

FROM python:3.12-slim-trixie as runtime

ENV VIRTUAL_ENV=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Install HDF5 library in runtime
RUN apt-get update && apt-get install -y \
    libhdf5-hl-310 \
    libhdf5-hl-fortran-310 \
    libexpat1 \
    make \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment and necessary files from builder
COPY --from=builder ${VIRTUAL_ENV} ${VIRTUAL_ENV}
COPY --from=builder /app/pydelling pydelling
COPY --from=builder /app/justfile justfile
COPY --from=builder /app/pyproject.toml pyproject.toml
COPY --from=builder /app/Makefile Makefile
COPY --from=builder /app/docs docs
COPY --from=builder /app/mkdocs.yml mkdocs.yml

# Create site directory for MkDocs output
RUN mkdir -p site


# Set the default command
CMD ["bash", "-c", "source /app/.venv/bin/activate && exec bash"]
WORKDIR /app