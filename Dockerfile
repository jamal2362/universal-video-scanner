FROM debian:13-slim

# Prevent interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Install dependencies
# The `7zip` package (Debian trixie) provides the `7z` binary used to list and
# extract the main-feature .m2ts sample + playlist from Blu-ray disc images
# (.iso) for reliable MediaInfo analysis. It reads the UDF 2.50 file system of
# UHD Blu-ray images that the legacy p7zip 16.02 cannot - without it extraction
# fails silently and audio codec/bitrate detection falls back to an unusable
# raw-.iso probe.
# ca-certificates is needed so the HTTPS downloads below (MediaArea repo key,
# hdrprobe release) can verify certificates (the slim base ships without it).
RUN apt-get update && apt-get install -y \
    7zip \
    python3 \
    python3-pip \
    wget \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install MediaInfo from MediaArea's official repository. Debian's own mediainfo
# package lags upstream, so track MediaArea directly (currently 26.05); apt then
# keeps it current on rebuilds.
RUN wget -qO /etc/apt/trusted.gpg.d/mediaarea.asc https://mediaarea.net/repo/deb/debian/pubkey.gpg \
    && echo "deb https://mediaarea.net/repo/deb/debian trixie main" > /etc/apt/sources.list.d/mediaarea.list \
    && apt-get update \
    && apt-get install -y mediainfo \
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
# Debian 13 ships a PEP 668 "externally-managed" Python, so allow pip to
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
