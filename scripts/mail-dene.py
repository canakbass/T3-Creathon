#!/usr/bin/env python3
"""E-posta ayarlarini SINAR ve gercekten bir mektup gonderir.

NEDEN VAR: kullanicinin ilk sikayeti "sifirlama e-postasi gelmedi"ydi ve
sebebi bir hata degildi - `EMAIL_BACKEND` varsayilan olarak `file`, yani
mektup `backend/outbox/*.eml` dosyasina yaziliyordu. Bunu ancak koda bakan
biri anlayabilirdi.

Bu betik iki soruyu ayri ayri cevapliyor:
  1. HANGI arka uc etkin ve mektup NEREYE gidiyor?
  2. SMTP secildiyse ayarlar GERCEKTEN calisiyor mu?

Ikincisi onemli: SMTP ayarlarini "kayit olup bekleyerek" denemek, hem yavas
hem de hatanin nerede oldugunu gizliyor (sunucu mu, sifre mi, port mu).
Burada hata dogrudan ekrana dusuyor.

KULLANIM
    cd backend
    ../.venv/bin/python ../scripts/mail-dene.py                # durumu goster
    ../.venv/bin/python ../scripts/mail-dene.py ben@ornek.com  # deneme gonder

GMAIL ICIN (en hizli yol):
    1. Google hesabinda IKI ADIMLI DOGRULAMA acik olmali.
    2. myaccount.google.com/apppasswords -> "Uygulama sifresi" olustur.
       (Normal Gmail sifreniz CALISMAZ - Google 2022'den beri kabul etmiyor.)
    3. backend/.env dosyasina:
           EMAIL_BACKEND=smtp
           SMTP_HOST=smtp.gmail.com
           SMTP_PORT=587
           SMTP_USER=hesabiniz@gmail.com
           SMTP_PASSWORD=<16 haneli uygulama sifresi, bosluksuz>
           SMTP_FROM=hesabiniz@gmail.com
           APP_BASE_URL=http://localhost:3000
    4. Bu betigi calistirin.
"""

import os
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK / "backend"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(KOK / "backend" / ".env")

from app.services import notify  # noqa: E402


def durum() -> str:
    arka = os.getenv("EMAIL_BACKEND", "file").strip().lower()
    print(f"EMAIL_BACKEND = {arka}")
    print(f"APP_BASE_URL  = {os.getenv('APP_BASE_URL', 'http://localhost:3000')}")
    if arka == "smtp":
        sunucu = os.getenv("SMTP_HOST")
        print(f"SMTP_HOST     = {sunucu or '(AYARLANMAMIS!)'}")
        print(f"SMTP_PORT     = {os.getenv('SMTP_PORT', '587')}")
        print(f"SMTP_USER     = {os.getenv('SMTP_USER') or '(bos)'}")
        # Sifreyi ASLA basmiyoruz - yalnizca ayarlanmis mi.
        print(
            "SMTP_PASSWORD = "
            + ("ayarlanmis" if os.getenv("SMTP_PASSWORD") else "(AYARLANMAMIS!)")
        )
        print(f"SMTP_FROM     = {os.getenv('SMTP_FROM') or '(varsayilan)'}")
        if not sunucu:
            print("\nHATA: EMAIL_BACKEND=smtp ama SMTP_HOST bos. Mektup gonderilemez.")
    elif arka == "console":
        print("\nMektuplar SUNUCU GUNLUGUNE basiliyor (gercek gonderim YOK).")
    else:
        kutu = Path(os.getenv("EMAIL_OUTBOX", "outbox")).resolve()
        print(f"\nMektuplar DOSYAYA yaziliyor: {kutu}")
        print("Gercek gonderim YOK - 'sifirlama e-postasi gelmedi' sikayetinin sebebi bu.")
        if kutu.exists():
            dosyalar = sorted(kutu.glob("*.eml"), key=lambda p: p.stat().st_mtime, reverse=True)
            if dosyalar:
                print(f"\nSon {min(5, len(dosyalar))} mektup:")
                for d in dosyalar[:5]:
                    print(f"  {d}")
                print("\nBaglantiyi gormek icin:")
                print(f"  grep -o 'http[^ ]*' {dosyalar[0]}")
            else:
                print("(Kutu bos - henuz mektup uretilmemis.)")
        else:
            print("(Kutu henuz olusmamis - henuz mektup uretilmemis.)")
    return arka


def main() -> int:
    print("=" * 60)
    arka = durum()
    print("=" * 60)

    if len(sys.argv) < 2:
        print("\nDeneme mektubu gondermek icin bir adres verin:")
        print("  ../.venv/bin/python ../scripts/mail-dene.py ben@ornek.com")
        return 0

    alici = sys.argv[1]
    print(f"\n{alici} adresine deneme mektubu gonderiliyor...")

    # `notify.gonder` hatalari YUTUYOR (bir kayit istegini 500'e dusurmemek
    # icin). Burada YUTMAMASI gerekiyor: betigin tek isi hatayi gostermek.
    # Bu yuzden arka ucu dogrudan cagiriyoruz.
    mektup = notify._mektup(  # noqa: SLF001
        alici,
        "Deneme mektubu",
        "Bu bir denemedir. Bu mektubu aldiysaniz e-posta ayarlariniz "
        "calisiyor demektir.\n",
    )
    try:
        if arka == "smtp":
            notify._smtp_gonder(mektup)  # noqa: SLF001
            print("BASARILI - mektup SMTP sunucusuna teslim edildi.")
            print("Gelen kutunuzu (ve spam klasorunu) kontrol edin.")
        else:
            notify.gonder(alici, "Deneme mektubu", "Bu bir denemedir.\n")
            print(f"Mektup uretildi ama GERCEKTEN GONDERILMEDI (arka uc: {arka}).")
            print("Gercek gonderim icin backend/.env icinde EMAIL_BACKEND=smtp yapin.")
    except Exception as hata:  # noqa: BLE001
        print(f"\nBASARISIZ: {hata!r}\n")
        metin = str(hata).lower()
        if "authentication" in metin or "username and password" in metin:
            print("IPUCU: Gmail normal hesap sifresini KABUL ETMIYOR.")
            print("       myaccount.google.com/apppasswords adresinden bir")
            print("       UYGULAMA SIFRESI olusturup SMTP_PASSWORD'e yazin.")
        elif "timed out" in metin or "connection" in metin:
            print("IPUCU: Sunucu adresi ya da port yanlis olabilir, ya da ag")
            print("       cikisi engelli. Gmail icin 587 + STARTTLS deneyin.")
        elif "starttls" in metin or "ssl" in metin:
            print("IPUCU: 465 portu SSL, 587 portu STARTTLS ister.")
            print("       587 kullaniyorsaniz SMTP_STARTTLS=1 olmali.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
