"""Dosya adindan TAKIM cikarma.

KULLANICININ ISTEGI: "yonetici raporu teslim eden kisilerin mailini girsin ya
da GONDERILEN DOSYALAR UZERINDEN isimlendirilebilsin; atiyorum
`232805068@ogr.cbu.edu.tr_canakbasforspecial@gmail.com` bu isimli dosya iki
kisiden olusan bir takimi temsil ediyor."

NEDEN: yukleme ekrani yoneticiden "takim kimligi" istiyordu ve bu, elinde
olmayan bir bilgiydi. Yoneticinin GERCEKTEN elinde olan sey teslim edilen
dosyalar ve o dosyalari kimin gonderdigi. Takim, e-posta kumesinden
turetiliyor.

BU MODUL KARAR VERMIYOR, ONERIYOR. Cikarim sezgisel; sonuc yoneticiye
gosteriliyor ve o onaylamadan hicbir takim/uyelik olusmuyor. Sebep guvenlik:
dogrulama "bu kutunun sahibi misin" sorusunu cevaplar, "bu kisi bu takimda
mi" sorusunu cevaplamaz. Dosya adindaki bir harf hatasi (ahmet.yilmiz@...)
dogrulamayi gecen YABANCI birine o takimin tum sonuclarini verirdi.
"""

import os
import re
import unicodedata

# Yukleme beyaz listesiyle AYNI olmali (routes/reports.py).
#
# NEDEN TLD LISTESI DEGIL: `.zip`, `.mov`, `.app` hem dosya uzantisi hem
# GERCEK ust duzey alan adi. Soyma listesi genis tutulursa `a@b.zip` gecerli
# bir adresken uzanti sanilip kirpilir. Yalnizca kabul ettigimiz uc uzantiyi
# soyuyoruz.
UZANTILAR = ("pdf", "docx", "doc")
_UZANTI = re.compile(r"\.(?:" + "|".join(UZANTILAR) + r")$", re.IGNORECASE)

# Windows/macOS/Turkce kopya ekleri: "dosya (1).pdf", "Rapor - Kopya (2).pdf"
_KOPYA_EKI = re.compile(
    r"(?:\s*\(\d{1,3}\)|\s*[-–]\s*kopya|\s*kopyas[ıi]|\s*[-–]\s*copy)\s*$",
    re.IGNORECASE,
)

# E-POSTA DESENI.
#
# Uc parcasi da bilincli:
#
# `(?<![^\W_])` -> "harf ya da rakamla BITISIK baslama, ama alt cizgiden
#   sonra baslayabil". Ayirici alt cizgi, e-postanin yerel kismi da alt cizgi
#   icerebiliyor; `a@b.com_ali_veli@x.com` girdisinde ikinci adresin
#   `_ali_veli` degil `ali_veli` olarak baslamasini saglayan sey budur.
#
# Alan adi sinifinda ALT CIZGI YOK. Olsaydi `a@b.com_ali@x.com` tek bir
#   adres olarak yutulurdu; ayirici ayrimini tamamen bu kisit sagliyor.
#
# Sondaki `(?![A-Za-z0-9-])` -> `\w` YAZILMAMALI. `\w` alt cizgiyi de
#   kapsadigi icin `...edu.tr_can@...` girdisinde motor `edu.tr` yerine
#   `edu`ya geri izler ve artiga `tr` duser.
#
# `re.ASCII` VERILMIYOR: verilseydi `\W` daralir ve `Ödevi_a@b.com` girdisi
#   `devi_a@b.com` olarak yakalanirdi (Turkce harf sinir sayilmazdi).
_EPOSTA = re.compile(
    r"(?<![^\W_])(?<![.%+\-@])"
    r"([A-Za-z0-9](?:[A-Za-z0-9_.%+\-]{0,62}[A-Za-z0-9])?)"
    r"@"
    r"((?:[A-Za-z0-9](?:[A-Za-z0-9\-]{0,61}[A-Za-z0-9])?\.){1,8}[A-Za-z]{2,24})"
    r"(?![A-Za-z0-9\-])"
)

