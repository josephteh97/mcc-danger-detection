#!/usr/bin/env bash
# Share the twin's dashboard with people on other machines through a Microsoft Dev Tunnel.
#
#   ./share.sh start [--repo <owner/repo>] [--org <github-org>]... [--tenant] [--owner-only]
#                    [--expires <1h..30d>]
#   ./share.sh status
#   ./share.sh stop
#
# The tunnel has one port, 8080 (the dashboard), and always requires sign-in. MQTT, RTSP, HLS,
# the serial bridges, ground truth and the trial control port 9200 are never put on it: remote
# viewers reach the twin only through the dashboard, which also serves the camera video to the
# browser. Options that would allow anonymous access are refused, and `start` takes the tunnel
# down again if an anonymous request gets through.
set -euo pipefail

PORT=8080                                   # the only port this script ever hosts
LABEL=twin-dashboard                        # marks the tunnels it creates
LOCAL="http://127.0.0.1:$PORT"
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
STATE="$ROOT/.share"                        # tunnel id, url, host pid and log (git-ignored)
DEVTUNNEL=${DEVTUNNEL:-$(command -v devtunnel || echo "$HOME/bin/devtunnel")}

say()  { printf '%s\n' "$*"; }
fail() { printf 'share.sh: %s\n' "$*" >&2; exit 1; }
dt()   { "$DEVTUNNEL" "$@"; }
json() {                    # evaluate a Python expression over the JSON on stdin (as d); one line on failure
  python3 -c '
import json, sys
try: d = json.load(sys.stdin); print(eval(sys.argv[1]))
except (ValueError, KeyError, TypeError) as e: sys.exit("share.sh: devtunnel returned no usable JSON (%s)" % type(e).__name__)' "$1"
}
optval() {                  # $1 option, $2 its value, $3 an example; a missing value or another flag is refused
  [[ -n "$2" && "$2" != -* ]] || fail "$1 needs a value, for example $1 $3"
}
lock() {                    # one start or stop at a time (locks this script file; no extra state)
  command -v flock >/dev/null || return 0
  exec 9<"${BASH_SOURCE[0]}"
  flock -n 9 || fail "another ./share.sh start or stop is running"
}

usage() {
  cat >&2 <<EOF
Usage: ./share.sh start [--repo <owner/repo>] [--org <github-org>]... [--tenant] [--owner-only]
                        [--expires <1h..30d>]
       ./share.sh status
       ./share.sh stop
EOF
  exit 2
}

# ------------------------------------------------------------------ preconditions
need_dashboard() {
  curl -fsS -m 5 -o /dev/null "$LOCAL/healthz" 2>/dev/null || fail "the dashboard is not answering on $LOCAL.
  Start the stack first:  docker compose up -d --build"
}

need_devtunnel() {
  [ -x "$DEVTUNNEL" ] || fail "devtunnel is not installed.
  Install it:   curl -sL https://aka.ms/DevTunnelCliInstall | bash
  Then log in:  devtunnel user login -g"
}

logged_in() { dt user show 2>/dev/null | grep -q '^Logged in as'; }

need_login() {
  logged_in || fail "devtunnel is not logged in ($(dt user show 2>&1 | head -1)).
  Log in with GitHub:  devtunnel user login -g     (add -d on a machine without a browser)"
}

warn_if_lan_exposed() {     # the tunnel adds sign-in; a dashboard on 0.0.0.0 would bypass it
  command -v ss >/dev/null || return 0
  local open
  open=$(ss -Hltn "sport = :$PORT" 2>/dev/null | awk '{print $4}' | grep -vE '^(127\.0\.0\.1|\[::1\]):' || true)
  [ -z "$open" ] || say "WARNING: the dashboard also listens on $(echo $open), so anyone on your network can use it
         without signing in. Restart the stack without DASHBOARD_BIND to keep it on 127.0.0.1."
}

# ------------------------------------------------------------------ state
tunnel_id()  { cat "$STATE/tunnel" 2>/dev/null; }
tunnel_url() { cat "$STATE/url" 2>/dev/null; }
host_pid() {                # the recorded host process, only while it is still 'devtunnel host'
  local pid
  pid=$(cat "$STATE/host.pid" 2>/dev/null) || return 1
  ps -ww -p "$pid" -o args= 2>/dev/null | grep -qF -- "$DEVTUNNEL host " && echo "$pid"
}

