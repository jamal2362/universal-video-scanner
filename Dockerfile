FROM ubuntu:22.04

# Prevent interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Install dependencies
# p7zip-full provides the `7z` binary used to extract a main-feature .m2ts
# sample from Blu-ray disc images (.iso) for reliable MediaInfo analysis.
RUN apt-get update && apt-get install -y \
    mediainfo \
    p7zip-full \
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
