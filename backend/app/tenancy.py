"""Kurum (kiraci) kapsaminin TEK tanimi.

NEDEN AYRI BIR MODUL: kurum kapsami "her rotada elle bir if yazmak" olarak
uygulanirsa, unutulan tek rota sessiz bir kurumlar arasi sizintidir - ve
sizinti kimse aramadigi surece gorunmez. Kural burada BIR kez yaziliyor;
rotalar onu cagiriyor.

UC KURAL, HEPSI BU DOSYADA:

1. ON-EK VE-KAPISI. Kurum kontrolu rol dallarindan ONCE gelir. Yabanci
   kurumun kaydinda "bu kisinin rolu ne" sorusu HIC sorulmaz - cunku
   sorulursa "yonetici her seyi gorur" gibi bir dal kurum sinirini asar.

2. TOLERANS YALNIZCA KAYIT TARAFINDA. Kurumu bos KAYITLARA erisim
   veriliyor (`_gecis_toleransi`) cunku kurum alanlari mevcut veriye
   sonradan eklendi ve eski kayitlarin kurumu bos; tolerans olmasaydi eski
   veri bir anda herkese kapanirdi. Kurum alanlari zorunlu hale gelince bu
   da kalkmali - `KATI_KURUM` bayragi bunun icin var.

   KULLANICI tarafinda tolerans YOK. Bir zamanlar vardi ve kapiyi tam ters
   cevirmisti: kurum SECMEMEK, kurum secmekten DAHA COK yetki veriyordu.
   Olculdu - org iddiasi tasimayan imzali bir token 12 raporun hepsini,
   baska kurumun yarismasini ve ozel kategorilerini goruyordu. Kurumsuz
   token "henuz secim yapilmadi" ya da "gecmisten kalmis" demek; ikisi de
   veri gormemeli.

3. YABANCI KURUMDA 404, KENDI KURUMUNDA 403. Kurum ICINDE 403 dogru
   tercihtir: net mesaj hakemin isini kolaylastirir ve kaydin var oldugu
   zaten bilinen bir sey. Kurum SINIRINDA 403 ise "bu kimlik baska bir
   kurumda VAR" bilgisini ONAYLAR; saldirgan kimlikleri tek tek deneyerek
   baska kurumun kayit listesini cikarabilir (varlik kahini). Sinirda kayit
   YOKMUS gibi davraniyoruz.
"""

import os

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from . import models

# Gecis donemi bittiginde "1" yapilacak: kurumu bos olan kayda erisim
# tamamen kapanir. Simdilik kapali cunku eski kayitlarin kurumu yok.
KATI_KURUM = os.getenv("STRICT_TENANCY", "0") == "1"

# Tek tanim models.py'de: uc ayri dosyada elle yazilan rol listeleri
# zamanla birbirinden ayrisiyordu.
YONETICI_ROLLERI = models.YONETICI_ROLLERI


def aktif_kurum(user) -> str | None:
    """Istegin yapildigi kurum. Token'dan geliyor, istekten DEGIL.

    Istemcinin gonderdigi bir `organization_id` alanina asla bakmiyoruz:
    baksaydik kurum secimi saldirganin elinde olurdu.
    """
    return getattr(user, "active_org_id", None)


def _gecis_toleransi(kayit_kurum, kullanici_kurum) -> bool:
    """Yalnizca KAYIT kurumsuzsa tolerans var; KULLANICI kurumsuzsa YOK.

    Onceden ikisi de tolere ediliyordu ve bu, kapiyi tam ters cevirmisti:
    kurum SECMEMEK, kurum secmekten DAHA COK yetki veriyordu. Olculdu - org
    iddiasi tasimayan imzali bir token 12 raporun hepsini, baska kurumun
    yarismasini ve ozel kategorilerini goruyordu.

    Kayit tarafindaki tolerans duruyor cunku sebebi baska: kurum alanlari
    mevcut veriye SONRADAN eklendi ve eski kayitlarin kurumu bos. Kullanici
    tarafinda boyle bir eski veri yok - kurumsuz token yalnizca "henuz
    secim yapilmadi" ya da "gecmisten kalmis" demek; ikisi de veri
    gormemeli.
    """
    if KATI_KURUM:
        return False
    if kullanici_kurum is None:
        return False
    return kayit_kurum is None


def ayni_kurum_mu(kayit, user) -> bool:
    """Kayit, kullanicinin AKTIF kurumuna mi ait?

    `kayit` uzerinde `organization_id` olmali. Alani olmayan bir nesne
    gelirse GECIRMIYORUZ (None donmuyor, False donuyor): sessizce izin
    vermek, alani eklemeyi unuttugumuz her modeli aciga cikarirdi.
    """
    if kayit is None:
        return False
    kayit_kurum = getattr(kayit, "organization_id", None)
    kullanici_kurum = aktif_kurum(user)
    if _gecis_toleransi(kayit_kurum, kullanici_kurum):
        return True
    # KATI modda None == None ESLESME SAYILMAZ.
    #
    # Bu satir olmadan, kurumu bos bir kayit ile kurumu bos bir token
    # birbirine esitleniyordu - yani bayragin kapatmasi gereken tek durum,
    # bayrak acikken bile aciktan geciyordu. Bayragi denemeden fark
    # edilemezdi: gevsek modda ayni girdi zaten toleransla geciyor.
    if kayit_kurum is None or kullanici_kurum is None:
        return False
    return kayit_kurum == kullanici_kurum


