# v11 remote management, emulated (no real Tailscale or cloud service; every network is internal):
# the 4G router's Tailscale node, an engineer and a superior client, and the cloud relay.
FROM python:3.12-alpine
RUN apk add --no-cache iptables iproute2 openssh-client netcat-openbsd curl mosquitto-clients
WORKDIR /remote
COPY remote/ /remote/
