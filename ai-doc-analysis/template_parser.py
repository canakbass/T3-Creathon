"""ORNEK SABLON DOSYASINDAN yarisma kurallarini cikarir (PROTOTIP).

NE ISE YARIYOR
--------------
Yarisma Yoneticisi, TEKNOFEST'in yayinladigi RESMI sablon dosyasini
(sablon_OTR_2026.docx gibi) yukler; bu modul dosyadan
  * zorunlu bolum basliklarini            -> Competition.required_headings
  * kriterleri ve AGIRLIKLARINI           -> CompetitionCriterion(title, weight)
cikarir. Yonetici bunlari elle yazmak yerine gozden gecirip onaylar.

NEDEN BU MUMKUN (olculdu, varsayim degil)
-----------------------------------------
Gercek sablon dosyalarinda basliklar Word'un BASLIK STILIYLE isaretli ve
puan agirligi basligin kendi metninde parantez icinde yaziyor:

  sablon_OTR_2026.docx        -> stil "Balk1" (heading 1, outlineLvl=0)
      TAKIM SEMASI
      PROJE MEVCUT DURUM DEGERLENDIRMESI (10 Puan)
      ALGORITMALAR VE SISTEM MIMARISI (30 PUAN)
      ...
  referans_2026_pdr_..._universite.docx -> stil "Balk3" (heading 3, outlineLvl=2)
      1. GIRIS (10 puan)
      2. YONTEM (25 puan)
      ...

Iki onemli tuzak var ve ikisi de bu dosyalarda GERCEKTEN cikiyor:

1) "Heading 1 olanlari al" YANLIS. Ikinci dosyada tum basliklar heading 3.
   Bu yuzden sabit bir seviye secmiyoruz; her (baslik seviyesi, liste
   girinti seviyesi) grubunu ayri ayri deneyip AGIRLIKLARI TAM 100 EDEN
   grubu seciyoruz. Toplam 100 kurali sartnamenin kendi kuralidir, bu yuzden
   hem secim olcutu hem de dogrulama olarak kullanilabiliyor.

2) "Butun (N Puan) ifadelerini topla" YANLIS. OTR dosyasinda
   "ALGORITMALAR VE SISTEM MIMARISI (30 PUAN)" basliginin altinda ayni Word
   stiliyle ama BIR GIRINTI ICERIDE (numPr/ilvl=1) uc alt baslik var:
   "Veri Setleri (10 Puan)", "Algoritmalar (15 Puan)", "Akis Semasi (5 Puan)".
   Bunlar EK kriter degil, ustteki 30 puanin DAGILIMI. Hepsini toplarsak
   100 yerine 130 cikar. Girinti seviyesine gore ayirmak bunu onluyor.

GUVEN SEVIYESI
--------------
  "yuksek" : agirliklar tam 100 ediyor ve basliklar Word baslik stilinden geldi.
  "orta"   : basliklar stilden geldi ama toplam 100 degil (ya da hic puan yok).
  "dusuk"  : PDF'ten sezgisel (yazi tipi boyutu/kalinlik) cikarildi.

Cikan sonuc HICBIR ZAMAN dogrudan kaydedilmez; yonetici duzenleyip onaylar.
Bkz. backend/app/routes/competitions.py -> /template-onizle ucu.

BAGIMLILIK YOK: .docx bir ZIP arsividir, icindeki word/document.xml duz XML.
Python'un standart kutuphanesindeki zipfile + xml.etree yetiyor; python-docx
kurmaya gerek kalmiyor. PDF yedegi icin zaten kurulu olan pdfplumber
kullaniliyor.
"""

from __future__ import annotations

import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

