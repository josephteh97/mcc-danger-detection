# Dashboard: FastAPI on 8080 (3D view, video proxy, scenarios, products, faults, trial pad).
FROM python:3.12-slim-bookworm
ENV PYTHONUNBUFFERED=1
RUN pip install --no-cache-dir "fastapi>=0.110" "uvicorn[standard]>=0.29" "docker>=7.0" "paho-mqtt>=2.0" \
      "httpx>=0.27" "pyyaml>=6.0" "numpy>=1.26" "opencv-python-headless>=4.9"
WORKDIR /twin
COPY site.yaml ./
COPY app/ app/
COPY catalog/ catalog/
COPY world/ world/
COPY devices/ devices/
COPY tools/ tools/
COPY dashboard/ dashboard/
EXPOSE 8080
CMD ["uvicorn", "dashboard.server:app", "--host", "0.0.0.0", "--port", "8080", "--log-level", "warning"]
