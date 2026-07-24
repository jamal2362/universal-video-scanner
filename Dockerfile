FROM ubuntu:24.04

# Prevent interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Install dependencies
# The `7zip` package (7-Zip 23.01+) provides the `7z` binary used to list and
# extract the main-feature .m2ts sample + playlist from Blu-ray disc images
# (.iso) for reliable MediaInfo analysis. It is required over the legacy
# p7zip 16.02 (Ubuntu 22.04) because that release cannot read the UDF 2.50
# file system of UHD Blu-ray images - extraction then fails silently and audio
# codec/bitrate detection falls back to an unusable raw-.iso probe.
RUN apt-get update && apt-get install -y \
    mediainfo \
    7zip \
    python3 \
    python3-pip \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Download and install hdrprobe
RUN wget https://github.com/matthane/hdrprobe/releases/download/v0.8.0/hdrprobe-0.8.0-linux-x64-static.tar.gz -O /tmp/hdrprobe.tar.gz \
    && mkdir -p /tmp/hdrprobe \
    && tar -xzf /tmp/hdrprobe.tar.gz -C /tmp/hdrprobe \
    && find /tmp/hdrprobe -type f -name hdrprobe -exec mv {} /usr/local/bin/hdrprobe \; \
    && chmod +x /usr/local/bin/hdrprobe \
    && rm -rf /tmp/hdrprobe /tmp/hdrprobe.tar.gz

# Set working directory
WORKDIR /app

# Copy requirements and install Python dependencies
# Ubuntu 24.04 ships a PEP 668 "externally-managed" Python, so allow pip to
# install into the system environment inside this (already isolated) container.
COPY requirements.txt .
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

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