# "(10 Puan)", "(30 PUAN)", "(ve RAPOR DUZENI 10 PUAN)" -> 10 / 30 / 10
_PUAN = re.compile(r"(\d{1,3})\s*puan", re.IGNORECASE)
# Basliktaki puan parantezi: "OZGUNLUK (10 Puan)" -> "OZGUNLUK"
_PUAN_PARANTEZ = re.compile(r"[\(\[][^()\[\]]*\d{1,3}\s*puan[^()\[\]]*[\)\]]", re.IGNORECASE)
# Elle yazilmis basliklar: "1. GIRIS", "2.3 Yontem", "IV. Sonuc" ve BOSLUKSUZ
# hali "2.PROJE MEVCUT DURUM" (PDF'e cevrilmis sablonlarda boyle cikiyor).
# Bosluksuz halde ardindan bir HARF gelmesini sart kosuyoruz, yoksa
# "3.5 kg" gibi ifadelerin basi kirpilirdi.
_NUMARA_ONEKI = re.compile(
    r"^\s*(?:\d+(?:\.\d+)*[\.\)]?|[IVXLC]+[\.\)])(?:\s+|(?=[A-Za-zÇĞİÖŞÜçğıöşü]))"
)
# Basligin numara DERINLIGI: "3." -> 1, "3.1." -> 2. PDF'te ust/alt baslik
# ayrimi icin tek isaret bu (bkz. _pdf_basliklari).
_NUMARA_DERINLIGI = re.compile(r"^\s*(\d+(?:\.\d+)*)[\.\)]?(?:\s|[A-Za-zÇĞİÖŞÜçğıöşü])")
# "Heading 3", "Baslik 3", "Balk3", "Baslk 3"
_STIL_SEVIYE = re.compile(r"(?:heading|ba[sş]l[iı]?k|balk)\s*([1-9])", re.IGNORECASE)

# outlineLvl 9 = "govde metni" demek; Word bunu TOC Heading gibi stillere de
# veriyor. Baslik saymiyoruz.
_GOVDE_SEVIYESI = 9


# --- Govde metninden cikarilabilen EK kurallar -------------------------------
# Iki gercek sablon dosyasi da sayfa sinirini duz metin olarak yaziyor:
#   OTR: "Toplam sayfa sayisi en az 6 sayfa en fazla 15 sayfa olmalidir."
#   PDR: "rapor 10 sayfayi gecmemelidir."
_ARALIK = re.compile(r"en\s*az\s*(\d{1,3})\s*sayfa.{0,30}?en\s*(?:fazla|çok)\s*(\d{1,3})\s*sayfa", re.IGNORECASE | re.DOTALL)
_EN_AZ = re.compile(r"en\s*az\s*(\d{1,3})\s*sayfa", re.IGNORECASE)
_EN_FAZLA = re.compile(r"en\s*(?:fazla|çok)\s*(\d{1,3})\s*sayfa", re.IGNORECASE)
_GECMEMELI = re.compile(r"(\d{1,3})\s*sayfa(?:y[ıi])?\s*(?:ge[çc]me|a[şs]ma)", re.IGNORECASE)
# "HAVACILIKTA YAPAY ZEKA YARISMASI ON TASARIM RAPORU" -> "On Tasarim Raporu"
_RAPOR_TURU = re.compile(r"([A-ZÇĞİÖŞÜ][A-ZÇĞİÖŞÜ ]{2,40}RAPORU)")
# K1: TEKNOFEST'te "kategori" = KATILIMCI SEVIYESI. Sablon dosyasi bunu
# kapak sayfasinda yaziyor ("Yarisma Egitim Seviyesi: Universite ve Uzeri").
_SEVIYE = re.compile(r"(?:Yarışma\s*)?E[ğg]itim\s*Seviyesi\s*[:：]\s*([^\n]{3,60})", re.IGNORECASE)


class SablonOkunamadi(Exception):
    """Dosya sablon olarak ayristirilamadi (bozuk, sifreli ya da eski .doc)."""


# --------------------------------------------------------------- yardimcilar


