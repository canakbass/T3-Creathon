"""Benzerlik / intihal analizi (MVP madde 4).

TASARIM KARARI - NEDEN KOSINUS BENZERLIGI PUANI BELIRLEMIYOR:

Ilk akla gelen yol, iki raporun TF-IDF vektorleri arasindaki kosinus
benzerligini "intihal orani" olarak vermek. Bunu 34 gercek finalist raporu
uzerinde olctuk (bkz. ai-scoring/calibrate.py):

  birbirinden BAGIMSIZ 34 gercek rapor, TF-IDF kosinus:  %12.5 - %44.9  (medyan %20.5)
  ayni 34 rapor, 8-kelimelik birebir ortusme:            %0.0  - %8.6   (medyan %0.6)

Sebep: hepsi ayni sablonu, ayni zorunlu baslikari ve ayni alan
terminolojisini kullaniyor. Yani kosinus benzerligi burada "ayni konuda
yazilmis" demek, "kopyalanmis" demek degil. Frontend'in intihal bandi
>35 'Yuksek risk' oldugu icin (frontend/src/lib/ai-analysis.ts,
NEGATIVE_CAUTION_CEILING=35), kosinus kullanilsa gercek ve masum
raporlarin bir kismi haksiz yere intihalle suclanirdi. Bir hakem karar
destek sisteminde bu, sistemi kullanilamaz kilan turde bir hata.

Bu yuzden:
  * PUANI belirleyen sinyal  -> birebir kelime ortusmesi (8-gram kapsama)
  * hakeme BAGLAM olarak gosterilen -> konusal (TF-IDF kosinus) benzerlik

Birebir ortusme, gercek intihal tespitinin de kullandigi sinyaldir: kopya
ceken rapor uzun cumleleri kelimesi kelimesine paylasir, ayni konuda
bagimsiz yazan rapor paylasmaz.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from text_utils import load_rules, read_report, tokenize, word_ngrams  # noqa: E402

DEFAULT_SCORING_RULES_PATH = (
    Path(__file__).resolve().parent.parent / "docs" / "scoring-rules.json"
)


def load_scoring_rules(path=DEFAULT_SCORING_RULES_PATH):
    import json

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _verbatim_overlap(ngrams_a, ngrams_b):
    """Iki n-gram kumesi arasindaki KAPSAMA oranini yuzde olarak doner.

    Jaccard yerine kapsama (containment) kullaniyoruz: kesisimi iki kumenin
    BIRLESIMINE degil, KUCUK olanina boluyoruz. Neden: 3 sayfalik bir rapor
    30 sayfalik bir rapordan tamamen kopyalanmis olabilir. Jaccard bu durumda
    buyuk belgenin boyutu yuzunden dusuk cikar ve intihali kacirir; kapsama
    "kucuk belgenin %100'u buyugunde var" diyerek dogru yakalar.
    """
    if not ngrams_a or not ngrams_b:
        return 0.0
    kesisim = len(ngrams_a & ngrams_b)
    return 100.0 * kesisim / min(len(ngrams_a), len(ngrams_b))


def _topical_similarity(hedef_tokenlar, diger_tokenlar_listesi):
    """TF-IDF kosinus benzerligi (yalnizca BAGLAM icin - puani belirlemiyor).

    scikit-learn yoksa None doner: benzerlik puani birebir ortusmeden
    geldigi icin bu sinyalin kaybi sistemi calismaz hale getirmez, sadece
    hakeme gosterilen ek baglami eksiltir.
    """
    if not diger_tokenlar_listesi:
        return None
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
    except ImportError:
        return None

    korpus = [" ".join(hedef_tokenlar)] + [" ".join(t) for t in diger_tokenlar_listesi]
    if any(not metin.strip() for metin in korpus):
        return None
    try:
        X = TfidfVectorizer(sublinear_tf=True).fit_transform(korpus)
    except ValueError:
        # korpusta anlamli kelime kalmadi (cok kisa/bozuk metinler)
        return None
    return [100.0 * s for s in cosine_similarity(X[0:1], X[1:])[0]]


def analyze_similarity(pdf_path, existing_paths, rules=None, scoring_rules=None):
    """Bir raporu daha once yuklenmis raporlarla karsilastirir.

    Doner:
      {
        "benzerlik_puani": int,          # 0-100, DUSUK olmasi iyi
        "en_benzer_raporlar": [{"rapor_id", "benzerlik_yuzdesi", "konusal_benzerlik"}],
        "karsilastirilan_rapor_sayisi": int,
        "hatalar": [str],
      }
    ya da hedef rapor okunamadiysa {"hata": "..."}.
    """
    if rules is None:
        rules = load_rules()
    if scoring_rules is None:
        scoring_rules = load_scoring_rules()

    benzerlik_kurallari = scoring_rules["benzerlik"]
    n = benzerlik_kurallari["ngram_kelime"]
    kac_eslesme = benzerlik_kurallari.get("raporlanacak_eslesme_sayisi", 3)

    hedef = read_report(pdf_path, rules)
    if "hata" in hedef:
        return {"hata": hedef["hata"]}

    hedef_tokenlar = tokenize(hedef["metin"])
    hedef_ngramlar = word_ngrams(hedef_tokenlar, n)

    hatalar = []
    digerleri = []  # (rapor_id, tokenlar, ngramlar)
    for yol in existing_paths:
        sonuc = read_report(yol, rules)
        if "hata" in sonuc:
            hatalar.append(f"{Path(yol).name}: {sonuc['hata']}")
            continue
        tokenlar = tokenize(sonuc["metin"])
        digerleri.append((Path(yol).name, tokenlar, word_ngrams(tokenlar, n)))

    if not digerleri:
        return {
            "benzerlik_puani": 0,
            "en_benzer_raporlar": [],
            "karsilastirilan_rapor_sayisi": 0,
            "hatalar": hatalar,
        }

    konusal = _topical_similarity(hedef_tokenlar, [t for _, t, _ in digerleri])

    eslesmeler = []
    for i, (rapor_id, _, ngramlar) in enumerate(digerleri):
        eslesmeler.append(
            {
                "rapor_id": rapor_id,
                "benzerlik_yuzdesi": round(_verbatim_overlap(hedef_ngramlar, ngramlar), 2),
                "konusal_benzerlik": round(konusal[i], 2) if konusal else None,
            }
        )
    eslesmeler.sort(key=lambda e: e["benzerlik_yuzdesi"], reverse=True)

    return {
        "benzerlik_puani": int(round(eslesmeler[0]["benzerlik_yuzdesi"])),
        "en_benzer_raporlar": eslesmeler[:kac_eslesme],
        "karsilastirilan_rapor_sayisi": len(digerleri),
        "hatalar": hatalar,
    }


def check_similarity_for_ui(pdf_path, existing_paths, rules=None, scoring_rules=None):
    """analyze_similarity ciktisini hakem panelinin bekledigi
    {"score", "summary", "findings"} formatina cevirir.

    DIKKAT - bu kontrol 'negatif polarite': DUSUK puan IYI sonuc demek
    (frontend/src/lib/ai-analysis.ts, polarity: "negative"). Frontend
    bantlari: <=15 "Ozgun", 16-35 "Gozden gecirilmeli", >35 "Yuksek risk".
    Ozet metnini bu kelime dagarcigina uydurdum ki karttaki etiketle
    yan yana tutarsiz durmasin.
    """
    if scoring_rules is None:
        scoring_rules = load_scoring_rules()
    esikler = scoring_rules["benzerlik"]

    sonuc = analyze_similarity(pdf_path, existing_paths, rules, scoring_rules)
    if "hata" in sonuc:
        return {
            "score": 0,
            "summary": f"Benzerlik analizi yapılamadı: {sonuc['hata']}",
            "findings": [
                "Rapor metni okunamadığı için benzerlik karşılaştırması yapılamadı.",
                "Bu bir analiz hatasıdır, özgünlük kanıtı değildir — hakem raporu elle incelemeli.",
            ],
        }

    puan = sonuc["benzerlik_puani"]
    karsilastirilan = sonuc["karsilastirilan_rapor_sayisi"]

    if karsilastirilan == 0:
        return {
            "score": 0,
            "summary": "Karşılaştırılacak başka rapor yok — bu, sistemdeki ilk başvuru.",
            "findings": [
                "Veri tabanında karşılaştırılacak başka rapor bulunmadığı için örtüşme hesaplanamadı.",
                "Puan 0 olarak verildi; bu 'özgünlüğü kanıtlandı' anlamına GELMEZ, sadece "
                "karşılaştırma yapılamadı anlamına gelir.",
            ],
        }

    bulgular = []
    if puan > esikler["kritik_esigi"]:
        ozet = "Yüksek oranda birebir metin örtüşmesi tespit edildi."
    elif puan > esikler["dikkat_esigi"]:
        ozet = "Dikkate değer birebir metin örtüşmesi var, hakem gözden geçirmeli."
    else:
        ozet = "Önceki başvurularla anlamlı bir birebir örtüşme bulunamadı."

    bulgular.append(
        f"{karsilastirilan} önceki başvuruyla karşılaştırıldı; en yüksek birebir "
        f"örtüşme %{puan}."
    )

    for eslesme in sonuc["en_benzer_raporlar"]:
        if eslesme["benzerlik_yuzdesi"] <= 0.01:
            continue
        satir = f"{eslesme['rapor_id']}: %{eslesme['benzerlik_yuzdesi']} birebir örtüşme"
        if eslesme["konusal_benzerlik"] is not None:
            satir += f" (konusal benzerlik %{eslesme['konusal_benzerlik']})"
        bulgular.append(satir)

    # Hakemin puani dogru yorumlamasi icin referans noktasi. Bu sayi
    # olculdu, uydurulmadi - bkz. calibrate.py.
    bulgular.append(
        "Referans: birbirinden bağımsız 34 gerçek finalist raporunda ölçülen en yüksek "
        f"birebir örtüşme %{esikler['gercek_raporlarda_gorulen_en_yuksek']}. "
        f"%{esikler['dikkat_esigi']} üstü incelenmeli, %{esikler['kritik_esigi']} üstü "
        "yüksek risk."
    )

    if sonuc["hatalar"]:
        bulgular.append(
            f"{len(sonuc['hatalar'])} önceki rapor okunamadı, karşılaştırmaya dahil "
            "edilemedi: " + "; ".join(sonuc["hatalar"][:3])
        )

    return {"score": puan, "summary": ozet, "findings": bulgular}