def kurum_filtresi(query, model, user):
    """Sorguyu kullanicinin kurumuyla sinirlar (liste uc noktalari icin).

    Gecis doneminde kurumu BOS olan kayitlar da doner - `ayni_kurum_mu` ile
    ayni tavizin sorgu karsiligi. Ikisi ayni yerde durmali, yoksa "detayda
    goruyorum ama listede yok" gibi tutarsizliklar cikar.
    """
    kullanici_kurum = aktif_kurum(user)
    if kullanici_kurum is None:
        # KURUMSUZ TOKEN HICBIR SEY GORMUYOR. Onceden burada `return query`
        # vardi - yani filtre tamamen atlaniyordu. Bos sonuc yerine
        # `1 = 0` kullanmiyoruz, ACIKCA reddediyoruz: sessizce bos donmek,
        # rol secmemis kullaniciya "sistemde hicbir sey yok" izlenimi verir
        # ve gercek sebep (secim yapilmadi) hicbir yerde gorunmez.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Bu istek icin kurum secilmemis. /api/auth/select-role ile "
                "hangi kurum adina calistiginizi secin."
            ),
        )
    if KATI_KURUM:
        return query.filter(model.organization_id == kullanici_kurum)
    return query.filter(
        (model.organization_id == kullanici_kurum) | (model.organization_id.is_(None))
    )


def yoksa_gibi_davran(mesaj: str = "Kayit bulunamadi.") -> HTTPException:
    """Yabanci kurum icin 404. Gerekcesi modul basligindaki 3. kural."""
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=mesaj)


def yonetici_mi(user) -> bool:
    return getattr(user, "active_role", None) in YONETICI_ROLLERI


def yarisma_getir_yetkiliyse(
    competition_id: str, user, db: Session
) -> models.Competition:
    """Yarismayi getirir; erisilemiyorsa 404 firlatir.

    Yarismaya dokunan HER uc nokta buradan gecmeli. Onceden her uc nokta
    kendi `db.query(...).first()` cagrisini yapiyordu ve hicbiri kurum
    sormuyordu; sonuc olarak bir kurumun yoneticisi BASKA bir kurumun
    sablonunu, kriterlerini ve asamasini degistirebiliyordu (olculdu: uc
    istekte de HTTP 200).

    Uc red sebebi de AYNI 404'u doner - "yok", "baska kurumun" ve "hazirlik
    asamasinda, sen goremezsin" ayirt edilemez olmali. Farkli cevaplar
    verseydik her biri bir kahin olurdu.
    """
    y = (
        db.query(models.Competition)
        .filter(models.Competition.id == competition_id)
        .first()
    )
    if y is None or not ayni_kurum_mu(y, user):
        raise yoksa_gibi_davran("Yarisma bulunamadi.")
    # Hazirlik asamasindaki yarisma yalnizca yoneticiye gorunur: yonetici
    # hazirligini bitirmeden yarisma duyurulmus gibi gorunmemeli.
    if y.status == "draft" and not yonetici_mi(user):
        raise yoksa_gibi_davran("Yarisma bulunamadi.")
    return y


def kurumun_rolleri(db: Session, kurum_id: str | None, rol: str) -> list:
    """Belirtilen kurumda o role sahip kullanici kimlikleri.

    NEDEN KURUM SART: `UserRole` sorgusuna kurum eklenmezse "hakem" demek
    "HERHANGI bir kurumda hakem" demek olur. Bu, bir kurumun raporunu baska
    kurumun hakemine atamayi mumkun kilar - kurum sinirini asmanin en sessiz
    yolu, cunku atama yaparken kimse hakemin hangi kurumda oldugunu
    sormuyordu.
    """
    # Kurumsuz istek HICBIR SEY gormuyor - KATI modda da, gevsek modda da.
    # Gevsek modda sistem genelindeki hakem rehberini dondurmek "kurum
    # secmemek daha cok yetki verir" hatasinin ta kendisiydi. Kontrol
    # sorgudan ONCE geliyor ki "once kapsamsiz sorguyu kur, sonra vazgec"
    # gibi bir sira kalmasin.
    if kurum_id is None:
        return []
    return [
        r.user_id
        for r in db.query(models.UserRole)
        .filter(
            models.UserRole.role == rol,
            models.UserRole.organization_id == kurum_id,
        )
        .all()
    ]
