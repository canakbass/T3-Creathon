import os
import secrets
import uuid
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..services import notify
from .. import models, schemas, auth, tenancy, jetonlar

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

# KENDI KENDINE KAYIT ARTIK ACIK (varsayilan).
#
# BIR SURE KAPALIYDI ve sebebi ciddiydi: raporun sonucunu TAKIM UYELIGI
# belirliyor, uyelik e-postaya bagli ve e-posta dogrulamamiz yoktu - yani bir
# takim uyesinin e-postasini ILK KAYDETTIREN kisi o takimin sonuclarini
# gorurdu.
#
# NE DEGISTI: (1) e-posta dogrulama eklendi, (2) kayit ARTIK HICBIR ROL VE
# HICBIR KURUM VERMIYOR. Takim bagi kayit aninda degil DOGRULAMA aninda
# kuruluyor. Yani kayit olmak tek basina hicbir sey acmiyor; acan sey posta
# kutusuna erisebildigini kanitlamak.
#
# Yonetici hesap acmaya devam ediyor (POST /api/auth/users) ve o hesaplar
# dogrulanmis sayiliyor - orada kimlige YONETICI kefil oluyor. Iki yol
# birbirinin yerine gecmiyor, birbirini tamamliyor:
#   * yonetici yolu: kimlik garantili, sifre iletilmesi gerekiyor
#   * kendi kaydi:   kimlik posta kutusuyla kanitlaniyor, sifre kullanicinin
#
# SELF_REGISTRATION=0 ile kapatilabilir (kurum icine kapali kurulumlar icin).
def _kendi_kaydi_acik() -> bool:
    return os.getenv("SELF_REGISTRATION", "1").strip().lower() in ("1", "true", "evet")


# Kendi kendine kayit (SELF_REGISTRATION=1) acikken yeni hesaplarin
# baglanacagi kurum. Yonetici acilan hesaplarda ARTIK KULLANILMIYOR - orada
# kurum cagiranin aktif kurumundan geliyor.
VARSAYILAN_KURUM_SLUG = "t3-vakfi"


def _varsayilan_kurum_id(db: Session):
    kurum = (
        db.query(models.Organization)
        .filter(models.Organization.slug == VARSAYILAN_KURUM_SLUG)
        .first()
    )
    return kurum.id if kurum else None


def _secim_gecerli(user: models.User, kurum, rol: str) -> bool:
    """(kurum, rol) cifti bu kullanici icin secilebilir mi?

    KURUM SORUMLUSU KENDI KURUMUNDA HER ROLU SECEBILIR. Kullanicinin istegi
    buydu: "bu superuserlar her role bakabilmeli". Bu bir taviz DEGIL, cunku
    sorumlu o rolu kendine zaten verebiliyor (POST /me/members/.../roles);
    engellemek guvenlik degil yalnizca fazladan iki tiklama saglardi.
    Kararlarda kimin imzasi oldugu degismiyor - karar kaydi kullanici
    kimligini tutuyor, rolu degil.

    SINIR AYNEN DURUYOR: yalnizca ORG_OWNER OLDUGU kurumda. Baska kurumda
    hicbir sey secemez.
    """
    uyelikler = user.memberships
    if (kurum, rol) in [
        (u["organization_id"], r) for u in uyelikler for r in u["roles"]
    ]:
        return True
    return rol in models.ROLLER and "ORG_OWNER" in user.roles_in(kurum)


def _uret_sifre() -> str:
    """Kriptografik olarak guvenli, okunabilir gecici sifre.

    `secrets` kullaniliyor - `random` DEGIL: random tahmin edilebilir bir
    PRNG ve parola uretiminde kullanilmasi acik bir zafiyettir.
    """
    return secrets.token_urlsafe(12)