stop_host() {
  local pid
  pid=$(host_pid) || return 0
  kill "$pid" 2>/dev/null || true
  for _ in $(seq 1 50); do kill -0 "$pid" 2>/dev/null || break; sleep 0.1; done
  kill -9 "$pid" 2>/dev/null || true
  say "Stopped hosting (pid $pid)."
}

abort_start() {             # EXIT trap while start is half done: stop the host, delete the tunnel
  set +e; trap - EXIT       # best effort from here: one failed write must not skip the rest
  local id; id=$(tunnel_id)
  [ -s "$STATE/host.log" ] && { echo "--- last lines of .share/host.log"; tail -20 "$STATE/host.log"; } >&2
  echo "Start failed; removing tunnel $id." >&2
  stop_host >&2
  if [ -z "$id" ] || delete_tunnel "$id" >&2; then rm -rf "$STATE"
  else echo "Kept .share/ so that ./share.sh stop can retry deleting $id." >&2; fi
}

delete_tunnel() {           # 0 when the tunnel is gone afterwards
  local out
  if out=$(dt delete "$1" -f 2>&1); then say "Deleted tunnel $1."
  elif grep -qi 'not found' <<<"$out"; then say "Tunnel $1 was already gone."
  else printf '%s\n' "$out" >&2; return 1; fi
}

leftovers() {               # twin tunnels in this account that the state does not know about
  logged_in || return 0
  local ids
  ids=$(dt list --labels "$LABEL" -j 2>/dev/null \
        | json '" ".join(t["tunnelId"] for t in d.get("tunnels", []))' 2>/dev/null || true)
  ids=$(for i in $ids; do [ "$i" = "$(tunnel_id || true)" ] || echo "$i"; done)
  [ -z "$ids" ] || say "Leftover twin tunnel(s) from an earlier run: $(echo $ids)
  Delete with:  $(for i in $ids; do printf 'devtunnel delete %s -f; ' "$i"; done)"
}

# ------------------------------------------------------------------ checks through the tunnel
anonymous_check() {         # prints a verdict; returns 0 if sign-in is required, 1 if open, 2 if unknown
  local out code="no response" body try
  for try in 1 2 3 4 5; do  # a fresh host can answer 502 or time out at first
    [ "$try" = 1 ] || sleep 2
    out=$(curl -sS -m 20 -w '\n%{http_code}' "$1/healthz" 2>/dev/null) || { code="no response"; continue; }
    code=${out##*$'\n'}; body=${out%$'\n'*}
    if [ "$code" = 200 ] && [ "$body" = ok ]; then
      echo "OPEN: an anonymous request reached the dashboard"; return 1
    fi
    case "$code" in
      302|307|401|403) echo "required: an anonymous request gets HTTP $code, not the dashboard"; return 0 ;;
    esac
    code="HTTP $code"
  done
  echo "could not verify sign-in through $1 (last answer: $code)"; return 2
}

signed_in_check() {         # the page, the API and the browser video, as a client with a connect token
  local token hdr playlist
  token=$(dt token "$1" --scopes connect -j 2>/dev/null | json 'd["token"]' 2>/dev/null) \
    || { echo "could not get a connect token to check"; return 1; }
  hdr="X-Tunnel-Authorization: tunnel $token"           # sent on stdin, never on a command line
  printf '%s\n' "$hdr" | curl -fsS -m 20 -H @- -o /dev/null "$2/" 2>/dev/null \
    || { echo "the dashboard page did not load through the tunnel"; return 1; }
  playlist=$(printf '%s\n' "$hdr" | curl -fsS -m 20 -H @- "$2/video/stream1/index.m3u8" 2>/dev/null) \
    && grep -q '^#EXTM3U' <<<"$playlist" \
    || { echo "the video stream did not load through the tunnel"; return 1; }
  echo "the dashboard and its video stream load through the tunnel"
}

