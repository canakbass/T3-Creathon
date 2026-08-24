#!/usr/bin/env bash
# Commit'lenen dosyalarda gercek anahtar var mi diye bakar.
#
# NEDEN VAR: backend/.env.example git'te IZLENIYOR ve bir kez gercek bir
# Google API anahtari oraya yazilip commit'lendi. Ornek dosyalarin
# doldurulmasi kolay bir hata; bu betik onu yakaliyor.
#
# Kullanim:  scripts/check-secrets.sh
# Git kancasi olarak:  ln -s ../../scripts/check-secrets.sh .git/hooks/pre-commit
set -uo pipefail
KOK="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$KOK"

DESEN='AIza[0-9A-Za-z_-]{20,}|sb_secret_[0-9A-Za-z_-]{10,}|sk-ant-api[0-9A-Za-z_-]{10,}|eyJhbGciOi[0-9A-Za-z_.-]{40,}'
BULUNAN=0

while IFS= read -r f; do
  [ -f "$f" ] || continue
  if grep -qE "$DESEN" "$f" 2>/dev/null; then
    echo "GERCEK ANAHTAR SUPHESI: $f"
    grep -nE "$DESEN" "$f" | sed 's/\(.\{100\}\).*/\1.../' | head -3
    BULUNAN=1
  fi
done < <(git ls-files)

# .env.example dosyalarinda dolu deger var mi
while IFS= read -r f; do
  [ -f "$f" ] || continue
  if grep -qE '^[A-Z_]+=.+$' "$f" 2>/dev/null; then
    echo "ORNEK DOSYADA DOLU DEGER: $f"
    grep -nE '^[A-Z_]+=.+$' "$f" | head -5
    BULUNAN=1
  fi
done < <(git ls-files | grep -E '\.env.*example')

if [ "$BULUNAN" -eq 0 ]; then
  echo "temiz: commit'lenen dosyalarda anahtar bulunamadi"
else
  echo ""
  echo "Gercek degerler .env / .env.local dosyalarina yazilir (bunlar gitignore'da)."
  echo ".env.example bir SABLONDUR; degerleri BOS kalmali."
fi
exit "$BULUNAN"