# Bir dosya adindan en fazla kac e-posta kabul ediyoruz.
#
# Ust sinir asilirsa SONUCU TUMDEN REDDEDIYORUZ, kirpmiyoruz: kirpsaydik
# cikarilmayan adresler proje adina duser ve yonetici eksik bir takimi
# onaylamis olurdu.
EN_FAZLA_EPOSTA = 10

# Dosya adi tavani. ReDoS savunmasi regexin kendisi degil, bu kirpma.
EN_FAZLA_UZUNLUK = 255


class DosyaAdiHatasi(ValueError):
    """Dosya adi guvenle ayristirilamiyor - sessizce duzeltmek yerine soyluyoruz."""


def _temel_ad(dosya_adi: str) -> str:
    """Yol bilesenlerini atar.

    HEM POSIX HEM WINDOWS: tarayicilar bazen `C:\\Users\\x\\rapor.pdf`
    gonderiyor ve Linux'ta `os.path.basename` ters egik cizgiyi ayirici
    saymiyor - o durumda tum yol dosya adi sanilirdi.
    """
    ad = dosya_adi.replace("\\", "/")
    return os.path.basename(ad)


def _ekleri_soy(govde: str) -> str:
    """Uzantiyi ve kopya ekini SONDAN, cok turlu soyar.

    Cok turlu, cunku zincirlenebiliyorlar: `Rapor - Kopya (2).pdf`,
    `a@b.com.pdf.pdf`. Tur sinirli - sonsuz dongu olmasin.
    """
    for _ in range(6):
        yeni = _KOPYA_EKI.sub("", _UZANTI.sub("", govde)).strip()
        if yeni == govde:
            break
        govde = yeni
    return govde


def _proje_adi(artik: str):
    """E-postalar cikarildiktan sonra kalan metinden okunabilir bir ad.

    Hicbir sey kalmazsa None doner - "Isimsiz Rapor" gibi bir sey UYDURMAK
    yanlis olurdu: cagiran taraf zaten orijinal dosya adina ya da rapor
    kimligine dusebilir ve uydurulan ad, gercekten adi olmayan raporlari
    ayirt edilemez kilardi.
    """
    metin = re.sub(r"[_\-.]+", " ", artik)
    metin = re.sub(r"[()\[\]{}]", " ", metin)
    metin = re.sub(r"\s+", " ", metin).strip()
    # Anlamli en az bir harf yoksa ad sayilmaz ("1_2_3" -> None).
    if not metin or not any(k.isalpha() for k in metin):
        return None
    return metin


