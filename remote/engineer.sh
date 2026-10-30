#!/bin/sh
# Engineer's laptop in the tailnet: a twin-only SSH key (made on first start, shared with the AI
# box through a volume) and the router's subnet route to the pole's LAN.
set -eu
[ -f /keys/engineer ] || ssh-keygen -q -t ed25519 -N "" -C "twin engineer" -f /keys/engineer
ip route replace 192.168.10.0/24 via 100.64.0.1
exec sleep infinity
