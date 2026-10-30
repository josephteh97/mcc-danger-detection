"""Twin-side helper on the v11 AI box (not part of app/): pushes a live-view snapshot every 2 s
to the cloud relay. The connection is outbound, as on the pole; nothing listens on 4G."""
import os
import subprocess
import time
import urllib.request

URL = os.environ.get("CAMERA_URL", "rtsp://192.168.10.20:8554/stream1")
RELAY = os.environ.get("CLOUD_RELAY", "http://172.30.4.11:8090/live")


def frames():
    cmd = ["ffmpeg", "-loglevel", "error", "-rtsp_transport", "tcp", "-i", URL, "-vf", "fps=0.5,scale=640:-2",
           "-f", "image2pipe", "-c:v", "mjpeg", "-q:v", "6", "-"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    buf = b""
    while True:
        chunk = p.stdout.read(65536)
        if not chunk:
            return
        buf += chunk
        while (start := buf.find(b"\xff\xd8")) >= 0 and (end := buf.find(b"\xff\xd9", start)) >= 0:
            yield buf[start:end + 2]
            buf = buf[end + 2:]


while True:
    try:
        for jpg in frames():
            req = urllib.request.Request(RELAY, data=jpg, method="POST", headers={"Content-Type": "image/jpeg"})
            try:
                urllib.request.urlopen(req, timeout=5).read()
            except OSError:
                pass
    except Exception:
        pass
    time.sleep(2)
