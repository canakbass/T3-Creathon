"""Dosya adindan e-posta cikarma testleri.

Kullanicinin verdigi gercek ornek:
  232805068@ogr.cbu.edu.tr_canakbasforspecial@gmail.com.pdf
Bu iki kisilik bir takimi temsil ediyor.

BU DOSYA NEDEN BU KADAR UZUN: cikarim bir REGEX ve regexler sessizce yanlis
yapar. Yanlis cikarilan bir adres, YABANCI birine bir takimin butun
sonuclarini vermek demek. Her vektor bir tuzagi kilitliyor.
"""

import pytest

from app.dosya_adi import (
    DosyaAdiHatasi,
    cozumle,
    eposta_normalle,
    takim_adi_uret,
    takim_anahtari,
)


def epostalari(ad):
    return cozumle(ad)["epostalar"]


def proje(ad):
    return cozumle(ad)["proje_adi"]


# --- Temel durumlar ------------------------------------------------------

def test_gercek_ornek_iki_kisilik_takim():
    assert epostalari("232805068@ogr.cbu.edu.tr_canakbasforspecial@gmail.com.pdf") == [
        "232805068@ogr.cbu.edu.tr",
        "canakbasforspecial@gmail.com",
    ]


def test_tek_eposta():
    """`.tr` ile `.docx` yan yana: uzanti soyulmazsa alan adi `cbu.edu.tr.docx`
    olurdu."""
    assert epostalari("ogrenci2@cbu.edu.tr.docx") == ["ogrenci2@cbu.edu.tr"]


def test_eposta_yoksa_bos_liste_ve_proje_adi():
    sonuc = cozumle("matematik_rapor.docx")
    assert sonuc["epostalar"] == []
    assert sonuc["proje_adi"] == "matematik rapor"


def test_hem_proje_adi_hem_eposta():
    sonuc = cozumle("Türkçe Proje Ödevi_a@b.com.pdf")
    assert sonuc["epostalar"] == ["a@b.com"]
    assert sonuc["proje_adi"] == "Türkçe Proje Ödevi"


# --- Uzanti tuzaklari ----------------------------------------------------

@pytest.mark.parametrize(
    "ad, beklenen",
    [
        # Acgozlu bir alan adi regexi `.pdf`i TLD sanir.
        ("a@b.com.pdf", ["a@b.com"]),
        ("a@b.com.pdf.pdf", ["a@b.com"]),
        ("a@b.com.PDF", ["a@b.com"]),
        ("a@b.com.docx", ["a@b.com"]),
        # `.zip` ve `.mov` GERCEK ust duzey alan adlari. Soyma listesi
        # yukleme beyaz listesiyle sinirli oldugu icin bunlar korunuyor.
        ("a@b.zip.pdf", ["a@b.zip"]),
        ("x@y.mov.pdf", ["x@y.mov"]),
    ],
)
def test_uzanti_alan_adina_yapismiyor(ad, beklenen):
    assert epostalari(ad) == beklenen


# --- Alt cizgi: hem ayirici hem yerel kisim ------------------------------

def test_yerel_kisimdaki_alt_cizgi_korunuyor():
    """Once-bol-sonra-dogrula yaklasimi tam burada patlardi: `ali_veli@x.com`
    ikiye bolunurdu."""
    assert epostalari("ali_veli@x.com.pdf") == ["ali_veli@x.com"]


def test_ayirici_ve_yerel_alt_cizgi_AYNI_ANDA():
    assert epostalari("a@b.com_ali_veli@x.com.pdf") == ["a@b.com", "ali_veli@x.com"]


def test_alan_adinda_alt_cizgi_YOK_sayiliyor():
    """Alan adi sinifina alt cizgi konsaydi `a@b.com_ali@x.com` TEK adres
    olarak yutulurdu."""
    assert epostalari("a@b.com_ali@x.com.pdf") == ["a@b.com", "ali@x.com"]