def _stil_haritasi(z: zipfile.ZipFile) -> dict:
    """styleId -> (ad, outlineLvl, basedOn)."""
    try:
        kok = ET.fromstring(z.read("word/styles.xml"))
    except (KeyError, ET.ParseError):
        return {}
    harita = {}
    for st in kok.iter(W + "style"):
        sid = st.get(W + "styleId")
        if not sid:
            continue
        ad_el = st.find(W + "name")
        ol_el = st.find(W + "pPr/" + W + "outlineLvl")
        dayanak = st.find(W + "basedOn")
        harita[sid] = (
            ad_el.get(W + "val") if ad_el is not None else None,
            int(ol_el.get(W + "val")) if ol_el is not None else None,
            dayanak.get(W + "val") if dayanak is not None else None,
        )
    return harita


def _stil_seviyesi(sid: Optional[str], harita: dict, derinlik: int = 0) -> Optional[int]:
    """Stilin baslik seviyesi. Once outlineLvl, sonra stil ADI, sonra basedOn.

    basedOn zinciri takip ediliyor cunku sablonlarda "Balk1Ozel" gibi
    turetilmis stiller var ve outlineLvl'i yalnizca ata stilde tanimli.
    `derinlik` sonsuz donguye karsi (bozuk dosyada basedOn kendine isaret
    edebiliyor).
    """
    if not sid or derinlik > 5:
        return None
    ad, lvl, dayanak = harita.get(sid, (None, None, None))
    if lvl is not None:
        return lvl
    for aday in (ad, sid):
        if aday:
            m = _STIL_SEVIYE.search(aday)
            if m:
                return int(m.group(1)) - 1
    return _stil_seviyesi(dayanak, harita, derinlik + 1)


def _kapsayici_mi(p: ET.Element) -> bool:
    """Icinde BASKA paragraf barindiran paragraf mi.

    Kapak sayfasi metin kutusu/tablo icinde kuruldugunda Word ic ice <w:p>
    uretiyor ve ET.iter() once DIS paragrafi veriyor - onun metni tum ic
    paragraflarin BIRLESIMI oluyor ("... RAPORUGOREV: ... Takim Adi:").
    Bu birlesik dev satir hem sahte baslik uretiyor hem de duz metin
    kurallarini (sayfa siniri, egitim seviyesi) yanlis kirpiyor. Kapsayici
    paragraflar atlanip yalnizca ic paragraflar okunuyor.
    """
    return p.find(".//" + W + "p") is not None


def _paragraf_metni(p: ET.Element) -> str:
    parcalar = []
    for dugum in p.iter():
        if dugum.tag == W + "t":
            parcalar.append(dugum.text or "")
        elif dugum.tag in (W + "tab", W + "br"):
            parcalar.append(" ")
    return re.sub(r"\s+", " ", "".join(parcalar)).strip()


def _agirlik(metin: str) -> Optional[int]:
    m = _PUAN.search(metin)
    return int(m.group(1)) if m else None


def _basligi_temizle(metin: str) -> str:
    """Puan parantezini ve elle yazilmis numarayi atar.

    ZORUNLU: analyzer.py zorunlu basliklari rapor METNINDE duz altdizge
    olarak ariyor. "OZGUNLUK (10 Puan)" oldugu gibi kaydedilirse hicbir
    raporda bulunamaz ve HER rapor "eksik baslik" alir.
    """
    metin = _PUAN_PARANTEZ.sub(" ", metin)
    metin = _NUMARA_ONEKI.sub("", metin)
    metin = re.sub(r"\s+", " ", metin).strip()
    return metin.strip(" .:-–—")


def _tf_kucult(s: str) -> str:
    """analyzer._turkish_casefold ile AYNI kural (I/i tuzagi)."""
    return s.replace("İ", "i").replace("I", "ı").lower()


