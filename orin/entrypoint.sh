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

# PulseAudio with a null sink named 'horn' (the guide's line). As root it only warns that it is
# not meant to run as root; 'docker exec' sessions find the same daemon. A power cut here is
# 'docker kill' + 'docker start', which keeps /tmp where a real boot would clear it, and the old
# daemon's pid file then makes '--start' exit 0 without starting one: clear that state first.
rm -rf /tmp/pulse-* "$HOME"/.config/pulse/*-runtime
pulseaudio --start --exit-idle-time=-1 && pactl load-module module-null-sink sink_name=horn

if [ "${TWIN_HORN_MONITOR:-0}" = "1" ]; then
  python3 /opt/pole/twin/horn_monitor.py >> /data/horn.log 2>/dev/null &
fi

cd /opt/pole
exec python3 -m app.main --config /opt/pole/app/config.yaml