def cozumle(dosya_adi: str) -> dict:
    """Dosya adini {epostalar, proje_adi, uyarilar} olarak cozumler.

    Doner:
      epostalar : sirasi korunmus, tekillestirilmis, kucuk harfli liste
      proje_adi : artik metinden turetilen ad ya da None
      uyarilar  : yoneticiye gosterilecek notlar (bos olabilir)

    Bozuk/tehlikeli girdide DosyaAdiHatasi firlatir - sessizce kirpmak,
    kullanicinin fark edemeyecegi bir veri kaybi olurdu.
    """
    if dosya_adi is None:
        raise DosyaAdiHatasi("Dosya adi bos.")

    # NUL ve kontrol karakterleri: `rapor\x00.exe_a@b.com.pdf` gibi girdiler
    # sessizce kirpilirsa e-posta kaybolur ve kimse fark etmez.
    if any(ord(k) < 32 or ord(k) == 127 for k in dosya_adi):
        raise DosyaAdiHatasi("Dosya adinda gecersiz karakter var.")

    ad = unicodedata.normalize("NFC", _temel_ad(dosya_adi).strip())
    if not ad:
        raise DosyaAdiHatasi("Dosya adi bos.")
    if len(ad) > EN_FAZLA_UZUNLUK:
        raise DosyaAdiHatasi(
            f"Dosya adi cok uzun ({len(ad)} karakter, en fazla {EN_FAZLA_UZUNLUK})."
        )

    govde = _ekleri_soy(ad)

    uyarilar = []
    # `-` ile ayrilmis adresler: `a@b.com-c@d.com`. Tire alan adinda mesru
    # oldugu icin regex bunu tek basina cozemez; govdede birden fazla `@`
    # varsa tireyi ayiriciya cevirip bir kez daha deniyoruz.
    if govde.count("@") > 1 and "-" in govde and len(_EPOSTA.findall(govde)) < 2:
        aday = govde.replace("-", "_")
        if len(_EPOSTA.findall(aday)) > len(_EPOSTA.findall(govde)):
            govde = aday
            uyarilar.append("Adresler tire ile ayrilmis gibi gorunuyor; oyle okundu.")

    epostalar = []
    gorulen = set()
    artik_parcalari = []
    son = 0
    for eslesme in _EPOSTA.finditer(govde):
        artik_parcalari.append(govde[son : eslesme.start()])
        son = eslesme.end()
        yerel, alan = eslesme.group(1), eslesme.group(2)
        # RFC uzunluk sinirlari: bunlari asan sey e-posta degildir.
        if len(yerel) > 64 or len(alan) > 255:
            uyarilar.append(f"Cok uzun bir adres atlandi: {yerel[:20]}...")
            continue
        adres = f"{yerel}@{alan}".lower()
        if adres in gorulen:
            continue
        gorulen.add(adres)
        epostalar.append(adres)
        # YEREL KISIM BELIRSIZLIGI: `YAPAY_ZEKA_ali@x.com` icinde `ZEKA_ali`
        # mi yerel kisim, `ali` mi? Regex bunu karara baglayamaz ve
        # `ali_veli@x.com` gercek bir adres oldugu icin acgozlu okuma DOGRU
        # varsayilan. Yonetici onaylamadan hicbir sey olusmadigi icin nadir
        # yanlislar ekranda duzeltiliyor - ama sessiz kalmiyoruz.
        if "_" in yerel:
            uyarilar.append(
                f"{adres} adresinin basindaki bolum proje adinin parcasi olabilir; "
                "yanlissa duzeltin."
            )
    artik_parcalari.append(govde[son:])

    if len(epostalar) > EN_FAZLA_EPOSTA:
        raise DosyaAdiHatasi(
            f"Dosya adinda {len(epostalar)} adres var (en fazla {EN_FAZLA_EPOSTA}). "
            "Takim uyelerini elle girin."
        )

    return {
        "epostalar": epostalar,
        "proje_adi": _proje_adi(" ".join(artik_parcalari)),
        "uyarilar": uyarilar,
    }


def eposta_normalle(adres: str) -> str:
    """E-posta karsilastirmasi icin TEK kural: kirp + kucult.

    TURKCE KATLAMA BURADA KULLANILMAZ. `models.turkce_katla` `ş`yi `s`ye,
    `ı`yi `i`ye ceviriyor - arama kutusunda dogru, kimlikte FELAKET:
    `karaş@x.com` ile `karas@x.com` FARKLI kisilerdir ve katlanirlarsa
    birinin raporunu digeri gorur.
    """
    return (adres or "").strip().lower()


def takim_adi_uret(epostalar) -> str:
    """E-posta kumesinden okunabilir bir takim adi.

    Yerel kisimlar yeterince ayirt edici ve tam adresleri ekrana basmak
    gereksiz yere uzun. Ad yalnizca GORUNTU icin - eslestirme her zaman
    e-posta kumesi uzerinden yapiliyor.
    """
    yereller = [a.split("@", 1)[0] for a in epostalar if "@" in a]
    if not yereller:
        return "Takim"
    if len(yereller) == 1:
        return yereller[0]
    return f"{yereller[0]} +{len(yereller) - 1}"


def takim_anahtari(epostalar) -> str:
    """Ayni e-posta kumesi HER ZAMAN ayni takima esleşsin diye kararli anahtar.

    Sirali ve tekillestirilmis: dosya adinda uyelerin sirasi degisirse ayni
    takimin ikinci kez olusturulmasi, ayni ekibin raporlarinin iki farkli
    takima dagilmasi demekti - ve o takimlarin uyeleri birbirinin sonucunu
    goremezdi.
    """
    return "eposta:" + ",".join(sorted({eposta_normalle(a) for a in epostalar}))