def test_belirsiz_yerel_kisim_UYARI_uretiyor():
    """`YAPAY_ZEKA_ali@x.com` icinde `ZEKA_ali` mi yerel kisim, `ali` mi?

    Regex bunu karara baglayamaz ve `ali_veli@x.com` gercek bir adres oldugu
    icin acgozlu okuma DOGRU varsayilan. Sessiz kalmiyoruz: yonetici
    ekranda duzeltebilsin diye uyari uretiyoruz.
    """
    sonuc = cozumle("YAPAY ZEKA_ali@ogr.cbu.edu.tr.docx")
    assert sonuc["epostalar"] == ["zeka_ali@ogr.cbu.edu.tr"]
    assert any("duzeltin" in u for u in sonuc["uyarilar"]), sonuc["uyarilar"]


# --- Turkce karakterler --------------------------------------------------

def test_turkce_harf_yerel_kisma_sizmiyor():
    """`re.ASCII` verilseydi `\\W` daralir ve `Ödevi_a@b.com` girdisi
    `devi_a@b.com` olarak yakalanirdi."""
    assert epostalari("Ödevi_a@b.com.pdf") == ["a@b.com"]
    assert epostalari("İSTANBUL_ŞUBE_a@b.com.PDF") == ["a@b.com"]


def test_turkce_proje_adi_korunuyor():
    assert proje("İSTANBUL_ŞUBE_a@b.com.PDF") == "İSTANBUL ŞUBE"


# --- E-posta gibi gorunup olmayanlar -------------------------------------

@pytest.mark.parametrize(
    "ad",
    [
        "rapor@2026.docx",   # alfabetik TLD yok
        "v1.2@final.pdf",    # uzanti soyulunca alan adi kalmiyor
        "hasan@com.pdf",     # noktasiz alan adi
    ],
)
def test_eposta_olmayanlar_yakalanmiyor(ad):
    assert epostalari(ad) == []


# --- Tekillestirme -------------------------------------------------------

def test_buyuk_kucuk_harf_tekillestiriliyor():
    assert epostalari("AYSE@GMAIL.COM_ayse@gmail.com.pdf") == ["ayse@gmail.com"]


def test_tekrar_eden_adres_bir_kez():
    assert epostalari("ogr@x.com_ogr@x.com_ogr@x.com.pdf") == ["ogr@x.com"]


# --- Kopya ekleri --------------------------------------------------------

@pytest.mark.parametrize(
    "ad, beklenen_proje",
    [
        ("dosya (1).pdf", "dosya"),
        ("dosya kopyasi.pdf", "dosya"),
        ("Rapor - Kopya (2).pdf", "Rapor"),
    ],
)
def test_kopya_ekleri_proje_adini_kirletmiyor(ad, beklenen_proje):
    assert proje(ad) == beklenen_proje


def test_kopya_eki_epostadan_SONRA_gelebilir():
    sonuc = cozumle("a@b.com (1).pdf")
    assert sonuc["epostalar"] == ["a@b.com"]
    assert sonuc["proje_adi"] is None


# --- Proje adi turetme ---------------------------------------------------

def test_bosluklar_daraltiliyor():
    sonuc = cozumle("  bosluklu  ad  _a@b.com .pdf")
    assert sonuc["epostalar"] == ["a@b.com"]
    assert sonuc["proje_adi"] == "bosluklu ad"


def test_parantezler_temizleniyor():
    sonuc = cozumle("TAKIM (SON HALI)_a@b.com_b@c.com.docx")
    assert sonuc["epostalar"] == ["a@b.com", "b@c.com"]
    assert sonuc["proje_adi"] == "TAKIM SON HALI"


def test_anlamli_harf_yoksa_proje_adi_UYDURULMUYOR():
    """"Isimsiz Rapor" gibi bir sey uydurmak, gercekten adi olmayan raporlari
    ayirt edilemez kilardi. Cagiran taraf orijinal dosya adina ya da rapor
    kimligine dusebilir."""
    assert proje("1_2_3.pdf") is None
    assert proje("a@b.com.pdf") is None