# ------------------------------------------------------------------ commands
show() {                    # returns 1 if an anonymous request reached the dashboard
  local id=$1 url=$2 pid=$3 verdict open=0
  say "  URL       $url"
  say "  Tunnel    $id (host pid $pid, log .share/host.log)"
  if logged_in; then
    say "  Ports     $(dt port list "$id" -j | json '", ".join("%s (%s)" % (p["portNumber"], p.get("protocol", "")) for p in d.get("ports", []))')"
    say "  Access"
    dt access list "$id" | tail -n +2 | sed 's/^/            /'
  else
    say "  Ports and access rules: log in to see them (devtunnel user login -g)"
  fi
  verdict=$(anonymous_check "$url") || { [ $? != 1 ] || open=1; }
  say "  Sign-in   $verdict"
  logged_in && say "  Check     $(signed_in_check "$id" "$url" || true)"
  warn_if_lan_exposed
  return "$open"
}

cmd_start() {
  local repo="" tenant=0 owner_only=0 expires="" orgs=() given=$#
  while [ $# -gt 0 ]; do
    case "$1" in
      --repo)       optval "$1" "${2:-}" owner/repo; repo=$2; shift 2 ;;
      --org)        optval "$1" "${2:-}" my-github-org; orgs+=("$2"); shift 2 ;;
      --tenant)     tenant=1; shift ;;
      --owner-only) owner_only=1; shift ;;
      --expires)    optval "$1" "${2:-}" 8h; expires=$2; shift 2 ;;
      -a|--allow-anonymous|--anonymous)
        fail "anonymous access is never allowed: the dashboard can inject faults, move workers and
  control Docker on this host. Viewers sign in instead; widen access with --org or --tenant." ;;
      *) usage ;;
    esac
  done
  if [ -n "$expires" ]; then  # devtunnel accepts 1h to 30d, but only checks once the tunnel exists
    local hours=0 per=1
    if [[ "$expires" =~ ^([0-9]{1,4})([hd])$ ]]; then
      [ "${BASH_REMATCH[2]}" = h ] || per=24
      hours=$((10#${BASH_REMATCH[1]} * per))
    fi
    (( hours >= 1 && hours <= 720 )) || fail "--expires takes 1h to 30d, for example 8h or 2d"
  fi
  # No default repo rule: devtunnel 1.0.2115 and earlier reject every --repo rule (design D16).
  if [ "$owner_only" = 1 ]; then
    [ -z "$repo" ] && [ ${#orgs[@]} = 0 ] && [ "$tenant" = 0 ] || fail "--owner-only cannot be combined with --repo, --org or --tenant"
  fi

  need_dashboard
  need_devtunnel
  need_login

  local pid id url
  if pid=$(host_pid); then
    [ "$given" = 0 ] || fail "already sharing, so these options would not apply. To change who can sign in
  or the expiry, run ./share.sh stop first."
    say "Already sharing; no new tunnel created."
    show "$(tunnel_id)" "$(tunnel_url)" "$pid" || {
      cmd_stop >&2
      fail "the running tunnel let an anonymous request through, so it has been taken down"
    }
    return 0
  fi
  if id=$(tunnel_id); then  # a host that died earlier: remove its tunnel, then start clean
    say "Removing the tunnel left by an earlier run ($id)."
    delete_tunnel "$id" || fail "could not delete the old tunnel $id"
  fi
  rm -rf "$STATE"; mkdir -p "$STATE"

  # Choose the id first and record it before creating, so the trap can clean up from here on.
  local out
  id="twin-$(date +%s)-$RANDOM"
  echo "$id" > "$STATE/tunnel"
  trap abort_start EXIT
  out=$(dt create "$id" --labels "$LABEL" -d "Danger-zone twin dashboard (share.sh)" ${expires:+--expiration "$expires"} \
        -j 2>"$STATE/err") || fail "could not create a tunnel: $(cat "$STATE/err")"
  id=$(json 'd["tunnel"]["tunnelId"]' <<<"$out")          # the full id, with its cluster suffix
  echo "$id" > "$STATE/tunnel"

  dt port create "$id" -p "$PORT" --protocol http >/dev/null
  local who=("the tunnel owner (you)")
  if [ -n "$repo" ]; then
    out=$(dt access create "$id" --repo "$repo" ${expires:+-e "$expires"} 2>&1) || fail "could not add the access rule for $repo:
$(head -3 <<<"$out")
  devtunnel 1.0.2115 and earlier reject --repo rules. Share without it: ./share.sh start (only you can
  sign in), or use --org <github-org> / --tenant"
    who+=("GitHub accounts with access to $repo")
  fi
  for org in "${orgs[@]}"; do
    dt access create "$id" --org "$org" ${expires:+-e "$expires"} >/dev/null
    who+=("members of the GitHub organization $org")
  done
  if [ "$tenant" = 1 ]; then
    dt access create "$id" --tenant ${expires:+-e "$expires"} >/dev/null
    who+=("accounts in your Microsoft Entra tenant")
  fi

  local ports anon
  ports=$(dt port list "$id" -j | json '" ".join(str(p["portNumber"]) for p in d.get("ports", []))')
  [ "$ports" = "$PORT" ] || fail "the tunnel has ports '$ports'; only $PORT may be shared"
  anon=$(dt access list "$id" -j | json 'sum(1 for e in d.get("accessControlEntries", []) if e.get("type") == "Anonymous" and not e.get("isDeny"))')
  [ "$anon" = 0 ] || fail "the tunnel has an anonymous access rule; refusing to share"

  nohup setsid "$DEVTUNNEL" host "$id" > "$STATE/host.log" 2>&1 < /dev/null 9<&- &   # 9<&-: not the lock
  echo $! > "$STATE/host.pid"
  local ready=0                                         # failures print host.log from abort_start
  for _ in $(seq 1 60); do
    url=$(grep -oE "https://[^ ,]+-$PORT\.[^ ,]+devtunnels\.ms" "$STATE/host.log" | head -1 || true)
    [ -n "$url" ] && grep -q 'Ready to accept connections' "$STATE/host.log" && { ready=1; break; }
    host_pid >/dev/null || fail "devtunnel host exited"
    sleep 0.5
  done
  [ "$ready" = 1 ] || fail "devtunnel host was not ready after 30 s"
  echo "$url" > "$STATE/url"

  local verdict check
  verdict=$(anonymous_check "$url") || fail "refusing to share: $verdict"
  check=$(signed_in_check "$id" "$url") || fail "$check"
  trap - EXIT

  say "Sharing the dashboard (port $PORT only). Open this on the other machine and sign in:"
  say ""
  say "  $url"
  say ""
  say "  Who       $(IFS=';'; echo "${who[*]}" | sed 's/;/; /g')"
  say "  Expires   ${expires:+access rules and tunnel after $expires}${expires:-when you run ./share.sh stop}"
  say "  Sign-in   $verdict"
  say "  Check     $check"
  warn_if_lan_exposed
  say "Stop sharing with ./share.sh stop"
}

cmd_status() {
  local id url pid
  if ! id=$(tunnel_id); then
    say "Sharing is off."
    leftovers
    return 0
  fi
  url=$(tunnel_url || true)
  if ! pid=$(host_pid); then
    say "Sharing is off: the host process has stopped, but tunnel $id still exists."
    say "Run ./share.sh stop to delete it (last lines of .share/host.log follow)."
    tail -5 "$STATE/host.log" 2>/dev/null | sed 's/^/  /'
    return 1
  fi
  say "Sharing is on."
  show "$id" "$url" "$pid" || true            # status reports an open tunnel; start takes it down
}

cmd_stop() {
  local id url
  if ! id=$(tunnel_id); then
    say "Nothing is shared."
    leftovers
    return 0
  fi
  url=$(tunnel_url || true)
  stop_host
  need_devtunnel
  delete_tunnel "$id" || fail "could not delete tunnel $id. Nothing hosts it any more, so its URL no longer
  reaches the dashboard. Log in (devtunnel user login -g) and run ./share.sh stop again to delete it."
  rm -rf "$STATE"
  if [ -n "$url" ]; then
    say "The old URL now answers HTTP $(curl -s -o /dev/null -m 20 -w '%{http_code}' "$url/healthz" || true)."
  fi
  leftovers
}

case "${1:-}" in
  start)  shift; lock; cmd_start "$@" ;;
  status) shift; [ $# = 0 ] || usage; cmd_status ;;
  stop)   shift; [ $# = 0 ] || usage; lock; cmd_stop ;;
  *)      usage ;;
esac
