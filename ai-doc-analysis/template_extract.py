"""Resmi rapor şablonundan zorunlu başlıkları ve puan ağırlıklarını çıkarır.

NEDEN VAR: Yarışma Yöneticisi "Kriter ve Şablon Tanımı" ekranında zorunlu
başlıkları ve kriter ağırlıklarını TEK TEK elle giriyordu. Oysa TEKNOFEST'in
resmi şablon dosyaları bu bilgiyi zaten makine-okunur biçimde taşıyor:

    sablon_OTR_2026.docx (Word "Başlık 1" stilinde):
        TAKIM ŞEMASI
        PROJE MEVCUT DURUM DEĞERLENDİRMESİ (10 Puan)
        ALGORİTMALAR VE SİSTEM MİMARİSİ (30 PUAN)
        ...
        GENEL RAPOR DÜZENİ (5 PUAN)          -> ağırlıklar toplamı TAM 100

Yönetici resmi şablonu yüklüyor, form kendiliğinden doluyor.

DİKKAT — NAİF ÇIKARMA YANLIŞ SONUÇ VERİR: `sablon_OTR_2026.docx` içinde
"Veri Setleri (10 Puan)", "Algoritmalar (15 Puan)", "Akış Şeması (5 Puan)"
alt başlıkları da ANA başlıklarla AYNI Word stilini kullanıyor. Hepsini
toplarsanız 130 çıkar; oysa o üçü zaten ana başlığın 30 puanının içinde.
Bu yüzden aday gruplar arasından **ağırlıkları 100'e toplananı** seçiyoruz —
şablonun kendi iç tutarlılığı, hangi seviyenin "ana bölüm" olduğunu
söylüyor.

Girdi: .docx veya .pdf yolu. Çıktı her zaman aynı sözlük; hata durumunda da
çöküyor değil, `uyarilar` doluyor — yönetici neyin neden çıkarılamadığını
görmeli.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

# "(10 Puan)", "(30 PUAN)", "(ve RAPOR DÜZENİ 10 PUAN)" hepsini yakalar.
# Sondaki parantezli bölümde geçen SON sayıyı puan kabul ediyoruz: bazı
# başlıklarda parantez içinde açıklama da var ("(ve RAPOR DÜZENİ 10 PUAN)").
_PUAN_DESENI = re.compile(r"\(([^()]*?)(\d{1,3})\s*(?:puan|PUAN|Puan)[^()]*\)")

# Başındaki "1.", "2 -", "III." gibi numaralandırma.
_NUMARA_ONEKI = re.compile(r"^\s*(?:\d{1,2}|[IVXivx]{1,5})\s*[.)\-–]?\s*")

# İçindekiler satırlarının sonuna yapışan sayfa numarası: "TAKIM ŞEMASI5"
# Word'ün TOC alanı metni ile sayfa numarasını aynı paragrafta veriyor.
# İçindekiler satırlarının sonundaki sayfa numarası. Word'ün TOC alanı metni
# ile sayfa numarasını AYNI paragrafta veriyor: "TAKIM ŞEMASI5" ya da
# "PROJE MEVCUT DURUM DEĞERLENDİRMESİ (10 Puan)6". Puan eki çıkarıldıktan
# sonra araya boşluk girebildiği için boşluğa da izin veriyoruz.
_SAYFA_NUMARASI_SONU = re.compile(r"(?:\s*\.{2,})?\s*\d{1,3}\s*$")

# Başlık olamayacak kadar kısa/uzun olanları eliyoruz.
_MIN_BASLIK = 3
_MAX_BASLIK = 120

# Şablonun kendi iç başlıkları - bölüm değil, belge süsü.
_BASLIK_OLMAYANLAR = {
    "içindekiler",
    "icindekiler",
    "şekil listesi",
    "sekil listesi",
    "tablo listesi",
    "kısaltmalar",
    "kisaltmalar",
    "simgeler ve kısaltmalar",
    "özet",  # şablona göre bazen bölüm bazen ön sayfa - aşağıda not var
}


def _turkce_kucult(s: str) -> str:
    """Türkçe'ye doğru küçültme.

    NEDEN str.casefold() YETMİYOR: Python "İ".casefold() sonucunu
    "i" + birleşen nokta (U+0307) olarak veriyor, yani
    "ŞEKİL LİSTESİ".casefold() == "şeki̇l li̇stesi̇" — düz "şekil listesi"
    ile EŞLEŞMİYOR. Bu tuzak bu projede daha önce de bir hataya yol açtı
    (ai-scoring'de ASCII anahtar kelimeler Türkçe metinle hiç eşleşmiyor,
    tüm raporlar sessizce 0 puan alıyordu).
    """
    return s.replace("İ", "i").replace("I", "ı").casefold()


def _temizle(ham: str) -> str:
    """Başlık metnini numaralandırma, puan eki ve sayfa numarasından arındırır."""
    metin = _PUAN_DESENI.sub("", ham)
    # Sayfa numarasını YALNIZCA başlıkta harf varken kırpıyoruz; aksi halde
    # "2026" gibi tamamen sayısal bir satırı boşaltırdık.
    if re.search(r"[A-Za-zÇĞİÖŞÜçğıöşü]", metin):
        metin = _SAYFA_NUMARASI_SONU.sub("", metin)
    metin = _NUMARA_ONEKI.sub("", metin)
    return re.sub(r"\s+", " ", metin).strip(" .:-–\t")


def _puan(ham: str):
    m = _PUAN_DESENI.search(ham)
    return int(m.group(2)) if m else None


def _docx_paragraflari(yol: str):
    """(stil_adi, metin) çiftleri. python-docx'e bağımlı DEĞİL.

    Neden elle XML: backend/requirements.txt'e yeni bir bağımlılık eklemek
    Demo Day öncesi gereksiz risk. Word belgesi zaten bir zip; ihtiyacımız
    olan tek şey paragraf stili + metni ve ikisi de düz XML'de.
    """
    with zipfile.ZipFile(yol) as z:
        xml = z.read("word/document.xml").decode("utf-8", "replace")
    for p in re.findall(r"<w:p[ >].*?</w:p>", xml, re.S):
        stil = re.search(r'w:pStyle w:val="([^"]+)"', p)
        # <w:t> parçalarını birleştir: Word bir başlığı birden fazla run'a bölebilir.
        metin = "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", p)).strip()
        if metin:
            yield (stil.group(1) if stil else ""), metin


def _pdf_satirlari(yol: str):
    """PDF'te stil bilgisi yok; her satırı aday sayıp desene bakıyoruz."""
    import pdfplumber  # yerel içe aktarma: yalnızca PDF yolunda gerekli

    with pdfplumber.open(yol) as pdf:
        for sayfa in pdf.pages[:6]:  # başlık listesi hep ilk sayfalarda
            for satir in (sayfa.extract_text() or "").split("\n"):
                satir = satir.strip()
                if satir:
                    yield "", satir


