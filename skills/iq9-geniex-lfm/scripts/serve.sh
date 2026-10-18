#!/usr/bin/env bash
# serve.sh: start, stop, restart, or check `geniex serve` on the IQ-9075.
#
#   serve.sh start [--keepalive SECONDS] [--compute npu|hybrid|cpu|gpu]   default: npu, 1800 s
#   serve.sh stop
#   serve.sh restart [...same flags as start]
#   serve.sh status
#
# Why a script: the `geniex` on PATH is a launcher, so `kill $!` does not reach the server (measured).
# This stops whatever process holds the port. The server log goes to $GENIEX_SERVE_LOG
# (default /tmp/geniex-serve.log) at --log info, which shows the device in use ("Using 1 device(s): HTP0").

set -euo pipefail

PORT="${GENIEX_PORT:-18181}"
LOG="${GENIEX_SERVE_LOG:-/tmp/geniex-serve.log}"
URL="http://127.0.0.1:$PORT"

pid_on_port() {
  ss -ltnp 2>/dev/null | sed -n "s/.*127.0.0.1:$PORT .*pid=\([0-9]*\).*/\1/p" | head -1
}

up() { curl -s -o /dev/null -m 3 "$URL/v1/models"; }

start() {
  local keepalive=1800 compute=npu
  while [ $# -gt 0 ]; do
    case "$1" in
      --keepalive) keepalive="$2"; shift 2 ;;
      --compute) compute="$2"; shift 2 ;;
      *) echo "unknown flag: $1" >&2; exit 64 ;;
    esac
  done
  if up; then echo "already running on $URL (pid $(pid_on_port))"; return 0; fi
  command -v geniex >/dev/null || { echo "geniex not on PATH" >&2; exit 1; }
  nohup geniex serve --compute "$compute" --keepalive "$keepalive" --log info > "$LOG" 2>&1 &
  for _ in $(seq 1 60); do
    if up; then echo "started on $URL (pid $(pid_on_port), compute=$compute, keepalive=${keepalive}s, log=$LOG)"; return 0; fi
    sleep 1
  done
  echo "geniex serve did not answer within 60 s; see $LOG" >&2
  exit 1
}

stop() {
  local pid
  pid="$(pid_on_port)"
  if [ -z "$pid" ]; then echo "not running"; return 0; fi
  kill "$pid"
  for _ in $(seq 1 15); do
    [ -z "$(pid_on_port)" ] && { echo "stopped (pid $pid)"; return 0; }
    sleep 1
  done
  echo "pid $pid did not exit; try: kill -9 $pid" >&2
  exit 1
}

status() {
  if up; then
    echo "running on $URL (pid $(pid_on_port))"
    if [ -f "$LOG" ]; then
      grep -a "Using .* device(s)" "$LOG" | tail -1 | sed 's/.*resolve_devices\] /  device: /' || true
    fi
    curl -s -m 5 "$URL/v1/models" | python3 -c 'import json,sys; [print("  model:", m["id"]) for m in json.load(sys.stdin)["data"]]'
  else
    echo "not running"
    return 3
  fi
}

cmd="${1:-status}"; shift || true
case "$cmd" in
  start) start "$@" ;;
  stop) stop ;;
  restart) stop; start "$@" ;;
  status) status ;;
  *) echo "usage: serve.sh start|stop|restart|status" >&2; exit 64 ;;
esac
