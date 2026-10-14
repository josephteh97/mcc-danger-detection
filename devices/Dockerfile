# Device emulators (laser arm, relay board) behind socat TCP bridges = the USB cables.
FROM python:3.12-slim-bookworm
ENV PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends socat procps && rm -rf /var/lib/apt/lists/*
WORKDIR /twin
COPY devices/ devices/
