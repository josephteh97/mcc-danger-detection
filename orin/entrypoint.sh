#!/bin/sh
# Orin sandbox: plug in the virtual USB cables, start the audio device, then start the app.
set -u

plug() {   # $1 = device path, $2 = host:port of the far end; re-plugs after the cable comes back
  while true; do
    socat "PTY,link=$1,raw,echo=0" "TCP:$2" 2>/dev/null
    sleep 1
  done
}
plug /dev/ttyARM devices:7001 &
plug /dev/ttyRELAY devices:7002 &

# PulseAudio with a null sink named 'horn' (the guide's 'pulseaudio --start' refuses to run as root)
export PULSE_SERVER=unix:/tmp/pulse/native
mkdir -p /tmp/pulse
pulseaudio --daemonize=yes --exit-idle-time=-1 --disallow-exit -n \
  --load="module-null-sink sink_name=horn" \
  --load="module-native-protocol-unix auth-anonymous=1 socket=/tmp/pulse/native" >/dev/null 2>&1
for i in $(seq 1 50); do pactl info >/dev/null 2>&1 && break; sleep 0.1; done

if [ "${TWIN_HORN_MONITOR:-0}" = "1" ]; then
  python3 /opt/pole/twin/horn_monitor.py >> /data/horn.log 2>/dev/null &
fi

cd /opt/pole
exec python3 -m app.main --config /opt/pole/app/config.yaml