def _aday_gruplar(ciftler):
    """Stil adına göre grupla; PDF'te tek grup olur.

    Ayrıca "numaralı satırlar" diye sanal bir grup üretiyoruz: PDF'te ve
    stil bilgisi kaybolmuş belgelerde ana bölümleri yakalayan tek sinyal
    baştaki numaralandırma oluyor.
    """
    gruplar: dict[str, list[str]] = {}
    for stil, metin in ciftler:
        gruplar.setdefault(stil or "(stilsiz)", []).append(metin)
        if _NUMARA_ONEKI.match(metin) and _puan(metin) is not None:
            gruplar.setdefault("(numarali+puanli)", []).append(metin)
    return gruplar


def _gruptan_bolumler(satirlar):
    """Bir gruptaki satırları (başlık, puan) listesine çevirir, tekrarları atar."""
    bolumler = []
    gorulen = set()
    for ham in satirlar:
        baslik = _temizle(ham)
        if not (_MIN_BASLIK <= len(baslik) <= _MAX_BASLIK):
            continue
        if _turkce_kucult(baslik) in _BASLIK_OLMAYANLAR:
            continue
        anahtar = _turkce_kucult(baslik)
        if anahtar in gorulen:
            continue
        gorulen.add(anahtar)
        bolumler.append({"baslik": baslik, "agirlik": _puan(ham)})
    return bolumler


def _alt_bolumleri_ele(bolumler):
    """Ana bölümün puanını paylaşan alt başlıkları listeden çıkarır.

    NEDEN GEREKLİ: `sablon_OTR_2026.docx` içinde "Veri Setleri (10 Puan)",
    "Algoritmalar (15 Puan)", "Akış Şeması (5 Puan)" alt başlıkları ANA
    başlıklarla AYNI Word stilini kullanıyor. Hepsi toplanınca 130 çıkıyor;
    oysa o üçü zaten bir üstteki "ALGORİTMALAR VE SİSTEM MİMARİSİ (30 PUAN)"
    başlığının içinde — 10+15+5 = 30.

    Kural: bir başlığı izleyen ARDIŞIK başlıkların puanları o başlığın
    puanına TAM olarak toplanıyorsa, onlar alt bölümdür ve elenir. Bu,
    şablonun kendi iç aritmetiğine dayanan bir kural; başlık metnine,
    numaralandırmaya veya girinti tahminine güvenmiyor.
    """
    sonuc = []
    i = 0
    while i < len(bolumler):
        mevcut = bolumler[i]
        sonuc.append(mevcut)
        hedef = mevcut["agirlik"]
        i += 1
        if not hedef:
            continue
        # Sonraki ardışık puanlı başlıkları toplayıp hedefi tutturmaya çalış.
        toplam = 0
        j = i
        while j < len(bolumler) and bolumler[j]["agirlik"]:
            toplam += bolumler[j]["agirlik"]
            j += 1
            if toplam == hedef and j > i + 1:
                # En az İKİ alt başlık aranıyor: tek bir eşit puanlı komşu,
                # alt bölüm değil sıradan bir kardeş bölüm olabilir.
                i = j
                break
            if toplam > hedef:
                break
    return sonuc


