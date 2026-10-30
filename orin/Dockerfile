# Orin sandbox. Fast mode (default): ubuntu:22.04 on x86.
# JetPack mode: docker build --platform linux/arm64 --build-arg BASE=nvcr.io/nvidia/l4t-jetpack:<tag> -f orin/Dockerfile .
ARG BASE=ubuntu:22.04
FROM ${BASE}
ENV DEBIAN_FRONTEND=noninteractive TZ=Asia/Singapore PYTHONUNBUFFERED=1
# 'pulseaudio' (the daemon) is added to the guide's list: 'pulseaudio-utils' has only the clients.
RUN apt-get update && apt-get install -y --no-install-recommends \
      python3-pip python3-numpy socat iproute2 openssh-server pulseaudio pulseaudio-utils alsa-utils ffmpeg tzdata \
    && rm -rf /var/lib/apt/lists/*
COPY app/requirements.txt /tmp/
RUN pip3 install --no-cache-dir -r /tmp/requirements.txt
COPY app/ /opt/pole/app/
COPY orin/horn_monitor.py orin/relay_push.py /opt/pole/twin/
COPY orin/entrypoint.sh /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