def _tr_baslik_yap(s: str) -> str:
    """Turkce'ye uygun baslik bicimi.

    Python'un str.title()'i Turkce bilmiyor: "ON TASARIM RAPORU".title()
    "On Tasarim Raporu" veriyor - 'I' harfi 'i'ye donuyor, 'ı' olmasi
    gerekirken. Once Turkce kucultup sonra ilk harfleri buyutuyoruz.
    """
    kelimeler = []
    for k in _tf_kucult(s).split():
        kelimeler.append((k[0].replace("i", "İ").upper() + k[1:]) if k else k)
    return " ".join(kelimeler)


# ------------------------------------------------------------------- docx


def _docx_basliklari(yol: str) -> list:
    """Belge sirasinda [(seviye, ilvl, ham_metin)] doner."""
    try:
        z = zipfile.ZipFile(yol)
    except zipfile.BadZipFile as exc:
        raise SablonOkunamadi(
            "Dosya .docx olarak acilamadi. Eski Word bicimi (.doc) ya da bozuk "
            "olabilir; Word'de 'Farkli Kaydet -> .docx' yapip tekrar deneyin."
        ) from exc
    with z:
        try:
            bilgi = z.getinfo("word/document.xml")
        except KeyError as exc:
            raise SablonOkunamadi("Dosyada word/document.xml yok.") from exc
        # ZIP BOMBASI KORUMASI: .docx bir zip arsivi. Kucuk bir dosya
        # acildiginda gigabaytlarca XML'e donusebilir ve sunucunun bellegini
        # tuketir. Gercek sablonlarda document.xml 68-147 KB; 64 MB fazlasiyla
        # genis bir sinir ama bombayi durduruyor.
        if bilgi.file_size > 64 * 1024 * 1024:
            raise SablonOkunamadi(
                "Sablon icerigi olagandisi buyuk (>64 MB); dosya bozuk ya da "
                "zararli olabilir."
            )
        govde = z.read("word/document.xml")
        harita = _stil_haritasi(z)
        try:
            kok = ET.fromstring(govde)
        except ET.ParseError as exc:
            raise SablonOkunamadi(f"word/document.xml ayristirilamadi: {exc}") from exc

    cikti = []
    tum_metin = []
    for p in kok.iter(W + "p"):
        if _kapsayici_mi(p):
            continue
        tum_metin.append(_paragraf_metni(p))
        ppr = p.find(W + "pPr")
        sid = None
        dogrudan = None
        ilvl = None
        if ppr is not None:
            ps = ppr.find(W + "pStyle")
            if ps is not None:
                sid = ps.get(W + "val")
            ol = ppr.find(W + "outlineLvl")
            if ol is not None:
                dogrudan = int(ol.get(W + "val"))
            npr = ppr.find(W + "numPr")
            if npr is not None:
                il = npr.find(W + "ilvl")
                if il is not None:
                    ilvl = int(il.get(W + "val"))
        seviye = dogrudan if dogrudan is not None else _stil_seviyesi(sid, harita)
        if seviye is None or seviye >= _GOVDE_SEVIYESI:
            continue
        metin = _paragraf_metni(p)
        if not metin:
            continue
        cikti.append((seviye, ilvl, metin))
    return cikti, "\n".join(t for t in tum_metin if t)


# -------------------------------------------------------------------- pdf


