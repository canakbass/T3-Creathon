"""E-posta gonderimi - tek arayuz, uc arka uc.

SORUN: SMTP sunucumuz yok. Kullanicinin kendi sozu: "Mail sistemi ise SMTP
sunucusu gerektiriyor, bununla ugrasmak yerine..." Ama e-posta dogrulama
olmadan kendi kendine kayit acilamaz - dogrulama, "bir takim uyesinin
e-postasini ILK KAYDETTIREN kisi o takimin sonuclarini gorur" acigini
kapatan tek sey.

COZUM: akis GERCEK, teslimat degisken. Jeton uretiliyor, ozeti saklaniyor,
suresi isliyor, baglanti tiklaniyor - hepsi uretimdeki gibi. Degisen tek
sey mektubun nereye dustugu:

    EMAIL_BACKEND=file     (VARSAYILAN) -> backend/outbox/*.eml
    EMAIL_BACKEND=console  -> sunucu gunlugune
    EMAIL_BACKEND=smtp     -> gercek SMTP

Demoda outbox dosyasi acilip baglanti kopyalaniyor. Uretimde dort ortam
degiskeni ayarlaniyor ve KOD DEGISMIYOR - Gmail uygulama sifresi, Resend,
Brevo hepsi ayni degiskenlerle takiliyor.

NEDEN JETONU API YANITINDA DONDURMUYORUZ: dondurseydik kayit olan kisi
kendi jetonunu gorurdu ve dogrulamanin TAMAMI anlamsizlasirdi - "bu
kutunun sahibi misin" sorusu kendi kendine cevaplanmis olurdu.
`DEV_EXPOSE_EMAIL_TOKEN` bunun icin ayri bir bayrak: varsayilan KAPALI,
`smtp` arka ucunda HIC calismiyor ve acikken uyari basiyor.
"""

import os
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path

# Baglantilarin adresi. ISTEK BASLIGINDAN (Host) URETILMEZ.
#
# NEDEN: host basligi istemcinin kontrolunde. Ondan uretilseydi saldirgan
# kendi sunucusuna giden bir "dogrulama" baglantisi urettirip kurbanin
# jetonunu toplayabilirdi (host header injection).
def _taban_url() -> str:
    return os.getenv("APP_BASE_URL", "http://localhost:3000").rstrip("/")

def _outbox() -> Path:
    """Mektup klasoru CAGRI ANINDA okunuyor, ice aktarma aninda degil.

    Modul seviyesinde okunsaydi, ortam degiskenini sonradan degistiren
    (testler, tek seferlik bir demo) hicbir sey ise yaramazdi - ve bunu fark
    etmek zor olurdu, cunku "mektup gelmedi" hatasi sessiz.
    """
    return Path(os.getenv("EMAIL_OUTBOX", "outbox"))


def _arka_uc() -> str:
    return os.getenv("EMAIL_BACKEND", "file").strip().lower()


def jeton_yanitta_gorunsun_mu() -> bool:
    """Gelistirme kolayligi: jetonu API yanitinda goster.

    UC KATLI KORUMA: varsayilan kapali, `smtp` arka ucunda hic calismiyor,
    ve acik oldugunda sunucu acilisinda uyari basiyor. `JWT_SECRET_KEY`
    kalibinin aynisi - yapilandirmayi unutmak GUVENLIGI ARTIRIYOR.
    """
    if _arka_uc() == "smtp":
        return False
    return os.getenv("DEV_EXPOSE_EMAIL_TOKEN", "0").strip().lower() in ("1", "true", "evet")


def _mektup(alici: str, konu: str, govde: str) -> EmailMessage:
    m = EmailMessage()
    m["From"] = os.getenv("SMTP_FROM", "no-reply@degerlendirme.local")
    m["To"] = alici
    m["Subject"] = konu
    m.set_content(govde)
    return m


def _dosyaya_yaz(mektup: EmailMessage, alici: str) -> None:
    kutu = _outbox()
    kutu.mkdir(parents=True, exist_ok=True)
    # Dosya adi guvenli hale getiriliyor: alici adresi yol ayiricilari
    # icerebilir ve outbox disina yazilmasi istenmez.
    guvenli = "".join(k if k.isalnum() or k in "@.-_" else "_" for k in alici)
    yol = kutu / f"{guvenli}.eml"
    yol.write_text(mektup.as_string(), encoding="utf-8")


