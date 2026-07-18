FROM python:3.12-slim

# ffmpeg is not in the base image — this is the exact gap that was failing locally
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Ephemeral-safe: write downloads to /tmp so it doesn't matter if the
# filesystem gets wiped on redeploy — this folder isn't meant to persist.
RUN mkdir -p /tmp/downloads

EXPOSE 5000

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--timeout", "120", "app:app"]