# --- Yol ve guvenlik -----------------------------------------------------

def test_yol_bilesenleri_atiliyor():
    """Basename alinmazsa `..` disk yoluna donusebilir."""
    assert epostalari("../../etc/passwd@x.com.pdf") == ["passwd@x.com"]


def test_windows_tam_yolu():
    """Tarayicilar bazen tam yol gonderiyor ve Linux'ta `os.path.basename`
    ters egik cizgiyi ayirici saymiyor."""
    assert epostalari("C:\\Users\\x\\Rapor_a@b.com.pdf") == ["rapor_a@b.com"]


def test_NUL_karakteri_SESSIZCE_kirpilmiyor():
    """Kirpilsaydi e-posta kaybolur ve kullanici bunu fark etmezdi."""
    with pytest.raises(DosyaAdiHatasi):
        cozumle("rapor\x00.exe_a@b.com.pdf")


def test_cok_uzun_ad_reddediliyor():
    """ReDoS savunmasi regexin kendisi degil, bu kirpma."""
    with pytest.raises(DosyaAdiHatasi):
        cozumle("a" * 300 + "@b.com.pdf")


def test_cok_fazla_adres_TUMDEN_reddediliyor():
    """Kirpsaydik cikarilmayan adresler proje adina duser ve yonetici EKSIK
    bir takimi onaylamis olurdu."""
    ad = "_".join(f"u{i}@x.com" for i in range(12)) + ".pdf"
    with pytest.raises(DosyaAdiHatasi) as hata:
        cozumle(ad)
    assert "elle girin" in str(hata.value)


def test_bos_ad_reddediliyor():
    for kotu in ("", "   ", None):
        with pytest.raises(DosyaAdiHatasi):
            cozumle(kotu)


# --- Mesru ozel durumlar -------------------------------------------------

def test_alan_adinda_tire_mesru():
    assert epostalari("a@b-c.com.tr.pdf") == ["a@b-c.com.tr"]


def test_etiketli_adres_bozulmuyor():
    """`team+2026@x.com` gecerli bir adres (gmail etiketi)."""
    assert epostalari("team+2026@x.com.pdf") == ["team+2026@x.com"]


def test_tire_ile_ayrilmis_adresler():
    """Tire alan adinda mesru oldugu icin regex tek basina cozemiyor;
    govdede birden fazla @ varsa ayirici olarak deneniyor."""
    sonuc = cozumle("a@b.com-c@d.com.pdf")
    assert sonuc["epostalar"] == ["a@b.com", "c@d.com"]
    assert sonuc["uyarilar"], "tire yorumu sessizce yapilmamali"


# --- Normalleme ve takim anahtari ----------------------------------------

def test_eposta_normalleme_TURKCE_KATLAMIYOR():
    """`models.turkce_katla` arama kutusunda dogru, KIMLIKTE felaket:
    `karaş@x.com` ile `karas@x.com` FARKLI kisilerdir ve katlanirlarsa
    birinin raporunu digeri gorur."""
    assert eposta_normalle("  KaraŞ@X.com ") == "karaş@x.com"
    assert eposta_normalle("karas@x.com") != eposta_normalle("karaş@x.com")


def test_takim_anahtari_SIRADAN_bagimsiz():
    """Sira degisince ayni ekip iki farkli takima dagilirdi ve o takimlarin
    uyeleri birbirinin sonucunu goremezdi."""
    a = takim_anahtari(["b@x.com", "a@x.com"])
    b = takim_anahtari(["a@x.com", "B@x.com"])
    assert a == b == "eposta:a@x.com,b@x.com"


def test_takim_adi_okunabilir():
    assert takim_adi_uret(["ali@x.com"]) == "ali"
    assert takim_adi_uret(["ali@x.com", "veli@y.com"]) == "ali +1"
    assert takim_adi_uret([]) == "Takim"