def _smtp_gonder(mektup: EmailMessage) -> None:
    sunucu = os.getenv("SMTP_HOST")
    if not sunucu:
        raise RuntimeError("EMAIL_BACKEND=smtp ama SMTP_HOST ayarlanmamis.")
    port = int(os.getenv("SMTP_PORT", "587"))
    zaman_asimi = int(os.getenv("SMTP_TIMEOUT", "10"))
    kullanici = os.getenv("SMTP_USER")
    sifre = os.getenv("SMTP_PASSWORD")
    starttls = os.getenv("SMTP_STARTTLS", "1").strip().lower() in ("1", "true", "evet")

    with smtplib.SMTP(sunucu, port, timeout=zaman_asimi) as baglanti:
        if starttls:
            baglanti.starttls(context=ssl.create_default_context())
        if kullanici and sifre:
            baglanti.login(kullanici, sifre)
        baglanti.send_message(mektup)


def gonder(alici: str, konu: str, govde: str) -> None:
    """Mektubu gonderir. HATA YUTULMAZ AMA CAGRIYI DUSURMEZ.

    Bu fonksiyon arka plan gorevinden cagriliyor: SMTP cokmesi bir kayit
    istegini 500'e dusurmemeli (kullanici hesabini kaybetmis olurdu) ama
    sessizce de gecmemeli - aksi halde "mail gelmedi" sikayetinin sebebi
    hicbir yerde gorunmez.
    """
    mektup = _mektup(alici, konu, govde)
    arka = _arka_uc()
    try:
        if arka == "smtp":
            _smtp_gonder(mektup)
        elif arka == "console":
            print(f"\n--- E-POSTA ({alici}) ---\n{konu}\n\n{govde}\n---\n")
        else:
            _dosyaya_yaz(mektup, alici)
    except Exception as hata:  # noqa: BLE001
        print(f"[e-posta HATASI] {alici} icin gonderim basarisiz: {hata!r}")


def dogrulama_mektubu(alici: str, jeton: str) -> None:
    baglanti = f"{_taban_url()}/dogrula?token={jeton}"
    gonder(
        alici,
        "E-posta adresinizi doğrulayın",
        (
            "Merhaba,\n\n"
            "Değerlendirme sisteminde hesabınızı oluşturdunuz. Sonuçlarınızı "
            "görebilmek için e-posta adresinizi doğrulamanız gerekiyor:\n\n"
            f"{baglanti}\n\n"
            "Bu bağlantı 24 saat geçerlidir.\n\n"
            "Bu hesabı siz oluşturmadıysanız bu iletiyi yok sayabilirsiniz.\n"
        ),
    )


def sifirlama_mektubu(alici: str, jeton: str) -> None:
    baglanti = f"{_taban_url()}/sifre-sifirla?token={jeton}"
    gonder(
        alici,
        "Şifre sıfırlama",
        (
            "Merhaba,\n\n"
            "Şifrenizi sıfırlamak için aşağıdaki bağlantıyı kullanın:\n\n"
            f"{baglanti}\n\n"
            "Bu bağlantı 30 dakika geçerlidir ve yalnızca bir kez "
            "kullanılabilir.\n\n"
            "Şifre sıfırlama talebinde bulunmadıysanız bu iletiyi yok "
            "sayabilirsiniz; şifreniz değişmedi.\n"
        ),
    )


def zaten_kayitli_mektubu(alici: str) -> None:
    """Kayit denemesi yapilan adres ZATEN kayitliysa SAHIBINE gidiyor.

    NEDEN: kayit ucu "bu e-posta zaten kayitli" diye 400 dondurseydi, o
    cevap bir VARLIK KAHINI olurdu - herhangi biri adres deneyerek sistemde
    kimin hesabi oldugunu ogrenebilirdi. Uc her durumda ayni cevabi
    donduruyor; farki YALNIZCA posta kutusunun sahibi goruyor.
    """
    gonder(
        alici,
        "Hesabınız zaten var",
        (
            "Merhaba,\n\n"
            "Bu adresle yeni bir hesap oluşturulmaya çalışıldı, ancak zaten "
            "bir hesabınız var.\n\n"
            f"Giriş yapabilirsiniz: {_taban_url()}\n"
            "Şifrenizi hatırlamıyorsanız giriş ekranındaki "
            "\"Şifremi unuttum\" bağlantısını kullanın.\n\n"
            "Bu denemeyi siz yapmadıysanız yapmanız gereken bir şey yok.\n"
        ),
    )
