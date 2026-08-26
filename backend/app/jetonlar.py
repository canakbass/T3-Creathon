"""E-posta dogrulama ve sifre sifirlama jetonlari.

SIFRE GIBI SAKLANIYOR. Veri tabaninda yalnizca SHA-256 ozeti duruyor; ham
jeton yalnizca gonderilen e-postada. Veri tabani sizarsa jetonlar
kullanilamaz - ki bu, sifre sifirlama jetonlarinin sizmasi "her hesabi ele
gecir" demek oldugu icin onemli.

NEDEN SHA-256, BCRYPT DEGIL: jetonun entropisi zaten yuksek
(`secrets.token_urlsafe(32)` = 256 bit), yani kaba kuvvet imkansiz.
Bcrypt'in yavasligi burada bir sey kazandirmiyor ama her dogrulamada TUM
tabloyu taramayi zorunlu kilardi - bcrypt ozetleri tuzlu oldugu icin
aranamaz. Duz SHA-256 ozeti benzersiz indeksli, arama sabit maliyetli.

NEDEN JWT DEGIL: bu jetonlar TEK KULLANIMLIK ve IPTAL EDILEBILIR olmali.
JWT ikisini de yapamaz - imzalanmis bir JWT, suresi dolana kadar kac kez
kullanilirsa kullanilsin gecerlidir. Kullanilmis bir sifirlama baglantisi
ikinci kez calismamali.
"""

import datetime
import hashlib
import secrets
import uuid

from sqlalchemy.orm import Session

from . import models

DOGRULAMA = "dogrulama"
SIFIRLAMA = "sifirlama"

# Dogrulama uzun, sifirlama KISA.
#
# Ikisi ayni sure olsaydi yanlis tarafta hata yapardik: dogrulama
# baglantisini kullanici bir gun sonra acabilir (spam klasoru, mesai),
# sifirlama baglantisi ise ele gecirilmis bir posta kutusunda ne kadar az
# beklerse o kadar iyi.
SURELER = {
    DOGRULAMA: datetime.timedelta(hours=24),
    SIFIRLAMA: datetime.timedelta(minutes=30),
}

# Ayni adrese ne siklikta jeton uretilebilir.
#
# Sinir olmadan bu uc bir MEKTUP BOMBASI aracina donusur: saldirgan
# kurbanin adresini yazip saniyede onlarca mektup gonderttirir.
BEKLEME = datetime.timedelta(seconds=60)


def _simdi() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC).replace(tzinfo=None)


def ozetle(ham: str) -> str:
    return hashlib.sha256(ham.encode("utf-8")).hexdigest()


def cok_sik_mi(db: Session, user_id: str, purpose: str) -> bool:
    """Son jeton BEKLEME suresinden yeni mi?

    Cagiran taraf bu durumda da AYNI yaniti dondurmeli: farkli bir cevap
    (orn. 429) yeni bir varlik kahini olurdu - "hizli deneyince farkli
    cevap veriyor, demek ki bu adres kayitli".
    """
    son = (
        db.query(models.EmailToken)
        .filter(
            models.EmailToken.user_id == user_id,
            models.EmailToken.purpose == purpose,
        )
        .order_by(models.EmailToken.created_at.desc())
        .first()
    )
    if son is None or son.created_at is None:
        return False
    return _simdi() - son.created_at < BEKLEME


def uret(db: Session, user_id: str, purpose: str) -> str:
    """Yeni jeton uretir, ONCEKILERI IPTAL EDER ve HAM jetonu doner.

    Onceki jetonlarin iptali sart: kullanici "baglanti gelmedi" deyip
    ikinci kez isteyince ELINDE iki gecerli baglanti olurdu ve eskisi -
    belki bir yerde loglanmis olan - hala calisirdi.
    """
    ham = secrets.token_urlsafe(32)
    # Ayni amacli eski jetonlari kullanilmis say.
    (
        db.query(models.EmailToken)
        .filter(
            models.EmailToken.user_id == user_id,
            models.EmailToken.purpose == purpose,
            models.EmailToken.used_at.is_(None),
        )
        .update({models.EmailToken.used_at: _simdi()}, synchronize_session=False)
    )
    db.add(
        models.EmailToken(
            id=str(uuid.uuid4()),
            user_id=user_id,
            purpose=purpose,
            token_hash=ozetle(ham),
            expires_at=_simdi() + SURELER[purpose],
        )
    )
    return ham


def tuket(db: Session, ham: str, purpose: str):
    """Jetonu ATOMIK olarak tuketir; kullaniciyi doner ya da None.

    NEDEN ATOMIK: once SELECT sonra UPDATE yapilsaydi, iki es zamanli istek
    ayni jetonu iki kez harcardi. `UPDATE ... WHERE used_at IS NULL` ve
    etkilenen satir sayisi kontrolu bunu veri tabaninin kendisine
    yaptiriyor.

    HER RED AYNI: "boyle bir jeton yok", "suresi dolmus" ve "zaten
    kullanilmis" ayirt edilemez olmali. Ayrilsaydi saldirgan gecerli bir
    jetonun VAR OLDUGUNU dogrulayabilirdi.
    """
    if not ham:
        return None
    etkilenen = (
        db.query(models.EmailToken)
        .filter(
            models.EmailToken.token_hash == ozetle(ham),
            models.EmailToken.purpose == purpose,
            models.EmailToken.used_at.is_(None),
            models.EmailToken.expires_at > _simdi(),
        )
        .update({models.EmailToken.used_at: _simdi()}, synchronize_session=False)
    )
    if etkilenen != 1:
        return None
    kayit = (
        db.query(models.EmailToken)
        .filter(models.EmailToken.token_hash == ozetle(ham))
        .first()
    )
    return kayit.user if kayit else None


def hepsini_dusur(db: Session, user_id: str) -> None:
    """Kullanicinin TUM bekleyen jetonlarini gecersiz kilar.

    Sifre sifirlandiktan sonra cagriliyor: o ana kadar uretilmis her
    dogrulama/sifirlama baglantisi olmeli, cunku hesabin ele gecirilmis
    olma ihtimali sifirlamanin sebebidir.
    """
    (
        db.query(models.EmailToken)
        .filter(
            models.EmailToken.user_id == user_id,
            models.EmailToken.used_at.is_(None),
        )
        .update({models.EmailToken.used_at: _simdi()}, synchronize_session=False)
    )