def _pdf_basliklari(yol: str) -> list:
    """PDF'te baslik SEZGISEL bulunur - docx kadar guvenilir DEGIL.

    OLCUM (sablon_OTR_2026.docx -> PDF'e cevrilip test edildi): PDF'te
    "3.ALGORITMALAR VE SISTEM MIMARISI (30 PUAN)" ile onun alt basligi
    "3.1.Veri Setleri (10 Puan)" AYNI puntoda (14.0) ve AYNI yazi tipinde
    yaziliyor. Yani ust/alt baslik ayrimini yapacak TIPOGRAFIK isaret yok;
    docx'teki numPr/ilvl bilgisi PDF'e cevrilirken kayboluyor. Elde kalan
    tek isaret basliktaki numaranin derinligi ("3." tek, "3.1." iki
    kademe) - onu grup anahtari olarak kullaniyoruz. Sablon numarasiz
    yazilmissa bu isaret de yoktur; o durumda agirlik toplami 100'u tutmaz
    ve kullanici uyarilir.

    Ayrica PDF'te kapak sayfasi ("Takim Adi", "Basvuru ID") ve icindekiler
    satirlari da buyuk puntoda oldugu icin baslik sanilabiliyor; nokta
    dizisi (leader) iceren satirlari ve numara derinligi olmayan puanlanmamis
    satirlari eliyoruz.
    """
    import pdfplumber

    satirlar = []
    with pdfplumber.open(yol) as pdf:
        for sayfa in pdf.pages:
            gruplar = {}
            for ch in sayfa.chars:
                gruplar.setdefault(round(ch["top"] / 3), []).append(ch)
            for _, chars in sorted(gruplar.items()):
                chars.sort(key=lambda c: c["x0"])
                metin = re.sub(r"\s+", " ", "".join(c["text"] for c in chars)).strip()
                if not metin:
                    continue
                punto = max(round(c["size"], 1) for c in chars)
                satirlar.append((metin, punto))

    tum_metin = "\n".join(m for m, _ in satirlar)
    if not satirlar:
        return [], ""
    sayac = {}
    for _, punto in satirlar:
        sayac[punto] = sayac.get(punto, 0) + 1
    govde = max(sayac, key=sayac.get)

    cikti = []
    for metin, punto in satirlar:
        if len(metin) > 120 or punto <= govde + 0.4:
            continue
        if "...." in metin:  # icindekiler satiri
            continue
        m = _NUMARA_DERINLIGI.match(metin)
        derinlik = len(m.group(1).split(".")) if m else 0
        # Numarasiz ve puansiz satirlar kapak/liste basligi olma egiliminde.
        if derinlik == 0 and _agirlik(metin) is None:
            continue
        cikti.append((int(punto * 10), derinlik, metin))
    return cikti, tum_metin


# ------------------------------------------------------------------ secim


def _grup_sec(basliklar: list) -> tuple:
    """(secilen_anahtar, gruplar) - agirliklari TAM 100 eden grubu secer.

    Grup anahtari (baslik_seviyesi, liste_girinti_seviyesi). Toplam 100 eden
    yoksa en sig (en ust) seviyeli, en az iki ogeli gruba dusuyoruz ve
    cagiran taraf bunu uyari olarak bildiriyor.
    """
    gruplar = {}
    for seviye, ilvl, metin in basliklar:
        gruplar.setdefault((seviye, ilvl), []).append(metin)

    tam_yuz = [
        anahtar
        for anahtar, ogeler in gruplar.items()
        if sum(_agirlik(m) or 0 for m in ogeler) == 100
        and any(_agirlik(m) for m in ogeler)
    ]
    if tam_yuz:
        # Birden fazlaysa en sig seviye (ilvl None'i 0 sayarak).
        return min(tam_yuz, key=lambda a: (a[0], a[1] if a[1] is not None else 0)), gruplar

    adaylar = [a for a, o in gruplar.items() if len(o) >= 2] or list(gruplar)
    if not adaylar:
        return None, gruplar
    return min(adaylar, key=lambda a: (a[0], a[1] if a[1] is not None else 0)), gruplar


# ------------------------------------------------------------- genel giris


