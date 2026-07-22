# ---------------------------------------------------------------------------
# Stage 1: build audioprobe from source (no prebuilt releases are published).
# Built as a fully static musl binary so it runs on any runtime glibc.
# ---------------------------------------------------------------------------
FROM rust:1-slim AS audioprobe-builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    musl-tools \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && rustup target add x86_64-unknown-linux-musl

WORKDIR /build
ADD https://github.com/CE-Repo/audioprobe/archive/refs/heads/main.tar.gz audioprobe.tar.gz
RUN tar -xzf audioprobe.tar.gz \
    && cd audioprobe-main \
    && cargo build --release --target x86_64-unknown-linux-musl \
    && cp target/x86_64-unknown-linux-musl/release/audioprobe /audioprobe

# ---------------------------------------------------------------------------
# Stage 2: runtime image
# ---------------------------------------------------------------------------
FROM ubuntu:22.04

# hdrprobe release version (prebuilt binary)
ARG HDRPROBE_VERSION=0.7.0

# Prevent interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Install runtime dependencies.
# ffmpeg is kept solely for ffprobe, which recovers the two fields audioprobe
# does not report: object-based audio (Atmos / DTS:X) and audio bitrate.
RUN apt-get update && apt-get install -y \
    ffmpeg \
    python3 \
    python3-pip \
    wget \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Download and install hdrprobe (prebuilt x86_64 Linux binary)
RUN wget -q "https://github.com/matthane/hdrprobe/releases/download/v${HDRPROBE_VERSION}/hdrprobe-${HDRPROBE_VERSION}-x86_64-unknown-linux-gnu.tar.gz" -O /tmp/hdrprobe.tar.gz \
    && mkdir -p /tmp/hdrprobe \
    && tar -xzf /tmp/hdrprobe.tar.gz -C /tmp/hdrprobe \
    && install -m 0755 "$(find /tmp/hdrprobe -type f -name hdrprobe | head -n1)" /usr/local/bin/hdrprobe \
    && rm -rf /tmp/hdrprobe /tmp/hdrprobe.tar.gz

# Install audioprobe (built in stage 1)
COPY --from=audioprobe-builder /audioprobe /usr/local/bin/audioprobe
RUN chmod +x /usr/local/bin/audioprobe

# Set working directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy application files
COPY app.py .
COPY config.py .
COPY services/ ./services/
COPY utils/ ./utils/
COPY watchers/ ./watchers/
COPY static/ ./static/
COPY templates/ ./templates/

# Create media directory
RUN mkdir -p /media

# Expose port
EXPOSE 2367

# Run the application
CMD ["python3", "app.py"]
