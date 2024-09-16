FROM python:3.11 as builder

ARG USE_AUTH=true

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    libhdf5-dev \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Install pip and uv
RUN pip install --upgrade pip
RUN pip install uv

# Copy necessary files
COPY pyproject.toml uv.lock justfile ./
COPY .git .git
COPY pydelling pydelling

# Create virtual environment and install dependencies
RUN uv venv
RUN uv sync
RUN uv pip install --no-binary=h5py h5py


FROM python:3.11-slim as runtime

ENV VIRTUAL_ENV=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Install HDF5 library in runtime
RUN apt-get update && apt-get install -y \
    libhdf5-103 \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment and necessary files from builder
COPY --from=builder ${VIRTUAL_ENV} ${VIRTUAL_ENV}
COPY --from=builder /app/pydelling pydelling
COPY --from=builder /app/justfile justfile
COPY --from=builder /app/pyproject.toml pyproject.toml


# Set the default command
CMD ["bash", "-c", "source /app/.venv/bin/activate && exec bash"]

WORKDIR /app