def sablondan_cikar(yol: str) -> dict:
    """Şablon dosyasından zorunlu başlıkları ve kriter ağırlıklarını çıkarır.

    Döner:
      {
        "basliklar":  ["Takım Şeması", ...],
        "kriterler":  [{"baslik": "...", "agirlik": 30}, ...],   # puanı olanlar
        "agirlik_toplami": 100 | None,
        "kaynak": "docx:Balk1" | "pdf" | ...,
        "uyarilar": [str],
      }
    Hiçbir şey çıkarılamazsa listeler boş döner ve `uyarilar` sebebi söyler -
    çağıran taraf yöneticiyi elle girmeye yönlendirmeli.
    """
    p = Path(yol)
    uzanti = p.suffix.lower()
    uyarilar: list[str] = []

    try:
        if uzanti == ".docx":
            ciftler = list(_docx_paragraflari(yol))
        elif uzanti == ".pdf":
            ciftler = list(_pdf_satirlari(yol))
        elif uzanti == ".doc":
            return _bos(
                "Eski .doc biçimi okunamıyor. Dosyayı Word'de açıp .docx olarak "
                "kaydedin ya da başlıkları elle girin."
            )
        else:
            return _bos(f"Desteklenmeyen dosya türü: {uzanti or 'bilinmiyor'}. .docx veya .pdf yükleyin.")
    except Exception as exc:  # bozuk/şifreli dosya
        return _bos(f"Şablon dosyası okunamadı: {exc}")

    if not ciftler:
        return _bos("Dosyadan hiç metin çıkarılamadı (taranmış/görüntü belge olabilir).")

    gruplar = _aday_gruplar(ciftler)

    # Her aday grubu değerlendir, EN İYİSİNİ seç.
    #
    # Seçim ölçütü ağırlıkların 100'e toplanması: alt başlıklar ana
    # başlıklarla aynı stili kullandığında toplam 100'ü AŞAR (ölçüldü:
    # sablon_OTR_2026.docx'te naif toplam 130). Şablonun kendi iç
    # tutarlılığı, hangi seviyenin "ana bölüm" olduğunu söylüyor.
    en_iyi = None
    for stil, satirlar in gruplar.items():
        bolumler = _alt_bolumleri_ele(_gruptan_bolumler(satirlar))
        puanlilar = [b for b in bolumler if b["agirlik"] is not None]
        if not bolumler:
            continue
        toplam = sum(b["agirlik"] for b in puanlilar) if puanlilar else None
        # Puan sayısı fazla ve toplamı 100'e yakın olan grup kazanır.
        yakinlik = abs(100 - toplam) if toplam is not None else 999
        skor = (yakinlik, -len(puanlilar), -len(bolumler))
        aday = {"stil": stil, "bolumler": bolumler, "puanlilar": puanlilar, "toplam": toplam, "skor": skor}
        if en_iyi is None or aday["skor"] < en_iyi["skor"]:
            en_iyi = aday

    if en_iyi is None:
        return _bos("Dosyada başlık gibi görünen bir satır bulunamadı.")

    toplam = en_iyi["toplam"]
    if toplam is None:
        uyarilar.append(
            "Şablonda puan ağırlığı bulunamadı; yalnızca zorunlu başlıklar "
            "çıkarıldı. Kriter ağırlıklarını elle girin."
        )
    elif toplam != 100:
        uyarilar.append(
            f"Çıkarılan ağırlıkların toplamı {toplam} (100 bekleniyordu). Şablonda "
            "alt başlıklar da puanlı olabilir; listeyi kaydetmeden önce gözden geçirin."
        )

    return {
        "basliklar": [b["baslik"] for b in en_iyi["bolumler"]],
        "kriterler": [
            {"baslik": b["baslik"], "agirlik": b["agirlik"]} for b in en_iyi["puanlilar"]
        ],
        "agirlik_toplami": toplam,
        "kaynak": f"{uzanti.lstrip('.')}:{en_iyi['stil']}",
        "uyarilar": uyarilar,
    }


def _bos(neden: str) -> dict:
    return {
        "basliklar": [],
        "kriterler": [],
        "agirlik_toplami": None,
        "kaynak": None,
        "uyarilar": [neden],
    }
