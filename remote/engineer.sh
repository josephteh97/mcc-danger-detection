#!/bin/sh
# Engineer's laptop in the tailnet: a twin-only SSH key (made on first start, shared with the AI
# box through a volume) and the router's subnet route to the pole's LAN, which Tailscale's
# userspace mode serves as a SOCKS5 proxy on the router node (100.64.0.1:1055).
set -eu
[ -f /keys/engineer ] || ssh-keygen -q -t ed25519 -N "" -C "twin engineer" -f /keys/engineer
mkdir -p /root/.ssh
cat > /root/.ssh/config <<'CFG'
Host 192.168.10.*
  ProxyCommand nc -X 5 -x 100.64.0.1:1055 %h %p
  IdentityFile /keys/engineer
  User root
  StrictHostKeyChecking no
  UserKnownHostsFile /dev/null
  BatchMode yes
  ConnectTimeout 10
CFG
exec sleep infinity