def sablondan_cikar(yol: str) -> dict:
    """Sablon dosyasindan yarisma kurallarini cikarir.

    Doner:
      {
        "bicim": "docx" | "pdf",
        "guven": "yuksek" | "orta" | "dusuk",
        "zorunlu_basliklar": [str, ...],
        "kriterler": [{"baslik": str, "agirlik": int}, ...],
        "agirlik_toplami": int,
        "alt_basliklar": [{"baslik": str, "agirlik": int|None, "ust": str}, ...],
        "uyarilar": [str, ...],
      }
    """
    uzanti = Path(yol).suffix.lower()
    if uzanti == ".docx":
        bicim = "docx"
        basliklar, govde = _docx_basliklari(yol)
    elif uzanti == ".pdf":
        bicim = "pdf"
        basliklar, govde = _pdf_basliklari(yol)
    elif uzanti == ".doc":
        raise SablonOkunamadi(
            "Eski Word bicimi (.doc) okunamiyor. Word'de acip "
            "'Farkli Kaydet -> Word Belgesi (.docx)' yapin."
        )
    else:
        raise SablonOkunamadi(f"Desteklenmeyen dosya turu: {uzanti or '(uzantisiz)'}")

    uyarilar = []
    if not basliklar:
        raise SablonOkunamadi(
            "Dosyada Word baslik stiliyle isaretlenmis hicbir baslik bulunamadi. "
            "Sablon basliklari duz metin olarak yazilmis olabilir; kurallari "
            "elle girmeniz gerekiyor."
        )

    secilen, gruplar = _grup_sec(basliklar)
    ana = gruplar.get(secilen, [])

    kriterler = []
    zorunlu = []
    gorulen = set()
    for ham in ana:
        temiz = _basligi_temizle(ham)
        if not temiz or len(temiz) < 2:
            continue
        anahtar = _tf_kucult(temiz)
        if anahtar in gorulen:
            uyarilar.append(f"'{temiz}' basligi birden fazla kez geciyor; biri atlandi.")
            continue
        gorulen.add(anahtar)
        zorunlu.append(temiz)
        ag = _agirlik(ham)
        if ag is not None:
            kriterler.append({"baslik": temiz, "agirlik": ag})
            # "(ve RAPOR DUZENI 10 PUAN)" gibi parantezler tek basligin
            # icine IKI kriter sikistiriyor - yonetici bolmek isteyebilir.
            m = _PUAN_PARANTEZ.search(ham)
            if m and re.search(r"[A-Za-zÇĞİÖŞÜçğıöşü]{3,}", _PUAN.sub("", m.group(0))):
                uyarilar.append(
                    f"'{temiz}' basliginin puan parantezi fazladan metin iceriyor "
                    f"({m.group(0).strip()}); iki ayri kriter olabilir."
                )

    toplam = sum(k["agirlik"] for k in kriterler)

    # Alt basliklar: secilen gruptan BIR seviye asagisi. Kriter olarak
    # eklenmiyorlar (cift sayim olur) ama yoneticiye gosteriliyor.
    alt = []
    if secilen is not None:
        s, i = secilen
        alt_anahtarlar = [
            a
            for a in gruplar
            if (a[0] == s and a[1] is not None and (i is None or a[1] > i))
            or (a[0] == s + 1)
        ]
        for a in alt_anahtarlar:
            for ham in gruplar[a]:
                temiz = _basligi_temizle(ham)
                if temiz:
                    alt.append({"baslik": temiz, "agirlik": _agirlik(ham)})
        alt_toplam = sum(x["agirlik"] or 0 for x in alt)
        if alt and alt_toplam and toplam == 100:
            uyarilar.append(
                f"{len(alt)} alt baslik bulundu (toplam {alt_toplam} puan). Bunlar ust "
                "basliklarin puan DAGILIMI kabul edilip kriter listesine "
                "EKLENMEDI; ayri kriter olmalarini istiyorsaniz elle ekleyin."
            )

    if not kriterler:
        uyarilar.append(
            "Basliklarda '(N Puan)' bicimli agirlik bulunamadi; kriter "
            "agirliklarini elle girmeniz gerekiyor."
        )
        guven = "orta"
    elif toplam != 100:
        uyarilar.append(
            f"Cikarilan agirliklarin toplami {toplam} (100 olmali). Sablonda "
            "puanlar farkli yazilmis ya da bazi basliklar kacirilmis olabilir - "
            "listeyi kaydetmeden once gozden gecirin."
        )
        guven = "orta"
    else:
        guven = "yuksek"

    if bicim == "pdf":
        guven = "dusuk"
        uyarilar.insert(
            0,
            "PDF'te Word baslik bilgisi yok; basliklar yazi tipi boyutuna gore "
            "TAHMIN edildi. Mumkunse .docx sablonu yukleyin.",
        )

    # analyzer.py basliklari altdizge olarak ariyor: bir baslik digerinin
    # icinde geciyorsa bolumleme sasar.
    for a in zorunlu:
        for b in zorunlu:
            if a is not b and _tf_kucult(a) in _tf_kucult(b):
                uyarilar.append(
                    f"'{a}' basligi '{b}' basliginin icinde geciyor; bolum ayirma "
                    "yanlis calisabilir, birini yeniden adlandirin."
                )

    ek = _govde_kurallari(govde, uyarilar)

    return {
        "bicim": bicim,
        "guven": guven,
        "zorunlu_basliklar": zorunlu,
        "kriterler": kriterler,
        "agirlik_toplami": toplam,
        "alt_basliklar": alt,
        "uyarilar": uyarilar,
        "_secilen_grup": secilen,
        **ek,
    }


