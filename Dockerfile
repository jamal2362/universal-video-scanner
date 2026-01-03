FROM ubuntu:22.04

# Prevent interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Install dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    mediainfo \
    python3 \
    python3-pip \
    wget \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Download and install dovi_tool
RUN wget https://github.com/quietvoid/dovi_tool/releases/download/2.3.1/dovi_tool-2.3.1-x86_64-unknown-linux-musl.tar.gz \
    && tar -xzf dovi_tool-2.3.1-x86_64-unknown-linux-musl.tar.gz \
    && mv dovi_tool /usr/local/bin/ \
    && chmod +x /usr/local/bin/dovi_tool \
    && rm dovi_tool-2.3.1-x86_64-unknown-linux-musl.tar.gz

# Set working directory
WORKDIR /data/app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy application files
COPY app.py .
COPY config.py .
COPY services/ ./services/
COPY utils/ ./utils/
COPY watchers/ ./watchers/

# Copy static and templates folders to /data/app
COPY static /data/app/static
COPY templates /data/app/templates

# Set permissions for static and templates folders
RUN chmod -R 755 /data/app/static /data/app/templates

# Create media directory
RUN mkdir -p /media

# Expose port
EXPOSE 2367

# Run the application
CMD ["python3", "app.py"]
