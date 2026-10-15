#!/bin/sh
# World container: the renderer draws the camera's view and ffmpeg is the camera's sensor and
# encoder. This is a script, not a compose 'command:', because YAML folding and Compose's own
# word-splitting broke the guide's inline version. The pipeline restarts if either end exits.
#   WEATHER and SCENARIO pick the start-up preset and scenario (both switch live afterwards).
set -u
while true; do
  # Frames go to the camera's sim_ctrl address: the renderer is its sensor, not a PoE cable,
  # so unplugging the camera from poe_lan cuts only the Orin's view.
  # -pix_fmt yuv420p: libx264 would otherwise encode the BGR input as 4:4:4, which browsers
  # cannot decode.
  python3 world/world.py --fps 15 --truth dashboard:9100,192.168.10.2:9100 \
      --weather "${WEATHER:-clear}" --scenario "${SCENARIO:-demo_loop}" \
      --control 0.0.0.0:9200 --arm-state /logs/arm.jsonl |
    ffmpeg -loglevel error -f rawvideo -pix_fmt bgr24 -s 1280x720 -r 15 -i - \
      -c:v libx264 -preset ultrafast -tune zerolatency -pix_fmt yuv420p -g 15 \
      -f rtsp -rtsp_transport tcp rtsp://172.29.10.20:8554/stream1
  sleep 1
done