def _govde_kurallari(govde: str, uyarilar: list) -> dict:
    """Sablonun GOVDE METNINDEN cikarilabilen ek alanlar.

    Iki gercek sablon dosyasinda da bu bilgiler duz cumle olarak yaziyor;
    basliklardan degil metinden geliyorlar, bu yuzden guven seviyesi ayri
    dusunulmeli - hepsi yoneticiye ONERI olarak sunuluyor.
    """
    sonuc = {
        "min_sayfa": None,
        "max_sayfa": None,
        "rapor_turu_adi": None,
        "seviye": None,
    }
    if not govde:
        return sonuc

    aralik = _ARALIK.search(govde)
    if aralik:
        sonuc["min_sayfa"] = int(aralik.group(1))
        sonuc["max_sayfa"] = int(aralik.group(2))
    else:
        az = _EN_AZ.search(govde)
        fazla = _EN_FAZLA.search(govde)
        if az:
            sonuc["min_sayfa"] = int(az.group(1))
        if fazla:
            sonuc["max_sayfa"] = int(fazla.group(1))

    # "10 sayfayi gecmemelidir" ayri bir sinir; ustteki araliktan FARKLIYSA
    # yoneticiye soyluyoruz - OTR sablonunda ikisi gercekten cakisiyor
    # ("Rapor 10 sayfayi gecmemelidir" ama "toplam en az 6 en fazla 15"),
    # cunku biri kapak/icindekiler HARIC sayiyor. Analyzer TOPLAM sayfayi
    # saydigi icin genis olani dogru olan; yine de karar yoneticinin.
    gec = _GECMEMELI.search(govde)
    if gec:
        deger = int(gec.group(1))
        if sonuc["max_sayfa"] is None:
            sonuc["max_sayfa"] = deger
        elif deger != sonuc["max_sayfa"]:
            uyarilar.append(
                f"Sablonda iki farkli sayfa siniri geciyor: '{deger} sayfayi "
                f"gecmemelidir' ve 'en fazla {sonuc['max_sayfa']} sayfa'. "
                "Genellikle biri kapak/icindekiler HARIC sayiyor; analiz "
                "TOPLAM sayfayi saydigi icin genis olani onerildi."
            )

    tur = _RAPOR_TURU.findall(govde[:3000])
    if tur:
        # En kisa eslesme genelde en temizi: "ON TASARIM RAPORU" gibi.
        ad = min(tur, key=len).strip()
        # "YARISMASI ON TASARIM RAPORU" -> "ON TASARIM RAPORU"
        ad = re.sub(r"^.*?YARIŞMASI\s+", "", ad).strip()
        sonuc["rapor_turu_adi"] = _tr_baslik_yap(ad)

    sev = _SEVIYE.search(govde)
    if sev:
        sonuc["seviye"] = sev.group(1).strip(" .:-")

    return sonuc
