#!/usr/bin/env bash
# Gelistirme sunucusunu baslatir/durdurur.
#
# NEDEN PID DOSYASI: `pkill -f uvicorn` gibi desen eslesmeleri, komutu
# calistiran KABUGUN kendisini de eslestirip onu da olduruyor (komut satiri
# metninde "uvicorn" gectigi icin). PID'i dosyaya yazmak bu tuzagi
# tamamen ortadan kaldiriyor.
#
# Kullanim:
#   scripts/dev-backend.sh start [port]
#   scripts/dev-backend.sh stop
#   scripts/dev-backend.sh restart [port]
set -euo pipefail

KOK="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PIDFILE="$KOK/.dev-backend.pid"
LOGFILE="${DEV_BACKEND_LOG:-$KOK/.dev-backend.log}"
PORT="${2:-8000}"

durdur() {
  if [[ -f "$PIDFILE" ]]; then
    PID="$(cat "$PIDFILE")"
    if kill -0 "$PID" 2>/dev/null; then
      kill "$PID" 2>/dev/null || true
      for _ in $(seq 1 20); do
        kill -0 "$PID" 2>/dev/null || break
        sleep 0.25
      done
      kill -9 "$PID" 2>/dev/null || true
      echo "durduruldu (pid $PID)"
    fi
    rm -f "$PIDFILE"
  else
    echo "calisan sunucu kaydi yok"
  fi
}

baslat() {
  if [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    echo "zaten calisiyor (pid $(cat "$PIDFILE"))"
    return 0
  fi
  cd "$KOK/backend"
  nohup "$KOK/.venv/bin/python" -m uvicorn main:app --port "$PORT" > "$LOGFILE" 2>&1 &
  echo $! > "$PIDFILE"
  for _ in $(seq 1 60); do
    if curl -s -o /dev/null "http://127.0.0.1:$PORT/"; then
      echo "hazir: http://127.0.0.1:$PORT (pid $(cat "$PIDFILE"))"
      return 0
    fi
    sleep 0.5
  done
  echo "sunucu acilmadi, log:"
  tail -20 "$LOGFILE"
  return 1
}

case "${1:-start}" in
  start)   baslat ;;
  stop)    durdur ;;
  restart) durdur; baslat ;;
  *) echo "kullanim: $0 {start|stop|restart} [port]"; exit 2 ;;
esac
