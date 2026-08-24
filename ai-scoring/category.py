"""Kategori uygunlugu analizi (MVP madde 3).

SORU: yarismaci raporunu X kategorisine gonderdi - rapor gercekten X'e mi ait?

TASARIM KARARI - NEDEN ANAHTAR KELIME LISTESI VAR:
Backend'in seed kategorileri INGILIZCE ("Robotics & Automation",
"AI & Machine Learning" - bkz. backend/main.py seed_db), raporlar ise
TURKCE. Kategori adi/aciklamasi ile rapor metni arasinda duz kelime
eslesmesi bu yuzden neredeyse sifir sonuc verir. Bu yuzden her kategori
icin Turkce anahtar kelime listesi docs/scoring-rules.json'da tutuluyor
(kod icine gomulmuyor - Yarisma Yoneticisi kategori ekledikce guncelleyecek).

Config'de tanimi OLMAYAN bir kategori icin karakter n-gram TF-IDF'e
dusuyoruz: Turkce/Ingilizce akraba kelimeler ("algoritma"/"algorithm",
"robotik"/"robotics") karakter duzeyinde kismen ortustugu icin bu zayif
ama sifirdan iyi bir sinyal. Boyle bir durumda bulgular bunu ACIKCA
soyler - hakem, puanin zayif bir yontemle uretildigini bilmeli.

ONEMLI: puani belirleyen sey, beyan edilen kategorinin MUTLAK eslesme
gucu; baska bir kategorinin daha iyi eslesmesi ise ceza olarak dusuyor.
Tersini yapmadik (yani "en iyi kategori bu mu" diye sormadik) cunku bir
IHA-yapay zeka raporu hem Robotik hem Yapay Zeka kategorisine mesru
sekilde uyar - ikinci bir makul kategorinin varligi kusur degildir.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from text_utils import load_rules, normalize_for_matching, read_report  # noqa: E402

DEFAULT_SCORING_RULES_PATH = (
    Path(__file__).resolve().parent.parent / "docs" / "scoring-rules.json"
)

# Beyan edilen kategorinin anahtar kelimelerinin ne kadarinin metinde
# gecmesi "tam uyum" sayilir.
#
# 34 gercek Havacilikta-YZ raporunda OLCULDU (bu raporlarin dogru
# kategorisi "AI & Machine Learning"):
#
#   AI & Machine Learning     min 0.179  p25 0.402  medyan 0.482  max 0.643
#   Robotics & Automation     min 0.083  p25 0.125  medyan 0.125  max 0.292
#   HealthTech                min 0.000  p25 0.091  medyan 0.091  max 0.182
#   Sustainability / FinTech / Game Design         medyan <= 0.056
#
# 34 raporun 34'unde de en iyi eslesen kategori "AI & Machine Learning"
# cikti; alakasiz bes kategori hicbir raporu kazanmadi.
#
# Esik 0.25 secildi: gozlenen en dusuk dogru-kategori orani (0.179) ile
# p25 (0.402) arasinda. Boylece raporlarin buyuk cogunlugu tam puan alir,
# terim eslesmesi gercekten en zayif olan rapor ~72 puanla "gozden
# gecirilmeli" bandina duser - yanlis alarm degil, mesru bir uyari.
# Kontrol: ayni raporlar FinTech beyan edilseydi (oran 0.053) puan ~10
# olurdu, yani "kritik" bandina duserdi - istenen davranis.
#
# UYARI - bu sayilar bir hata duzeltmesi SONRASI olculdu: ilk olcumde
# anahtar kelimeler ASCII ('makine ogrenmesi'), rapor metni ise diakritikli
# ('makine öğrenmesi') oldugu icin eslesme sessizce eksik cikiyordu ve
# medyan 0.482 yerine 0.286 gorunuyordu (bkz. text_utils.normalize_for_matching).
# Esigi o bozuk olcume gore ayarlamak sistemi kalici olarak yanlis
# kalibre edecekti.
HEDEF_ESLESME_ORANI = 0.25

# Baska bir kategori daha iyi eslesiyorsa puandan en fazla bu kadar
# oraninda kesinti yapilir. 1.0 yapmadik: beyan edilen kategori mutlak
# olarak iyi esleşiyorsa, daha iyi bir alternatifin varligi raporu
# "kategori disi" yapmaz - sadece hakemin dikkatini ceker.
MAKSIMUM_RAKIP_CEZASI = 0.60


def load_scoring_rules(path=DEFAULT_SCORING_RULES_PATH):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _keyword_ratio(normalized_text, kelimeler):
    """Kategorinin anahtar kelimelerinin kaci metinde geciyor (oran 0-1).

    Kac KEZ gectigini degil KAC FARKLI kelimenin gectigini sayiyoruz:
    "model" kelimesini 80 kez tekrarlayan bir rapor, kategoriye 80 kat
    daha uygun degil. Farkli terim sayisi, konu kapsamini daha dogru olcer.
    """
    if not kelimeler:
        return 0.0, []
    bulunan = [k for k in kelimeler if normalize_for_matching(k) in normalized_text]
    return len(bulunan) / len(kelimeler), bulunan


def _char_ngram_similarity(rapor_metni, kategori_metinleri):
    """Config'de anahtar kelimesi olmayan kategoriler icin yedek sinyal.

    Karakter n-gram TF-IDF: Turkce/Ingilizce akraba kelimeleri kismen
    yakalar. scikit-learn yoksa None doner.
    """
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
    except ImportError:
        return None
    korpus = [rapor_metni] + kategori_metinleri
    try:
        X = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=1).fit_transform(
            korpus
        )
    except ValueError:
        return None
    return list(cosine_similarity(X[0:1], X[1:])[0])


def analyze_category(
    pdf_path,
    categories,
    declared_category_id=None,
    rules=None,
    scoring_rules=None,
):
    """Raporun kategori uygunlugunu olcer.

    categories: [{"id": str, "name": str, "description": str (opsiyonel)}]
    declared_category_id: yarismacinin secdigi kategori. None verilirse
        modul "en uygun kategori hangisi" sorusunu yanitlar ve onu puanlar.

    Doner:
      {
        "kategori_onerisi": str,           # en iyi eslesen kategori adi
        "kategori_guven_skoru": float,     # 0-1
        "beyan_edilen": str | None,
        "beyan_edilen_puani": int,         # 0-100
        "siralama": [{"kategori", "oran", "eslesen_kelimeler", "yontem"}],
        "yontem": "anahtar_kelime" | "karakter_ngram" | "karma",
      }
    ya da rapor okunamadiysa {"hata": "..."}.
    """
    if rules is None:
        rules = load_rules()
    if scoring_rules is None:
        scoring_rules = load_scoring_rules()

    if not categories:
        return {"hata": "Karsilastirilacak kategori tanimi yok."}

    rapor = read_report(pdf_path, rules)
    if "hata" in rapor:
        return {"hata": rapor["hata"]}

    normalized = normalize_for_matching(rapor["metin"])
    tanimlar = scoring_rules["kategori"]["anahtar_kelimeler"]

    # 1. Anahtar kelime tanimi olan kategorileri olc
    siralama = []
    tanimsizlar = []
    for kategori in categories:
        ad = kategori.get("name") or ""
        tanim = tanimlar.get(ad)
        if tanim is None:
            # Turkce ad uzerinden de dene (frontend Turkce ad kullaniyor)
            tanim = next(
                (t for t in tanimlar.values() if t.get("turkce_ad") == ad),
                None,
            )
        if tanim is None:
            tanimsizlar.append(kategori)
            continue
        oran, bulunan = _keyword_ratio(normalized, tanim["kelimeler"])
        siralama.append(
            {
                "kategori_id": kategori.get("id"),
                "kategori": ad,
                "oran": round(oran, 4),
                "eslesen_kelimeler": bulunan,
                "yontem": "anahtar_kelime",
            }
        )

    # 2. Tanimsiz kategoriler icin karakter n-gram yedegi
    if tanimsizlar:
        kategori_metinleri = [
            f"{k.get('name', '')} {k.get('description', '') or ''}" for k in tanimsizlar
        ]
        benzerlikler = _char_ngram_similarity(rapor["metin"], kategori_metinleri)
        for i, kategori in enumerate(tanimsizlar):
            oran = float(benzerlikler[i]) if benzerlikler else 0.0
            siralama.append(
                {
                    "kategori_id": kategori.get("id"),
                    "kategori": kategori.get("name") or "",
                    "oran": round(oran, 4),
                    "eslesen_kelimeler": [],
                    "yontem": "karakter_ngram",
                }
            )

    siralama.sort(key=lambda s: s["oran"], reverse=True)
    en_iyi = siralama[0]

    yontemler = {s["yontem"] for s in siralama}
    yontem = yontemler.pop() if len(yontemler) == 1 else "karma"

    # 3. Beyan edilen kategoriyi puanla
    beyan = None
    if declared_category_id is not None:
        beyan = next((s for s in siralama if s["kategori_id"] == declared_category_id), None)
    if beyan is None:
        # Beyan yok (ya da beyan edilen kategori listede degil): sistem
        # "en uygun kategori" onerisini puanlar. Bu, backend beyan edilen
        # kategoriyi gecmedigi eski cagri sekliyle de calismayi saglar.
        beyan = en_iyi

    mutlak = min(1.0, beyan["oran"] / HEDEF_ESLESME_ORANI) if HEDEF_ESLESME_ORANI else 0.0

    en_iyi_rakip = next((s for s in siralama if s is not beyan), None)
    ceza = 0.0
    if en_iyi_rakip and en_iyi_rakip["oran"] > beyan["oran"] > 0:
        ceza = (en_iyi_rakip["oran"] - beyan["oran"]) / en_iyi_rakip["oran"]
    elif en_iyi_rakip and en_iyi_rakip["oran"] > 0 and beyan["oran"] == 0:
        ceza = 1.0

    puan = int(round(100 * mutlak * (1 - MAKSIMUM_RAKIP_CEZASI * ceza)))

    return {
        "kategori_onerisi": en_iyi["kategori"],
        "kategori_guven_skoru": round(min(1.0, en_iyi["oran"] / HEDEF_ESLESME_ORANI), 3),
        "beyan_edilen": beyan["kategori"] if declared_category_id else None,
        "beyan_edilen_puani": max(0, min(100, puan)),
        "siralama": siralama,
        "yontem": yontem,
    }


def analyze_category_fit_for_ui(
    pdf_path,
    categories,
    declared_category_id=None,
    rules=None,
    scoring_rules=None,
):
    """analyze_category ciktisini hakem panelinin bekledigi
    {"score", "summary", "findings"} formatina cevirir.

    Pozitif polarite: YUKSEK puan iyi (frontend/src/lib/ai-analysis.ts).
    Bantlar: >=85 "Yuksek guven", 65-84 "Gozden gecirilmeli", <65 "Kritik".
    """
    if scoring_rules is None:
        scoring_rules = load_scoring_rules()

    sonuc = analyze_category(
        pdf_path, categories, declared_category_id, rules, scoring_rules
    )
    if "hata" in sonuc:
        return {
            "score": 0,
            "summary": f"Kategori analizi yapılamadı: {sonuc['hata']}",
            "findings": [
                "Rapor metni okunamadığı için kategori uygunluğu değerlendirilemedi.",
                "Hakem kategori uygunluğunu elle kontrol etmeli.",
            ],
        }

    puan = sonuc["beyan_edilen_puani"]
    en_iyi = sonuc["siralama"][0]
    beyan_satiri = next(
        (s for s in sonuc["siralama"] if s["kategori"] == (sonuc["beyan_edilen"] or en_iyi["kategori"])),
        en_iyi,
    )

    bulgular = []
    if sonuc["beyan_edilen"]:
        if puan >= 85:
            ozet = f"Rapor, beyan edilen \"{sonuc['beyan_edilen']}\" kategorisine uyumlu."
        elif puan >= 65:
            ozet = (
                f"Rapor \"{sonuc['beyan_edilen']}\" kategorisine kısmen uyuyor, "
                "hakem kategori seçimini gözden geçirmeli."
            )
        else:
            ozet = (
                f"Rapor, beyan edilen \"{sonuc['beyan_edilen']}\" kategorisine zayıf uyuyor."
            )
        bulgular.append(
            f"Beyan edilen kategori \"{sonuc['beyan_edilen']}\": kategori terimlerinin "
            f"%{round(100 * beyan_satiri['oran'])}'i raporda geçiyor."
        )
        if en_iyi["kategori"] != sonuc["beyan_edilen"]:
            bulgular.append(
                f"Daha iyi eşleşen kategori: \"{en_iyi['kategori']}\" "
                f"(%{round(100 * en_iyi['oran'])}). Kategori değişikliği hakemin kararı."
            )
        else:
            bulgular.append("Beyan edilen kategori, en iyi eşleşen kategori ile aynı.")
    else:
        # Beyan edilen kategori sisteme gecilmemis - ne oldugunu saklamiyoruz
        if puan >= 85:
            ozet = f"Rapor en çok \"{en_iyi['kategori']}\" kategorisine uyuyor."
        elif puan >= 65:
            ozet = f"Rapor \"{en_iyi['kategori']}\" kategorisine kısmen uyuyor."
        else:
            ozet = "Rapor hiçbir tanımlı kategoriye güçlü şekilde uymuyor."
        bulgular.append(
            "Beyan edilen kategori sisteme geçilmediği için en uygun kategori önerisi "
            "puanlandı; bu, kategori uygunluğunun doğrulanması DEĞİLDİR."
        )
        bulgular.append(
            f"En uygun kategori önerisi: \"{en_iyi['kategori']}\" "
            f"(%{round(100 * en_iyi['oran'])} terim eşleşmesi)."
        )

    if beyan_satiri["eslesen_kelimeler"]:
        ornekler = ", ".join(beyan_satiri["eslesen_kelimeler"][:8])
        bulgular.append(f"Eşleşen terimler (ilk 8): {ornekler}.")

    if beyan_satiri["yontem"] == "karakter_ngram":
        bulgular.append(
            "UYARI: Bu kategori için docs/scoring-rules.json'da anahtar kelime tanımı yok; "
            "puan, kategori adı/açıklaması ile karakter benzerliğinden üretildi — zayıf bir "
            "yöntem. Hakem bu puana güvenmeden önce kategori tanımını elle kontrol etmeli."
        )

    return {"score": puan, "summary": ozet, "findings": bulgular}
