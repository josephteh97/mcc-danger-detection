# World simulator + ffmpeg encoder; also runs the one-shot calibration step.
FROM python:3.12-slim-bookworm
ENV PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir "numpy>=1.26" "opencv-python-headless>=4.9" "pyyaml>=6.0"
WORKDIR /twin
COPY site.yaml ./
COPY app/ app/
COPY catalog/ catalog/
COPY world/ world/
COPY tools/__init__.py tools/calibrate.py tools/
CMD ["sh", "world/entrypoint.sh"]
