"""Ortak metin araclari: PDF'ten bolumleme, tokenizasyon, n-gram uretimi.

Bu modul ai-scoring'in uc alt modulunun (kategori / benzerlik / kriter)
ortak kullandigi dusuk seviyeli isleri toplar. PDF metin cikarma ve
bolumleme icin ai-doc-analysis/analyzer.py'deki (Hasan'in) fonksiyonlar
tekrar kullaniliyor - ayni isi iki yerde yapmamak icin.
"""

import os
import re
import sys
from pathlib import Path

_AI_DOC_ANALYSIS_PATH = Path(__file__).resolve().parent.parent / "ai-doc-analysis"
if str(_AI_DOC_ANALYSIS_PATH) not in sys.path:
    sys.path.insert(0, str(_AI_DOC_ANALYSIS_PATH))

from analyzer import (  # noqa: E402
    extract_text,
    find_sections,
    load_rules,
    _turkish_casefold as turkish_casefold,
)

__all__ = [
    "extract_text",
    "find_sections",
    "load_rules",
    "turkish_casefold",
    "fold_diacritics",
    "normalize_for_matching",
    "read_report",
    "tokenize",
    "word_ngrams",
    "count_matches",
    "TURKCE_ETKISIZ_KELIMELER",
    "SAYI_DESENI",
    "KAYNAK_DESENLERI",
]


# Turkce harflerin ASCII karsiliklari.
_DIAKRITIK_TABLOSU = str.maketrans(
    {
        "ç": "c", "ğ": "g", "ı": "i", "î": "i", "ö": "o", "ş": "s",
        "ü": "u", "û": "u", "â": "a", "Ç": "c", "Ğ": "g", "İ": "i",
        "I": "i", "Î": "i", "Ö": "o", "Ş": "s", "Ü": "u", "Û": "u",
        "Â": "a",
    }
)


def fold_diacritics(s):
    """Turkce harfleri ASCII'ye indirger: 'özgün' -> 'ozgun'."""
    return s.translate(_DIAKRITIK_TABLOSU)


def normalize_for_matching(s):
    """Anahtar kelime eslesmesi icin metni tam normalize eder: kucuk harf
    + diakritik katlama.

    NEDEN AYRI BIR FONKSIYON (analyzer.turkish_casefold yetmiyor):
    turkish_casefold sadece I/i sorununu cozer, diakritikleri KORUR. Baslik
    aramada bu dogru davranis - mvp-rules.json'daki basliklar da ("Özgünlük",
    "Kaynakça") diakritikli yazili, iki taraf birebir esleşiyor.

    Ama anahtar kelime listeleri kod/config icinde ASCII yazilir
    ('ozgun', 'literatur', 'makine ogrenmesi') cunku diakritikli yazim
    editor/kodlama hatalarina acik. Iki taraf ayni sekilde katlanmazsa
    eslesme SESSIZCE sifir doner - bu hata gerceklesti: 34 gercek raporun
    hicbirinde 'ozgunluk_dili' sinyali puan almiyordu, cunku listedeki
    'ozgun' metindeki 'özgün' ile hic eslesmiyordu. Hata patlamiyor,
    sadece sinyal olu doguyor; bu yuzden calibrate.py ile olcup fark ettik.
    """
    return fold_diacritics(turkish_casefold(s))


