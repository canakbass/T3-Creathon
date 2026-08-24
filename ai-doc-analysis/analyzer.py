import json
import sys
from pathlib import Path

import pdfplumber
from langdetect import detect, DetectorFactory

# langdetect kisa metinlerde her calistirmada farkli sonuc verebiliyor
# (rastgele bir tohum kullaniyor). Ayni PDF her seferinde ayni sonucu
# vermeli, bu yuzden tohumu sabitliyoruz.
DetectorFactory.seed = 0

DEFAULT_RULES_PATH = Path(__file__).resolve().parent.parent / "docs" / "mvp-rules.json"


def load_rules(rules_path: Path = DEFAULT_RULES_PATH) -> dict:
    with open(rules_path, "r", encoding="utf-8") as f:
        return json.load(f)


def extract_text(pdf_path: str) -> str:
    """PDF'ten sayfa sayfa duz metin cikarir. Taranmis/goruntu PDF'lerde bos donebilir."""
    text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
    return text


def count_pages(pdf_path: str) -> int:
    with pdfplumber.open(pdf_path) as pdf:
        return len(pdf.pages)


def detect_language(text: str) -> str:
    """Dil tespiti yapar. Kisa/bozuk metinde 'unknown' doner.

    Ilk 1000 karakteri DEGIL, kapak sayfasi + Icindekiler'i atlayip
    metnin biraz icinden bir pencere kullaniyoruz. Gercek 34 KTR raporunda
    test edildi: ilk-1000-karakter yontemi 12/34 raporu yanlislikla
    Almanca/Ingilizce sandi (kapak+Icindekiler'de gecen kisa
    kisaltmalar/Ingilizce teknik terimler langdetect'i yaniltiyor).
    Bu pencereyle 33/34 dogru tespit ediliyor.
    """
    baslangic = min(2500, len(text) // 3)
    sample = text[baslangic:baslangic + 1500].strip()
    if not sample:
        sample = text[:1000].strip()
    if not sample:
        return "unknown"
    try:
        return detect(sample)
    except Exception:
        return "unknown"


def _turkish_casefold(s: str) -> str:
    """Python'un varsayilan .lower() metodu Turkce I/i, I/i harflerini yanlis
    esler (ornegin 'ILAC'.lower() -> 'ilac' degil 'ilac' olur ama 'Istanbul'
    gibi durumlarda 'i' ile 'i' karisir). Once Turkce harfleri ASCII'ye elle
    esitleyip sonra kucuk harfe ceviriyoruz; bu sayede hem basliktaki hem
    metindeki karsilastirma tutarli oluyor.
    """
    return s.replace("İ", "i").replace("I", "ı").lower()


def _find_heading(normalized_text: str, baslik: str, esanlamli: dict):
    """Bir basligin (ya da bilinen esanlamlilarindan birinin) metindeki SON
    gectigi yeri bulur. Once kanonik baslik, sonra esanlamlilar denenir.
    Bulunursa (konum, eslesen_metnin_uzunlugu) doner, yoksa None."""
    for varyant in [baslik] + esanlamli.get(baslik, []):
        idx = normalized_text.rfind(_turkish_casefold(varyant))
        if idx != -1:
            return idx, len(varyant)
    return None


def check_template(text: str, rules: dict) -> dict:
    """Zorunlu basliklarin (ya da bilinen esanlamlilarinin) metinde olup
    olmadigini kontrol eder (Turkce karakter farkliliklarina duyarli,
    buyuk/kucuk harf farki gozetmez).

    Esanlamli varyantlar `rules["esanlamli_basliklar"]` icinde tutulur -
    gercek 34 raporda gorduk ki hakemler "Kaynakca" yerine "Referanslar"/
    "Kaynaklar" yazan raporlari da kabul etmis; birebir kelime eslesmesi
    boyle raporlari haksiz yere "eksik" sayardi.
    """
    normalized_text = _turkish_casefold(text)
    esanlamli = rules.get("esanlamli_basliklar", {})
    eksik = [
        baslik
        for baslik in rules["zorunlu_basliklar"]
        if _find_heading(normalized_text, baslik, esanlamli) is None
    ]
    return {
        "sablon_uygun": len(eksik) == 0,
        "eksik_basliklar": eksik,
    }


def find_sections(text: str, rules: dict) -> dict:
    """Rapor metnini zorunlu basliklara gore bolumlere ayirir.

    Doner: {kanonik_baslik: bolum_metni}. Metinde hic bulunamayan basliklar
    sozlukte yer almaz - onlar zaten check_template'te "eksik" olarak
    raporlaniyor. Sozluk, basliklarin metindeki gercek sirasina gore dolu.

    Basligin ilk gectigi yeri degil SON gectigi yeri kullaniyoruz: gercek
    raporlarda 2. sayfa genelde "Icindekiler" oluyor ve tum basliklar orada
    bir kez daha (sayfa numarasiyla) geciyor. Ilk esleseni kullansaydik
    icindekiler satirini "bolum icerigi" sanip yanlis olculer.

    Bu fonksiyon hem check_content (bolum uzunlugu kontrolu) hem de
    ai-scoring modulu (kriter bazli puanlama) tarafindan kullaniliyor -
    bolumleme mantigi tek yerde dursun diye ayri fonksiyona alindi.
    """
    normalized_text = _turkish_casefold(text)
    esanlamli = rules.get("esanlamli_basliklar", {})

    positions = []
    for baslik in rules["zorunlu_basliklar"]:
        bulunan = _find_heading(normalized_text, baslik, esanlamli)
        if bulunan is not None:
            idx, eslesen_uzunluk = bulunan
            positions.append((idx, eslesen_uzunluk, baslik))
    positions.sort()

    bolumler = {}
    for i, (idx, eslesen_uzunluk, baslik) in enumerate(positions):
        bolum_baslangic = idx + eslesen_uzunluk
        bolum_bitis = positions[i + 1][0] if i + 1 < len(positions) else len(text)
        bolumler[baslik] = text[bolum_baslangic:bolum_bitis]
    return bolumler


def check_content(text: str, rules: dict) -> list:
    """Metinde BULUNAN basliklarin (ya da esanlamlilarinin) altinda yeterli
    icerik olup olmadigini kontrol eder (eksik basliklar zaten
    check_template'te raporlaniyor, burada onlari tekrar saymiyoruz).
    """
    varsayilan_min = rules.get("min_bolum_karakter", 30)
    ozel_min = rules.get("min_bolum_karakter_override", {})

    return [
        baslik
        for baslik, bolum_metni in find_sections(text, rules).items()
        if len(bolum_metni) < ozel_min.get(baslik, varsayilan_min)
    ]


def analyze_document(pdf_path: str, rules: dict) -> dict:
    """Ana giris noktasi - backend sadece bu fonksiyonu cagirir."""
    try:
        text = extract_text(pdf_path)
        if not text.strip():
            return {"hata": "PDF'ten metin cikarilamadi (taranmis/goruntu PDF olabilir)"}

        dil = detect_language(text)
        dil_uygun = dil in rules.get("kabul_edilen_diller", [])

        sablon = check_template(text, rules)
        icerik_yetersiz_basliklar = check_content(text, rules)

        sayfa_sayisi = count_pages(pdf_path)
        sayfa_uygun = rules.get("min_sayfa", 0) <= sayfa_sayisi <= rules.get("max_sayfa", 10**9)

        return {
            "dil": dil,
            "dil_uygun": dil_uygun,
            "sayfa_sayisi": sayfa_sayisi,
            "sayfa_uygun": sayfa_uygun,
            "sablon_uygun": sablon["sablon_uygun"],
            "eksik_basliklar": sablon["eksik_basliklar"],
            "icerik_yetersiz_basliklar": icerik_yetersiz_basliklar,
            "hatalar": [],
        }
    except Exception as e:
        return {"hata": str(e)}


def analyze_document_for_ui(pdf_path: str, rules: dict = None) -> dict:
    """analyze_document()'in yapilandirilmis (bool/liste) ciktisini,
    backend'in ve hakem panelinin bekledigi
    {"languageTemplate": {score, summary, findings}, "contentHeading": {...}}
    formatina cevirir.

    NEDEN BU FONKSIYON VAR: backend/frontend ekibi (Mustafa/Mahmut) benimle
    senkron olmadan, 0-100 puanli + insan-okur ozet/bulgu seklinde bir
    sozlesme uzerine tum sistemi (veritabani semasi, API, hakem paneli)
    insa etmis (bkz. proje geçmişi). Puan bantlari onlarin
    src/lib/ai-analysis.ts dosyasindaki esiklerle hizalandi:
    >=85 yuksek guven, 65-84 gozden gecirilmeli, <65 kritik.

    Bu fonksiyon backend'deki mock analyze_document(file_path)'in yerine
    gecebilir - tek argumanla da cagirilabilir (rules verilmezse
    docs/mvp-rules.json okunur).
    """
    if rules is None:
        rules = load_rules()

    sonuc = analyze_document(pdf_path, rules)

    if "hata" in sonuc:
        hata_check = {"score": 0, "summary": sonuc["hata"], "findings": [sonuc["hata"]]}
        return {"languageTemplate": dict(hata_check), "contentHeading": dict(hata_check)}

    # languageTemplate: dil uygunlugu + sayfa sayisi + baslik varligi
    lt_skor = 100
    lt_bulgular = []
    if not sonuc["dil_uygun"]:
        lt_skor -= 40
        lt_bulgular.append(f"Rapor dili '{sonuc['dil']}' olarak tespit edildi, kabul edilen dil degil.")
    if not sonuc["sayfa_uygun"]:
        lt_skor -= 20
        lt_bulgular.append(f"Sayfa sayisi ({sonuc['sayfa_sayisi']}) beklenen araliğin disinda.")
    if sonuc["eksik_basliklar"]:
        lt_skor -= min(20 * len(sonuc["eksik_basliklar"]), 60)
        lt_bulgular.append("Eksik basliklar: " + ", ".join(sonuc["eksik_basliklar"]) + ".")
    lt_skor = max(0, lt_skor)
    lt_ozet = (
        "Rapor dili ve sablon yapisi uygun."
        if not lt_bulgular
        else "Dil/sablon kontrolunde sorun tespit edildi."
    )

    # contentHeading: bulunan basliklarin altindaki icerigin yeterliligi
    ch_skor = 100
    ch_bulgular = []
    if sonuc["icerik_yetersiz_basliklar"]:
        ch_skor -= min(20 * len(sonuc["icerik_yetersiz_basliklar"]), 60)
        ch_bulgular.append(
            "Icerigi yetersiz basliklar: " + ", ".join(sonuc["icerik_yetersiz_basliklar"]) + "."
        )
    ch_skor = max(0, ch_skor)
    ch_ozet = (
        "Tum basliklarin altinda yeterli icerik var."
        if not ch_bulgular
        else "Bazi basliklarin altinda yeterli icerik bulunamadi."
    )

    return {
        "languageTemplate": {
            "score": lt_skor,
            "summary": lt_ozet,
            "findings": lt_bulgular or ["Tum kontroller basarili."],
        },
        "contentHeading": {
            "score": ch_skor,
            "summary": ch_ozet,
            "findings": ch_bulgular or ["Tum basliklarin icerigi yeterli."],
        },
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Kullanim: python analyzer.py <pdf_dosya_yolu>")
        sys.exit(1)

    rules = load_rules()
    result = analyze_document(sys.argv[1], rules)
    print(json.dumps(result, ensure_ascii=False, indent=2))
