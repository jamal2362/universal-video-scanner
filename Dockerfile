FROM ubuntu:22.04

# Probe versions (prebuilt release binaries)
ARG HDRPROBE_VERSION=0.7.0
ARG AUDIOPROBE_VERSION=0.2.0

# Prevent interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Install runtime dependencies.
# Detection is handled entirely by hdrprobe + audioprobe, so no ffmpeg,
# MediaInfo or dovi_tool are required.
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    wget \
    unzip \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Download and install hdrprobe (prebuilt x86_64 Linux binary)
RUN wget -q "https://github.com/matthane/hdrprobe/releases/download/v${HDRPROBE_VERSION}/hdrprobe-${HDRPROBE_VERSION}-x86_64-unknown-linux-gnu.tar.gz" -O /tmp/hdrprobe.tar.gz \
    && mkdir -p /tmp/hdrprobe \
    && tar -xzf /tmp/hdrprobe.tar.gz -C /tmp/hdrprobe \
    && install -m 0755 "$(find /tmp/hdrprobe -type f -name hdrprobe | head -n1)" /usr/local/bin/hdrprobe \
    && rm -rf /tmp/hdrprobe /tmp/hdrprobe.tar.gz

# Download and install audioprobe (prebuilt static musl binary, runs on any glibc)
RUN wget -q "https://github.com/CE-Repo/audioprobe/releases/download/v${AUDIOPROBE_VERSION}/audioprobe-x86_64-unknown-linux-musl.zip" -O /tmp/audioprobe.zip \
    && mkdir -p /tmp/audioprobe \
    && unzip -q /tmp/audioprobe.zip -d /tmp/audioprobe \
    && install -m 0755 "$(find /tmp/audioprobe -type f -name audioprobe | head -n1)" /usr/local/bin/audioprobe \
    && rm -rf /tmp/audioprobe /tmp/audioprobe.zip

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