# Turkce etkisiz kelimeler (stop words). Benzerlik ve kategori
# karsilastirmasinda bunlar ayirt edici bilgi tasimadigi icin atiliyor.
# TF-IDF zaten her belgede gecen kelimeleri kendiliginden zayiflatir, ama
# 34 raporluk kucuk bir koleksiyonda IDF gurultulu kaliyor - elle bir liste
# vermek sonuclari belirgin sekilde temizliyor.
TURKCE_ETKISIZ_KELIMELER = frozenset(
    """
    acaba altmis alti ama ancak arada artik asla aslinda ayrica az bana bazen
    bazi bazilari belki ben benden beni benim beri beş bile bin bir biraz
    birazi birbiri birca birkac birkaci birsey biz bizden bize bizi bizim bu
    buna bunda bundan bunlar bunlari bunlarin bunu bunun burada butun cok
    cunku da daha dahi de defa degil diger diye dokuz dolayi dort edecek eden
    ederek edilecek ediliyor edilmesi ediyor elli en fakat falan felan gibi
    hala hangi hani hatta hem henuz hep hepsi her herhangi herkes herkesi
    hicbir icin ikı iki ile ilgili ise iste itibaren itibariyle kadar karsin
    katrilyon kendi kendilerine kendini kendisi kendisine kendisini kez ki
    kim kimden kime kimi kimse kirk milyar milyon mu mi nasil ne neden nedenle
    nerde nerede nereye niye nicin o olan olarak oldu olduklarini oldugu
    oldugunu olmadi olmadigi olmak olması olmayan olmaz olsa olsun olup olur
    olursa oluyor on ona ondan onlar onlardan onlari onlarin onu onun otuz oysa
    oyle sadece sanki sekiz seksen sen senden seni senin sey seyden seyi seyler
    siz sizden size sizi sizin sonra su suna sunda sundan sunlari sunlarin sunu
    tarafindan trilyon tum uc uzere var vardi ve veya ya yani yapacak yapilan
    yapilmasi yapiyor yapmak yapti yaptigi yaptigini yaptiklari yedi yerine
    yetmis yine yirmi yoksa yuz zaten
    """.split()
)

# Bir bolumde sayisal kanit olup olmadigini olcmek icin: yuzde, ondalik,
# tam sayi, "0.85", "%92,4", "12 ms" gibi ifadeleri yakalar.
#
# {0,8} SINIRI NEDEN VAR (SonarQube: "super-linear performance due to
# backtracking"): onceki hali `(?:[.,]\d+)*` seklinde sinirsizdi. Ic ice
# niceleyici (`\d+` icinde oldugu bir yildizli grup) statik analizde ReDoS
# supheli isaretleniyor. Olctuk: gercek bir patlama YOK - 800.000 karakterlik
# saldirgan girdi ("1,1,1,...") eski desende 36 ms suruyordu; kiyas icin
# bilinen gercek bir ReDoS deseni olan `(a+)+$` sadece 26 karakterde 4 saniye
# aliyor. Yani risk somurulebilir degildi. Yine de sinirlandirdik, cunku:
#   1. girdi kullanicinin yukledigi PDF'ten geliyor, yani guvenilmez
#   2. sinirli hali daha da hizli (ayni saldirgan girdide 19.8 -> 13.5 ms)
#   3. kalite kapisini temiz tutuyor
# 8 ayirici, "1.2.3.4.5.6.7.8.9" gibi bir sayiyi bile tek parca yakalar.
#
# KRITIK: bu degisiklik ANLAMI DEGISTIRMEDI. 34 gercek raporun tam metninde
# ve 203 bolumunde eslesme listeleri birebir ayni cikti (7874 eslesme).
# Bu sart, cunku docs/scoring-rules.json'daki beklenen_kanit_yogunlugu
# esikleri eski desenle olculdu - eslesme sayisi degisse tum esikler
# gecersiz olurdu.
SAYI_DESENI = re.compile(r"%?\s?\d+(?:[.,]\d+){0,8}\s?%?")

# Kaynakca bolumunde gercek atif olup olmadigini olcen desenler.
KAYNAK_DESENLERI = re.compile(
    r"""
    \[\s*\d+\s*\]                     # [1], [12]
  | \(\s*[A-ZÇĞİÖŞÜ][^()]{2,40}?,\s*\d{4}\s*\)   # (Yazar, 2020)
  | \bdoi\s*:?\s*10\.\d{4,}           # doi:10.1234/...
  | https?://\S+                      # duz URL
  | \barxiv\b                         # arXiv atiflari
    """,
    re.VERBOSE | re.IGNORECASE,
)

# Diakritikler katlandiktan sonra calisiyor, o yuzden ASCII yeterli.
_KELIME_DESENI = re.compile(r"[0-9a-z]+")


