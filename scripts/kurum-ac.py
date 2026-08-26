#!/usr/bin/env python3
"""Yeni kurum (kiraci) acar ve ilk kurum sorumlusunu tanimlar.

NEDEN BETIK, NEDEN API DEGIL: kurum acmak bir isletme karari, kullanici
islemi degil. Bir uc noktadan acilabilse hesabi olan herkes yeni kiraci
uretebilirdi - ustelik kendini o kurumun sorumlusu yapardi, yani sisteme
girebilen herkes kendine sinirsiz yetkili bir alan acabilirdi. Bu betigi
calistirmak icin SUNUCUYA erisim gerekiyor; yetkinin kokunde olmasi gereken
sinir bu.

TAVUK-YUMURTA SORUNU: kurumun uyelerini yalnizca ORG_OWNER yonetebiliyor, ama
yeni bir kurumda henuz kimse yok. Ilk sorumluyu bu betik koyuyor; sonrasinda
her sey API'den yurutuluyor (POST /api/organizations/me/members/...).

KULLANIM
    cd backend
    ../.venv/bin/python ../scripts/kurum-ac.py \\
        --slug ege-uni --ad "Ege Üniversitesi" --sorumlu dekan@ege.edu.tr

Sorumlu zaten kayitliysa yeni hesap ACILMIYOR, o kuruma UYELIK ekleniyor -
ayni kisi birden fazla kurumda olabilir ("hem TEKNOFEST yarismasi icin hem
de odev kontrolu icin ayni maile bagliysam?"). Mevcut sifresi de
degistirilmiyor: degistirilse, yeni bir kurum acan kisi o kullanicinin baska
kurumdaki oturumunu dusurebilirdi.
"""

import argparse
import re
import secrets
import sys
import uuid
from pathlib import Path

# Betik `backend/` icinden ya da depo kokunden calistirilabilsin.
KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK / "backend"))

from app import auth, models  # noqa: E402
from app.database import SessionLocal, engine  # noqa: E402

SLUG_BICIMI = re.compile(r"^[a-z0-9][a-z0-9-]{1,48}[a-z0-9]$")


def main() -> int:
    ayristirici = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ayristirici.add_argument("--slug", required=True, help="kisa kimlik, orn. ege-uni")
    ayristirici.add_argument("--ad", required=True, help="kurumun tam adi")
    ayristirici.add_argument(
        "--sorumlu", required=True, help="ilk kurum sorumlusunun e-postasi"
    )
    a = ayristirici.parse_args()

    slug = a.slug.strip().lower()
    if not SLUG_BICIMI.match(slug):
        # Slug bir kimlik: URL'de ve gunlukte gorunuyor. Serbest metin
        # olsaydi bosluk/buyuk harf/Turkce karakter yuzunden ayni kuruma iki
        # farkli slug ile bakilabilirdi.
        print(
            f"HATA: slug bicimi gecersiz ({slug!r}). Kucuk harf, rakam ve "
            "tire; 3-50 karakter.",
            file=sys.stderr,
        )
        return 2

    eposta = a.sorumlu.strip().lower()
    models.Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if db.query(models.Organization).filter(models.Organization.slug == slug).first():
            print(f"HATA: '{slug}' slug'i zaten kullaniliyor.", file=sys.stderr)
            return 1

        kurum = models.Organization(id=f"org-{slug}", name=a.ad.strip(), slug=slug)
        db.add(kurum)
        db.flush()

        kullanici = db.query(models.User).filter(models.User.email == eposta).first()
        sifre = None
        if kullanici is None:
            # `secrets`, `random` DEGIL: random tahmin edilebilir bir PRNG ve
            # parola uretiminde kullanilmasi acik bir zafiyet.
            sifre = secrets.token_urlsafe(12)
            kullanici = models.User(
                id=str(uuid.uuid4()),
                email=eposta,
                password_hash=auth.hash_password(sifre),
            )
            db.add(kullanici)
            db.flush()

        db.add(
            models.UserRole(
                id=str(uuid.uuid4()),
                user_id=kullanici.id,
                organization_id=kurum.id,
                role="ORG_OWNER",
            )
        )
        db.commit()
    finally:
        db.close()

    print(f"Kurum acildi: {kurum.name}  (id={kurum.id}, slug={kurum.slug})")
    print(f"Kurum sorumlusu: {eposta}")
    if sifre:
        print(f"Gecici sifre: {sifre}")
        print(
            "\nBu sifre BIR DAHA gosterilmeyecek - veri tabaninda yalnizca "
            "bcrypt ozeti var. Sorumluya guvenli bir kanaldan iletin."
        )
    else:
        print(
            "Bu e-posta zaten kayitliydi; yeni hesap acilmadi, bu kuruma "
            "UYELIK eklendi. Mevcut sifresi degismedi."
        )
    print(
        "\nSonraki adim: sorumlu giris yapip kurumunu secsin, ardindan "
        "POST /api/auth/users ile ekibini kursun."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
