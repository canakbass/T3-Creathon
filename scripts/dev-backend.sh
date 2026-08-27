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

# Port'u DINLEYEN surecin pid'i (yoksa bos ciktı).
#
# NEDEN GEREKLI: "port bos mu" sorusunu curl ile sormak yaniltici. Porttaki
# yabanci bir surec de curl'e 200 doner; betik onu kendi sunucumuz sanar.
# `|| true`: port BOSSA grep hicbir sey bulmaz ve 1 doner; `set -e` +
# `pipefail` altinda bu, betigi sessizce sonlandirirdi (hicbir cikti
# vermeden "exit 1"). Bos sonuc burada bir hata degil, beklenen cevap.
port_sahibi() {
  if command -v ss >/dev/null 2>&1; then
    ss -lptnH "sport = :$1" 2>/dev/null | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2 || true
  elif command -v lsof >/dev/null 2>&1; then
    lsof -tiTCP:"$1" -sTCP:LISTEN 2>/dev/null | head -1 || true
  fi
}

# CALISAN SUNUCUNUN VERI TABANI SILINMIS MI?
#
# NEDEN VAR: "sunucu acikken sql_app.db'yi sil" bu projede IKI KEZ zaman
# kaybettirdi. SQLite acik dosya tanitici uzerinden calisiyor; dosya
# silinince surec SILINMIS inode'a yazmaya devam ediyor ve her yazma
# "attempt to write a readonly database" ile patliyor. Sunucu ayakta,
# istekler geliyor, GET'ler bile calisiyor - yalnizca yazma islemleri 500
# veriyor. Hata mesaji da sebebi soylemiyor.
#
# Dogru sira HER ZAMAN: once stop, sonra sil, sonra start.
veritabani_silinmis_mi() {
  local pid="$1"
  [[ -z "$pid" ]] && return 0
  if command -v lsof >/dev/null 2>&1 &&
     lsof -p "$pid" 2>/dev/null | grep -q "sql_app.db (deleted)"; then
    echo ""
    echo "!! DIKKAT: calisan sunucu SILINMIS bir veri tabani dosyasi tutuyor."
    echo "   Her YAZMA islemi 'readonly database' ile 500 verecek."
    echo "   Cozum:  $0 restart"
    echo ""
    return 1
  fi
  return 0
}

baslat() {
  if [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    echo "zaten calisiyor (pid $(cat "$PIDFILE"))"
    veritabani_silinmis_mi "$(cat "$PIDFILE")"
    return 0
  fi

  # BASLAMADAN ONCE portu kontrol et. Yoksa yeni uvicorn "address already
  # in use" ile olur, ama porttaki ESKI surec isteklere cevap vermeye devam
  # ettigi icin her sey calisiyormus gibi gorunur - degistirdiginiz kodun
  # neden etki etmedigini saatlerce arayabilirsiniz.
  SAHIP="$(port_sahibi "$PORT")"
  if [[ -n "$SAHIP" ]]; then
    echo "port $PORT zaten kullaniliyor (pid $SAHIP) - bu betigin baslattigi"
    echo "bir surec DEGIL (pid dosyasi yok ya da eskimis)."
    echo "Kapatmak icin:  kill $SAHIP"
    return 1
  fi

  cd "$KOK/backend"
  nohup "$KOK/.venv/bin/python" -m uvicorn main:app --port "$PORT" > "$LOGFILE" 2>&1 &
  YENI_PID=$!
  echo "$YENI_PID" > "$PIDFILE"
  for _ in $(seq 1 60); do
    # SIRALAMA ONEMLI: once "surecimiz yasiyor mu", sonra "port cevap
    # veriyor mu".
    #
    # NEDEN: yalnizca curl'e bakan onceki hali YANLIS "hazir" veriyordu.
    # Porta baglanamayan uvicorn ("address already in use") hemen olur,
    # ama porttaki ESKI surec curl'e 200 dondurmeye devam eder. Betik
    # "hazir" der, oysa calisan sey yeni kod degil eski surectir - ustelik
    # veri tabani dosyasi silinmisse o eski surec artik var olmayan bir
    # inode'a yazmaya calisip her istege "disk I/O error" verir.
    if ! kill -0 "$YENI_PID" 2>/dev/null; then
      echo "sunucu basladiktan hemen sonra oldu. log:"
      tail -20 "$LOGFILE"
      rm -f "$PIDFILE"
      return 1
    fi
    if curl -s -o /dev/null "http://127.0.0.1:$PORT/"; then
      echo "hazir: http://127.0.0.1:$PORT (pid $YENI_PID)"
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