_METIN_ONBELLEGI = {}
_ONBELLEK_SINIRI = 256


def _extract_text_cached(pdf_path):
    """extract_text'i dosya kimligine gore onbellekler.

    NEDEN GEREKLI: benzerlik analizi, her yeni rapor icin daha once
    yuklenmis TUM raporlari yeniden okumak zorunda. Onbellek olmadan N
    raporluk bir veri tabaninda her yukleme N adet PDF ayristirmasi
    demek - 34 raporda tek bir benzerlik cagrisi ~10 saniye suruyordu ve
    maliyet rapor sayisiyla dogrusal buyuyor. Ayristirma PDF basina en
    pahali islem oldugu icin en buyuk kazanc burada.

    Anahtar (yol, degistirilme_zamani, boyut): dosya diskte degisirse
    onbellek kendiliginden gecersiz olur, yani bayat metin donmez.
    """
    yol = str(pdf_path)
    try:
        st = os.stat(yol)
        anahtar = (yol, st.st_mtime_ns, st.st_size)
    except OSError:
        # Dosyaya erisilemiyor - onbelleklemeye calismadan asil hatayi
        # extract_text'in kendisi bildirsin.
        return extract_text(yol)

    if anahtar in _METIN_ONBELLEGI:
        return _METIN_ONBELLEGI[anahtar]

    metin = extract_text(yol)
    if len(_METIN_ONBELLEGI) >= _ONBELLEK_SINIRI:
        # Sinirsiz buyumesin: uzun yasayan bir backend surecinde bellek
        # sizintisi olurdu. En eski girdiyi atmak yeterli - erisim deseni
        # "ayni korpusu tekrar tekrar oku" oldugu icin basit FIFO iyi calisiyor.
        _METIN_ONBELLEGI.pop(next(iter(_METIN_ONBELLEGI)))
    _METIN_ONBELLEGI[anahtar] = metin
    return metin


def read_report(pdf_path, rules=None):
    """Bir PDF raporu okur; tam metnini ve bolumlerini birlikte doner.

    Doner: {"metin": str, "bolumler": {baslik: metin}} ya da okunamadiysa
    {"hata": "..."}. Cagiran tarafin her seferinde ayni try/except'i
    yazmasini onlemek icin hatayi istisna olarak firlatmiyoruz - Hasan'in
    analyze_document'i da ayni sozlesmeyi kullaniyor.
    """
    if rules is None:
        rules = load_rules()
    try:
        metin = _extract_text_cached(pdf_path)
    except Exception as e:
        return {"hata": f"PDF okunamadi: {e}"}

    if not metin.strip():
        return {"hata": "PDF'ten metin cikarilamadi (taranmis/goruntu PDF olabilir)"}

    return {"metin": metin, "bolumler": find_sections(metin, rules)}


def tokenize(text, etkisizleri_at=True):
    """Metni normalize edilmis kelime listesine cevirir.

    Diakritikleri de katliyor (normalize_for_matching): ayni kelimenin
    'özgün'/'ozgun' gibi iki yazimi tek tokene inmeli, yoksa birebir
    ortusme olcumu PDF'in font kodlamasina gore degisir. Etkisiz kelime
    listesi de ASCII yazili oldugu icin bu sart.
    """
    kelimeler = _KELIME_DESENI.findall(normalize_for_matching(text))
    if etkisizleri_at:
        return [k for k in kelimeler if k not in TURKCE_ETKISIZ_KELIMELER and len(k) > 1]
    return kelimeler


def word_ngrams(tokens, n):
    """Kelime dizisinden n-gram kumesi uretir (birebir kopya tespiti icin).

    Kume donuyor, liste degil: iki rapor arasindaki ORTAK n-gram oranini
    olcecegiz, ayni n-gram'in bir belgede kac kez tekrarlandigi onemli degil.
    """
    if len(tokens) < n:
        return set()
    return {" ".join(tokens[i : i + n]) for i in range(len(tokens) - n + 1)}


def count_matches(pattern, text):
    """Bir regex deseninin metinde kac kez gectigini sayar."""
    return len(pattern.findall(text))