def _rol_ver(db: Session, user: models.User, roller, organization_id=None) -> None:
    """Kullaniciya BIR KURUMDAKI rol(leri) ekler. Zaten varsa tekrar eklemez.

    `organization_id` govdeden DEGIL cagiranin baglamindan gelmeli - govdeye
    acilirsa "baska kuruma kullanici acma" ucu olur.
    """
    mevcut = set(user.roles_in(organization_id))
    for rol in roller:
        if rol in mevcut or rol not in models.ROLLER:
            continue
        db.add(models.UserRole(
            id=str(uuid.uuid4()),
            user_id=user.id,
            organization_id=organization_id,
            role=rol,
        ))
        mevcut.add(rol)


@router.post(
    "/register", response_model=schemas.RegistrationResult, status_code=status.HTTP_202_ACCEPTED
)
def register(
    user_in: schemas.UserCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Kendi kendine kayit + E-POSTA DOGRULAMA.

    NEDEN TEKRAR ACIK: kullanicinin istegi - "kullanici kendi kendine de
    hesap olusturabilsin, sifremi unuttum gibi islemler yapabilsin".

    NEDEN KAPALIYDI: raporun sonucunu TAKIM UYELIGI belirliyor ve uyelik
    e-postaya bagli; kayit acik olsaydi bir takim uyesinin e-postasini ILK
    KAYDETTIREN kisi o takimin sonuclarini gorurdu.

    DOGRULAMA BU ACIGI KAPATIYOR, AMA TEK BIR KOSULLA: takim bagi KAYIT
    aninda degil DOGRULAMA aninda kuruluyor. Aksi halde saldirgan kayit
    olur, dogrulamaz ve bag yine kurulmus olurdu.

    UC SEY BILINCLI:

    1. HIC ROL VERILMIYOR. Govdedeki `roles`/`role` alanlari TAMAMEN yok
       sayiliyor. Kara liste (AYRICALIKLI_ROLLER) yetmezdi: `REFEREE` o
       listede degil ve kendine hakem rolu veren biri /reports/lookup ile
       kurumun butun basvuru kunyelerini okuyabilirdi. Rol yalnizca
       dogrulama sonrasi eslesmeyle ve yalnizca COMPETITOR olarak geliyor.

    2. HIC KURUM VERILMIYOR. Onceden varsayilan kuruma yaziliyordu, yani
       "kayit formu = T3 Vakfi uyeligi" demekti. Kuruma giris yalnizca iki
       yolla: sorumlu rol verir, ya da DOGRULANMIS e-posta bir bekleyen
       takim uyeligiyle eslesir.

    3. YANIT HER DURUMDA AYNI. "Bu e-posta zaten kayitli" demek bir VARLIK
       KAHINI olurdu - herhangi biri adres deneyerek sistemde kimin hesabi
       oldugunu ogrenirdi. Adres zaten varsa SAHIBINE "hesabin var" mektubu
       gidiyor; farki yalnizca posta kutusunun sahibi goruyor.
    """
    if not _kendi_kaydi_acik():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Kendi kendine kayit kapali. Hesabinizi kurumunuzun yoneticisi "
                "acar ve giris bilgileri size iletilir."
            ),
        )

    eposta = (user_in.email or "").strip().lower()
    if len(user_in.password or "") < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Sifre en az 8 karakter olmali.",
        )

    mevcut = db.query(models.User).filter(func.lower(models.User.email) == eposta).first()
    jeton = None

    if mevcut is not None:
        # Sahibine haber ver, cagirana AYNI cevabi don.
        background_tasks.add_task(notify.zaten_kayitli_mektubu, eposta)
    else:
        kullanici = models.User(
            id=str(uuid.uuid4()),
            email=eposta,
            password_hash=auth.hash_password(user_in.password),
            full_name=user_in.full_name,
            email_verified=False,
        )
        db.add(kullanici)
        db.flush()
        jeton = jetonlar.uret(db, kullanici.id, jetonlar.DOGRULAMA)
        background_tasks.add_task(notify.dogrulama_mektubu, eposta, jeton)

    db.commit()
    return {
        "message": (
            "Bu adres kullanilabilirse dogrulama baglantisi gonderildi. "
            "Gelen kutunuzu (ve spam klasorunu) kontrol edin."
        ),
        # YALNIZCA gelistirmede dolu (DEV_EXPOSE_EMAIL_TOKEN=1 ve SMTP disi).
        # Uretimde None - jetonu yanitta dondurmek dogrulamayi anlamsiz kilar.
        "dev_token": jeton if notify.jeton_yanitta_gorunsun_mu() else None,
    }


@router.post("/verify-email", response_model=schemas.VerificationResult)
def verify_email(
    govde: schemas.TokenSubmit,
    db: Session = Depends(get_db),
):
    """E-postayi dogrular ve BEKLEYEN TAKIM UYELIKLERINI baglar.

    BAGLAMA ANI TAM OLARAK BURASI ve tek islem icinde: dogrulanmamis bir
    hesap hicbir takima, hicbir kuruma, hicbir role sahip degil.
    """
    kullanici = jetonlar.tuket(db, govde.token, jetonlar.DOGRULAMA)
    if kullanici is None:
        # "Yok", "suresi dolmus" ve "kullanilmis" AYNI cevabi veriyor.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Bu dogrulama baglantisi gecersiz ya da suresi dolmus. "
                "Giris ekranindan yeni bir baglanti isteyin."
            ),
        )
    kullanici.email_verified = True
    baglanan = _bekleyen_uyelikleri_bagla(db, kullanici)
    db.commit()
    return {
        "message": "E-posta adresiniz dogrulandi.",
        "linked_teams": baglanan,
    }


@router.post("/resend-verification", status_code=status.HTTP_202_ACCEPTED)
def resend_verification(
    govde: schemas.EmailSubmit,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Dogrulama baglantisini yeniden gonderir - HER ZAMAN ayni cevap."""
    eposta = (govde.email or "").strip().lower()
    kullanici = db.query(models.User).filter(func.lower(models.User.email) == eposta).first()
    if (
        kullanici is not None
        and not kullanici.email_verified
        and not jetonlar.cok_sik_mi(db, kullanici.id, jetonlar.DOGRULAMA)
    ):
        jeton = jetonlar.uret(db, kullanici.id, jetonlar.DOGRULAMA)
        background_tasks.add_task(notify.dogrulama_mektubu, eposta, jeton)
        db.commit()
    return {"message": "Bu adres dogrulama bekliyorsa baglanti gonderildi."}


@router.post("/password-reset/request", status_code=status.HTTP_202_ACCEPTED)
def password_reset_request(
    govde: schemas.EmailSubmit,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Sifre sifirlama baglantisi ister.

    VARLIK KAHINI OLMAMALI - iki taraflı:

    1. YANIT hep ayni: 202 + ayni metin. Kayitli olmayan adres icin de.
    2. ZAMANLAMA da ayni olmali. Kayitli dalda jeton uretimi + veri tabani
       yazma + SMTP var; kayitsiz dalda yok. SMTP'yi istek icinde
       bekleseydik fark milisaniyeden buyuk olur ve OLCULEBILIRDI. Gonderim
       ARKA PLAN gorevine aliniyor, yani iki dal da aninda donuyor.

    Hiz siniri da ayni sekilde SESSIZ: sinira takilan istek 429 degil yine
    202 aliyor, yoksa "hizli deneyince farkli cevap veriyor" yeni bir kahin
    olurdu.
    """
    eposta = (govde.email or "").strip().lower()
    kullanici = db.query(models.User).filter(func.lower(models.User.email) == eposta).first()
    if kullanici is not None and not jetonlar.cok_sik_mi(db, kullanici.id, jetonlar.SIFIRLAMA):
        jeton = jetonlar.uret(db, kullanici.id, jetonlar.SIFIRLAMA)
        background_tasks.add_task(notify.sifirlama_mektubu, eposta, jeton)
        db.commit()
    return {"message": "Bu adres kayitliysa sifirlama baglantisi gonderildi."}


@router.post("/password-reset/confirm")
def password_reset_confirm(
    govde: schemas.PasswordReset,
    db: Session = Depends(get_db),
):
    """Sifreyi degistirir ve ELDEKI TUM OTURUMLARI dusurur.

    OTURUM DUSURME SART: token 60 dakika gecerli ve rol/kurum veri tabanina
    karsi dogrulaniyor ama SIFRE dogrulanmiyordu - yani calinmis bir token,
    kurban sifresini sifirladiktan SONRA da bir saat daha calisiyordu. Bu,
    sifre sifirlamanin tek amacini ("hesabi geri al") ortadan kaldiriyordu.
    `token_epoch` artiyor ve o ana kadar imzalanmis her token oluyor.
    """
    if len(govde.new_password or "") < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Sifre en az 8 karakter olmali.",
        )
    kullanici = jetonlar.tuket(db, govde.token, jetonlar.SIFIRLAMA)
    if kullanici is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Bu sifirlama baglantisi gecersiz ya da suresi dolmus. "
                "Yeni bir baglanti isteyin."
            ),
        )
    kullanici.password_hash = auth.hash_password(govde.new_password)
    kullanici.token_epoch = (kullanici.token_epoch or 0) + 1
    # Sifirlama hesabin ele gecirilmis olabilecegi anlamina geliyor: o ana
    # kadar uretilmis HER baglanti (dogrulama dahil) olmeli.
    jetonlar.hepsini_dusur(db, kullanici.id)
    # Sifresini e-posta uzerinden sifirlayabilen kisi o kutuya erisiyor
    # demektir - bu, dogrulamanin ta kendisi.
    kullanici.email_verified = True
    baglanan = _bekleyen_uyelikleri_bagla(db, kullanici)
    db.commit()
    return {
        "message": "Sifreniz degistirildi. Yeni sifrenizle giris yapabilirsiniz.",
        "linked_teams": baglanan,
    }


def _bekleyen_uyelikleri_bagla(db: Session, kullanici: models.User) -> int:
    """Dogrulanmis e-postayi bekleyen takim uyeliklerine baglar.

    Her bagli takim icin O TAKIMIN KURUMUNDA `COMPETITOR` rolu veriliyor -
    baska rol degil, baska kurum degil. Kendi kendine kayit boylece kurum
    sinirini asmanin yeni bir yolu OLMUYOR: kuruma giris yine yoneticinin
    yaptigi bir eylemden (raporu o e-postayla yuklemesinden) doguyor.

    KURUMU BOS OLAN TAKIMA BAGLANMIYOR: gecis donemi toleransi kurumsuz
    kaydi herkese aciyor; kurumsuz bir uyelik uretmek o toleransi kalici
    bir aciga cevirirdi.
    """
    adres = (kullanici.email or "").strip().lower()
    bekleyenler = (
        db.query(models.TeamMember)
        .filter(
            models.TeamMember.email == adres,
            models.TeamMember.user_id.is_(None),
        )
        .all()
    )
    sayi = 0
    for uyelik in bekleyenler:
        takim = uyelik.team
        if takim is None or takim.organization_id is None:
            continue
        uyelik.user_id = kullanici.id
        sayi += 1
        if "COMPETITOR" not in kullanici.roles_in(takim.organization_id):
            db.add(
                models.UserRole(
                    id=str(uuid.uuid4()),
                    user_id=kullanici.id,
                    organization_id=takim.organization_id,
                    role="COMPETITOR",
                )
            )
    return sayi


@router.post(
    "/users", response_model=schemas.CreatedUser, status_code=status.HTTP_201_CREATED
)
def create_user(
    govde: schemas.AdminUserCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        auth.RoleChecker(list(models.YONETICI_ROLLERI))
    ),
):
    """Yonetici bir kullanici hesabi acar; sifreyi SISTEM uretir.

    NEDEN BOYLE: raporun sonucunu TAKIM UYELIGI belirliyor ve uyelik
    e-postaya bagli. Kullanicilar kendi kendine kayit olsaydi, bir takim
    uyesinin e-postasini ilk kaydettiren kisi o takimin sonuclarini gorurdu -
    e-posta dogrulamamiz yok. Hesabi yoneticinin acmasi bu bagi guvenilir
    kiliyor: kimlige yonetici kefil oluyor.

    T3'un mevcut pratigi de bu ("belirlenen mail + uretilmis guvenli sifre,
    kullaniciya iletiliyor").

    Sifre YALNIZCA BU YANITTA doner ve veri tabaninda yalnizca bcrypt ozeti
    saklanir - bir daha okunamaz. Kaybolursa yeni hesap degil, sifre
    sifirlama gerekir.
    """
    # KURUM CAGIRANIN AKTIF KURUMU. Onceden `_varsayilan_kurum_id(db)`
    # kullaniliyordu, yani B kurumunun yoneticisi A kurumuna kullanici
    # aciyordu - kullanicinin tarif ettigi durumun birebir kendisi:
    # "rastgele hakem hesabi actim herkesin verisini okuyabilir hale
    # geliyorum". Govdeden de ALMIYORUZ: alinsa "baska kuruma kullanici
    # acma" ucu olurdu.
    kurum = tenancy.aktif_kurum(current_user)
    if kurum is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Hangi kurum adina hesap acildigi belirsiz. Cikip tekrar giris "
                "yapin (kurum secimi token'da tasiniyor)."
            ),
        )

    eposta = govde.email.strip().lower()
    mevcut = db.query(models.User).filter(models.User.email == eposta).first()

    gecersiz = [r for r in govde.roles if r not in models.ROLLER]
    if gecersiz:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Gecersiz rol: {', '.join(gecersiz)}.",
        )

    # YETKI YUKARI DOGRU DAGITILAMAZ. Onceden her yarisma yoneticisi
    # sinirsiz yonetici uretebiliyordu; tek bir yonetici hesabi ele
    # gecirildiginde saldirgan kendine kalici yetki basabilirdi.
    ayricalikli = [r for r in govde.roles if r in models.AYRICALIKLI_ROLLER]
    if ayricalikli and getattr(current_user, "active_role", None) != "ORG_OWNER":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"{', '.join(ayricalikli)} rolunu yalnizca kurum sorumlusu "
                "(ORG_OWNER) verebilir."
            ),
        )

    # AYNI E-POSTA BASKA BIR KURUMDA OLABILIR. Kullanicinin sordugu durum:
    # "hem TEKNOFEST yarismasi icin hem de odev sonucu kontrolu icin ayni
    # maile bagliysam?" Cevap: ayni hesap, yeni kurumda yeni bir uyelik.
    # Yeni hesap acmiyoruz (o zaman iki ayri sifre olurdu) ve mevcut sifreyi
    # de DEGISTIRMIYORUZ - baska bir kurumun yoneticisi, o kisinin baska
    # kurumdaki oturumunu dusurebilirdi.
    if mevcut is not None:
        if mevcut.roles_in(kurum):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Bu e-posta adresi bu kurumda zaten kayitli.",
            )
        _rol_ver(db, mevcut, govde.roles, kurum)
        takim_id = _takima_ekle(db, mevcut, govde, kurum)
        db.commit()
        db.refresh(mevcut)
        return {
            "id": mevcut.id,
            "email": mevcut.email,
            # GONDERILEN ad doner, KAYITLI ad DEGIL.
            #
            # Onceden `mevcut.full_name` donuyordu: cagirinin hic vermedigi,
            # BASKA BIR KURUMUN kaydindan okunan bir bilgi. Yani herhangi bir
            # kurumun yoneticisi rastgele bir e-posta deneyip o kisinin
            # gercek adini ogrenebiliyordu (olculdu: "TAHMIN" gonderildi,
            # "Demo Yarismaci" dondu). Kisi bu kuruma uye oldugu icin adini
            # zaten uye listesinde gorecek - ama SORGUNUN CEVABI olarak
            # dondurmek, listeyi bir arama motoruna cevirir.
            "full_name": govde.full_name,
            "roles": mevcut.roles_in(kurum),
            "team_id": takim_id,
            "temporary_password": None,
            "notice": (
                "Bu e-posta baska bir kurumda zaten kayitliydi; bu kuruma "
                "UYELIK eklendi. Mevcut sifresi degistirilmedi - kullanici "
                "kendi sifresiyle girip kurum secer."
            ),
        }

    sifre = _uret_sifre()
    kullanici = models.User(
        id=str(uuid.uuid4()),
        email=eposta,
        password_hash=auth.hash_password(sifre),
        full_name=govde.full_name,
    )
    db.add(kullanici)
    db.flush()
    _rol_ver(db, kullanici, govde.roles, kurum)
    takim_id = _takima_ekle(db, kullanici, govde, kurum)

    db.commit()
    db.refresh(kullanici)
    return {
        "id": kullanici.id,
        "email": kullanici.email,
        "full_name": kullanici.full_name,
        "roles": kullanici.roles_in(kurum),
        "team_id": takim_id,
        "temporary_password": sifre,
        "notice": (
            "Bu sifre YALNIZCA BURADA gorunuyor; veri tabaninda yalnizca "
            "ozeti saklaniyor. Kullaniciya guvenli bir kanaldan iletin."
        ),
    }


def _takima_ekle(db: Session, kullanici: models.User, govde, kurum: str):
    """Istege bagli: ayni islemde takima ekle.

    Yonetici "hesabi ac + takima ekle"yi iki ayri adimda yapmak zorunda
    kalmasin; iki adimin arasinda unutulan bir uye, sonucunu HIC goremeyen
    bir yarismaci demek.

    TAKIM CAGIRANIN KURUMUNDA OLMALI: onceden kontrol yoktu, yani bir kurumun
    yoneticisi BASKA bir kurumun takimina uye ekleyebiliyordu - eklenen kisi
    o takimin butun basvuru sonuclarini gorurdu. "Yok" ile "baska kurumun"
    ayni 404'u donuyor.
    """
    if not govde.team_id:
        return None
    takim = db.query(models.Team).filter(models.Team.id == govde.team_id).first()
    if takim is None or not tenancy.ayni_kurum_mu(takim, kullanici_kurum_sahtesi(kurum)):
        raise HTTPException(status_code=404, detail="Takim bulunamadi.")
    adres = (kullanici.email or "").strip().lower()
    # E-POSTA ile ariyoruz, kimlikle degil: uyelik kaydi hesap acilmadan
    # ONCE (yonetici raporu yuklerken) olusmus olabilir. Kimlikle arasaydik
    # ayni kisi icin IKINCI bir uyelik satiri acar ve takimda ayni adres iki
    # kez gorunurdu.
    zaten = (
        db.query(models.TeamMember)
        .filter(
            models.TeamMember.team_id == takim.id,
            models.TeamMember.email == adres,
        )
        .first()
    )
    if zaten is not None:
        # Bekleyen uyeligi BAGLIYORUZ. Yonetici hesabi actigi icin kimlige
        # zaten kefil oluyor - dogrulama beklemeye gerek yok.
        if zaten.user_id is None:
            zaten.user_id = kullanici.id
        return takim.id
    db.add(
        models.TeamMember(
            id=str(uuid.uuid4()),
            team_id=takim.id,
            email=adres,
            user_id=kullanici.id,
            role=govde.team_role or "uye",
        )
    )
    return takim.id


class kullanici_kurum_sahtesi:
    """`tenancy.ayni_kurum_mu` bir KULLANICI bekliyor; burada elimizde yalnizca
    kurum kimligi var. Kurumu ikinci bir yerde elle karsilastirmak yerine ayni
    fonksiyonu cagiriyoruz - gecis toleransi ve KATI_KURUM davranisi tek
    yerde kalsin."""

    def __init__(self, kurum_id):
        self.active_org_id = kurum_id


@router.post("/login", response_model=schemas.LoginResponse)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """E-posta + sifre ile giris.

    Yanit, kullanicinin UYELIKLERINI (`memberships`) icerir: hangi kurumda
    hangi rollere sahip. Rol artik tek basina bir kimlik degil - "hakem"
    degil, "T3 Vakfi'nda hakem".

    Tek kurumda tek rolu varsa token dogrudan ona gore imzalanir ve arayuz
    ek bir adim gostermez. Birden fazla secenek varsa `active_role` ve
    `active_organization_id` null doner; arayuz KURUM+ROL secimi gosterip
    /select-role cagirir.

    OAuth2PasswordRequestForm kullaniliyor: govde JSON DEGIL form-encoded ve
    e-posta alaninin adi `username` (OAuth2 standardi).
    """
    user = db.query(models.User).filter(models.User.email == form_data.username).first()
    if not user or not auth.verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="E-posta veya sifre hatali",
            headers={"WWW-Authenticate": "Bearer"},
        )

    uyelikler = user.memberships
    roller = user.role_list

    # ROLSUZ HESAP GIRIS YAPABILIR, ama hicbir veri gormez.
    #
    # ONCEDEN 403 DONUYORDU ve bu, kendi kendine kayit akisini tamamen
    # KILITLIYORDU: yeni kayit olan kimsenin rolu yok, giris yapamiyor,
    # dolayisiyla "e-postani dogrula" ekranina bile ulasamiyordu.
    #
    # Guvenlik acisindan sorun degil: rolsuz/kurumsuz token yalnizca /me ve
    # /select-role icin is goruyor; her veri ucu `kurum_filtresi` uzerinden
    # 403 donduruyor (bkz. tenancy.py). Yani "girebilmek" ile "gorebilmek"
    # ayri seyler ve ayri kaliyor.

    # Secenek = (kurum, rol) cifti. Rol tek basina secilemez; ayri ayri
    # secilirse "kurum secildi ama rol secilmedi" gibi yarim durumlar olusur
    # ve o yarim tokenin ne gorecegi her rotada ayri ayri dusunulmek zorunda
    # kalir. Tek atomik secim bu sinifi tumden yok ediyor.
    secenekler = [
        (u["organization_id"], rol) for u in uyelikler for rol in u["roles"]
    ]

    # OAuth2'nin `scope` alani ile dogrudan rol istenebiliyor. Arayuz rol
    # secim ekranindan sonra bunu kullaniyor, boylece ikinci bir istek
    # gerekmiyor.
    # `scope` ile dogrudan secim: "ROL" ya da "org_id:ROL". Ikinci bicim
    # kurumu da belirtiyor; ilki geriye donuk uyumluluk icin duruyor ve
    # kullanicinin TEK kurumu varsa calisiyor.
    istenen = (form_data.scopes or [None])[0]
    aktif_rol = aktif_kurum = None
    if istenen:
        if ":" in istenen:
            aktif_kurum, aktif_rol = istenen.split(":", 1)
        else:
            aktif_rol = istenen
            kurumlar = {o for o, r in secenekler if r == aktif_rol}
            if len(kurumlar) == 1:
                aktif_kurum = next(iter(kurumlar))
        if not _secim_gecerli(user, aktif_kurum, aktif_rol):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Bu hesabin secili kurumda '{aktif_rol}' rolu yok. "
                    "Uyelikleriniz icin giris yanitindaki `memberships` alanina bakin."
                ),
            )
    elif len(secenekler) == 1:
        aktif_kurum, aktif_rol = secenekler[0]

    token = auth.create_access_token(
        data={
            "sub": user.email,
            "role": aktif_rol,
            "org": aktif_kurum,
            "epoch": user.token_epoch or 0,
        }
    )

    return {
        "access_token": token,
        "token_type": "bearer",
        "roles": roller,
        "active_role": aktif_rol,
        "active_organization_id": aktif_kurum,
        "memberships": uyelikler,
        # Arayuz "e-postanizi dogrulayin" ya da "henuz size ait bir basvuru
        # yok" ekranlarindan hangisini gosterecegini buradan biliyor.
        "email_verified": bool(user.email_verified),
        "user": _kullanici_yaniti(user),
    }


@router.post("/select-role", response_model=schemas.LoginResponse)
def select_role(
    secim: schemas.RoleSelection,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """Aktif rolu degistirir ve O ROLE gore imzalanmis YENI bir token doner.

    NEDEN YENI TOKEN: yetki kontrolu sunucu tarafinda kaliyor. Arayuz
    "ben simdi hakemim" ya da "ben simdi B kurumundayim" diyerek yetki
    degistiremez; ikisini de token tasiyor ve token'i yalnizca sunucu
    imzalayabiliyor.

    KURUM VE ROL TEK SECIM: `organization_id` verilmezse ve kullanicinin o
    role sahip oldugu TEK bir kurum varsa ondan turetiliyor; birden fazlaysa
    secim ZORUNLU - yanlis kurumda islem yapmak, baska bir kurumun verisine
    dokunmak demek.
    """
    uyelikler = current_user.memberships
    secenekler = [(u["organization_id"], rol) for u in uyelikler for rol in u["roles"]]

    kurum = secim.organization_id
    if kurum is None:
        adaylar = {o for o, r in secenekler if r == secim.role}
        # Sorumlu oldugu kurumlar da aday: sorumlu, kendisine henuz
        # verilmemis bir rolu de secebiliyor (bkz. _secim_gecerli).
        adaylar |= {
            u["organization_id"]
            for u in uyelikler
            if "ORG_OWNER" in u["roles"] and secim.role in models.ROLLER
        }
        if len(adaylar) == 1:
            kurum = next(iter(adaylar))
        elif len(adaylar) > 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"'{secim.role}' rolune birden fazla kurumda sahipsiniz; "
                    "hangi kurum adina calisacaginizi secin (organization_id)."
                ),
            )

    if not _secim_gecerli(current_user, kurum, secim.role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Bu hesabin secili kurumda '{secim.role}' rolu yok. "
                f"Uyelikler: {', '.join(u['organization_id'] + '=' + '/'.join(u['roles']) for u in uyelikler) or 'yok'}."
            ),
        )

    token = auth.create_access_token(
        data={
            "sub": current_user.email,
            "role": secim.role,
            "org": kurum,
            "epoch": current_user.token_epoch or 0,
        }
    )
    return {
        "access_token": token,
        "token_type": "bearer",
        "roles": current_user.role_list,
        "active_role": secim.role,
        "active_organization_id": kurum,
        "memberships": uyelikler,
        "user": _kullanici_yaniti(current_user),
    }


@router.get("/me", response_model=schemas.UserResponse)
def get_me(current_user: models.User = Depends(auth.get_current_user)):
    return _kullanici_yaniti(current_user)


def _kullanici_yaniti(user: models.User) -> dict:
    """UserResponse govdesi.

    `role` alani, tekil rol bekleyen eski istemciler icin duruyor: aktif rol
    varsa o, yoksa ilk rol.
    """
    roller = user.role_list
    aktif = getattr(user, "active_role", None)
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "created_at": user.created_at,
        "roles": roller,
        "role": aktif or (roller[0] if roller else None),
    }
