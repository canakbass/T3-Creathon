"""ai-scoring test paketi. Hafif, bagimsiz script - pytest gerektirmez.
Calistirmak icin: python ai-scoring/tests/test_scorer.py

TEST FELSEFESI: 34 gercek finalist raporunun HEPSI sistemden geciyor
(hepsi gercekten finale kalmis raporlar - gecmeleri dogru davranis). Bu
yuzden pozitif kontrol tek basina hicbir sey kanitlamaz: her seye 100
veren bir sistem de ayni testi gecerdi.

Bu yuzden testlerin agirligi SALDIRGAN vakalarda:
  * birebir kopyalanmis rapor  -> yakalanmali
  * yanlis kategori beyani     -> yakalanmali
  * bos/eksik bolumler         -> yakalanmali
  * bozuk / olmayan dosya      -> cokmemeli
Pozitif kontrol ise "yanlis alarm uretmiyor mu" sorusunu yanitliyor.
"""

import json
import shutil
import sys
import tempfile
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(MODULE_DIR))

from text_utils import (  # noqa: E402
    load_rules,
    normalize_for_matching,
    read_report,
    tokenize,
    turkish_casefold,
    word_ngrams,
)
from category import analyze_category, analyze_category_fit_for_ui  # noqa: E402
from criteria import (  # noqa: E402
    evaluate_criteria,
    evaluate_criteria_for_ui,
    load_scoring_rules,
)
from similarity import (  # noqa: E402
    _verbatim_overlap,
    analyze_similarity,
    check_similarity_for_ui,
)
from scorer import score_report  # noqa: E402

passed = 0
failed = 0


def check(name, condition, detay=""):
    """detay yalnizca test BASARISIZ oldugunda basiliyor - hata ayiklamayi
    kolaylastirmak icin olculen gercek degeri gostermek istiyoruz."""
    global passed, failed
    if condition:
        print(f"PASS - {name}")
        passed += 1
    else:
        print(f"FAIL - {name}" + (f"  [olculen: {detay}]" if detay else ""))
        failed += 1

RULES = load_rules()
SCORING = load_scoring_rules()
KTR_DIR = MODULE_DIR.parent / "ai-doc-analysis" / "sample_reports" / "havacilikta_yz_ktr" / "reports"
RAPORLAR = sorted(KTR_DIR.glob("*.pdf"))

# Backend'in seed kategorileriyle ayni liste (backend/main.py seed_db)
KATEGORILER = [
    {"id": "cat-1", "name": "Robotics & Automation", "description": "Drones, industrial robots."},
    {"id": "cat-2", "name": "AI & Machine Learning", "description": "Neural networks, NLP, vision."},
    {"id": "cat-3", "name": "Sustainability & Energy", "description": "Green tech, renewables."},
    {"id": "cat-4", "name": "FinTech", "description": "Ledgers, lending, trading."},
    {"id": "cat-5", "name": "HealthTech", "description": "Monitoring, diagnostics, wearables."},
    {"id": "cat-6", "name": "Game Design", "description": "Procedural engines, VR/AR."},
]

# Bu raporlarin gercek kategorisi: Havacilikta Yapay Zeka -> cat-2
DOGRU_KATEGORI = "cat-2"
ORNEK = str(RAPORLAR[0])
ORNEK2 = str(RAPORLAR[1])

print("=" * 78)
print("0. ON KOSUL")
print("=" * 78)
check(f"34 referans rapor bulundu ({len(RAPORLAR)} adet)", len(RAPORLAR) == 34)

# ---------------------------------------------------------------------------
print()
print("=" * 78)
print("1. METIN NORMALIZASYONU (diakritik hatasi regresyon testi)")
print("=" * 78)

# Bu tam olarak bir kez gercekten kirilan seydi: config'deki ASCII anahtar
# kelimeler ('ozgun'), diakritikli metinle ('özgün') hic eslesmiyordu ve
# sinyal SESSIZCE olu doguyordu. Hata patlamadigi icin sadece olcum
# yakaladi - bu yuzden kalici bir test birakiyoruz.
check(
    "normalize_for_matching diakritigi katliyor: 'Özgünlük' -> 'ozgunluk'",
    normalize_for_matching("Özgünlük") == "ozgunluk",
    normalize_for_matching("Özgünlük"),
)
check(
    "ASCII anahtar kelime diakritikli metinde bulunuyor ('ozgun' in 'özgün katki')",
    normalize_for_matching("ozgun") in normalize_for_matching("Özgün katkı"),
)
check(
    "turkish_casefold (Hasan'in baslik aramasi) diakritigi KORUYOR - degistirmedik",
    turkish_casefold("Özgünlük") == "özgünlük",
    turkish_casefold("Özgünlük"),
)
check(
    "Turkce buyuk I dogru kucultuluyor: 'İNCELEME' -> 'inceleme'",
    normalize_for_matching("İNCELEME") == "inceleme",
    normalize_for_matching("İNCELEME"),
)
check(
    "tokenize etkisiz kelimeleri atiyor",
    "ve" not in tokenize("model ve algoritma") and "algoritma" in tokenize("model ve algoritma"),
)
check("word_ngrams n'den kisa dizide bos kume donuyor", word_ngrams(["a", "b"], 8) == set())

# ---------------------------------------------------------------------------
print()
print("=" * 78)
print("2. BENZERLIK - SALDIRGAN VAKALAR")
print("=" * 78)

with tempfile.TemporaryDirectory() as tmp:
    # 2a. Birebir kopya: baska bir takimin raporunu aynen yeniden gonderme.
    kopya = Path(tmp) / "birebir_kopya.pdf"
    shutil.copy(RAPORLAR[0], kopya)
    sonuc = analyze_similarity(str(kopya), [str(RAPORLAR[0])], RULES, SCORING)
    check(
        f"birebir kopyalanmis rapor %100'e yakin ortusme veriyor (olculen: %{sonuc['benzerlik_puani']})",
        sonuc["benzerlik_puani"] >= 95,
        f"puan={sonuc['benzerlik_puani']}",
    )
    ui = check_similarity_for_ui(str(kopya), [str(RAPORLAR[0])], RULES, SCORING)
    check(
        f"birebir kopya frontend 'Yuksek risk' bandina (>{SCORING['benzerlik']['kritik_esigi']}) duşuyor",
        ui["score"] > SCORING["benzerlik"]["kritik_esigi"],
        f"score={ui['score']}",
    )

# 2b. Kismi intihal: bir raporun buyuk bir parcasini digerine yapistir.
# PDF uretmeye gerek yok - algoritmayi gercek rapor METNI uzerinde test
# ediyoruz (analyze_similarity zaten ayni fonksiyonu kullaniyor).
metin_a = read_report(RAPORLAR[0], RULES)["metin"]
metin_b = read_report(RAPORLAR[1], RULES)["metin"]
n = SCORING["benzerlik"]["ngram_kelime"]
tok_a = tokenize(metin_a)
tok_b = tokenize(metin_b)
ng_a = word_ngrams(tok_a, n)

temiz_ortusme = _verbatim_overlap(ng_a, word_ngrams(tok_b, n))
check(
    f"iki bagimsiz gercek rapor temiz cikiyor (%{temiz_ortusme:.1f} <= {SCORING['benzerlik']['dikkat_esigi']})",
    temiz_ortusme <= SCORING["benzerlik"]["dikkat_esigi"],
    f"ortusme=%{temiz_ortusme:.2f}",
)

# B raporunun ilk yarisini, A'dan calinmis metinle degistir
calinti = tok_a[: len(tok_a) // 2]
karisik = calinti + tok_b[len(tok_b) // 2 :]
kismi_ortusme = _verbatim_overlap(ng_a, word_ngrams(karisik, n))
check(
    f"yarisi kopyalanmis rapor yakalaniyor (%{kismi_ortusme:.1f} > {SCORING['benzerlik']['kritik_esigi']})",
    kismi_ortusme > SCORING["benzerlik"]["kritik_esigi"],
    f"ortusme=%{kismi_ortusme:.2f}",
)

# 2c. Bos korpus: karsilastirilacak rapor yok
sonuc = check_similarity_for_ui(ORNEK, [], RULES, SCORING)
check("karsilastirilacak rapor yokken puan 0 donuyor", sonuc["score"] == 0)
check(
    "bos korpusta ozet 'ozgunluk kanitlandi' demiyor, durumu duruse aciklıyor",
    "ilk başvuru" in sonuc["summary"] or "yok" in sonuc["summary"],
    sonuc["summary"],
)
check(
    "bos korpus bulgularinda 'kanitlanmis degil' uyarisi var",
    any("GELMEZ" in b or "kanıt" in b for b in sonuc["findings"]),
)

# 2d. Kapsama (containment) mantigi: kucuk belge buyugunun icindeyse yakalanmali
kucuk = word_ngrams(tok_a[:400], n)
check(
    "kapsama mantigi: kisa bir alinti uzun belgede %100 ortusme veriyor "
    "(Jaccard bunu kacirirdi)",
    _verbatim_overlap(kucuk, ng_a) >= 99,
    f"{_verbatim_overlap(kucuk, ng_a):.1f}",
)

# ---------------------------------------------------------------------------
print()
print("=" * 78)
print("3. KATEGORI - SALDIRGAN VAKALAR")
print("=" * 78)

# 3a. Dogru kategori
ui = analyze_category_fit_for_ui(ORNEK, KATEGORILER, DOGRU_KATEGORI, RULES, SCORING)
check(
    f"dogru kategori beyaninda puan yuksek guven bandinda (>=85, olculen {ui['score']})",
    ui["score"] >= 85,
    f"score={ui['score']}",
)

# 3b. Tamamen yanlis kategori - havacilik YZ raporu "FinTech" olarak beyan edilmis
ui_yanlis = analyze_category_fit_for_ui(ORNEK, KATEGORILER, "cat-4", RULES, SCORING)
check(
    f"yanlis kategori (FinTech) beyani kritik banda duşuyor (<65, olculen {ui_yanlis['score']})",
    ui_yanlis["score"] < 65,
    f"score={ui_yanlis['score']}",
)
check(
    "yanlis kategoride bulgular daha iyi eslesen kategoriyi soyluyor",
    any("Daha iyi eşleşen" in b for b in ui_yanlis["findings"]),
    str(ui_yanlis["findings"]),
)
check(
    "yanlis kategoride nihai kararin hakemde oldugu belirtiliyor",
    any("hakemin kararı" in b for b in ui_yanlis["findings"]),
)

# 3c. Beyan edilen kategori gecilmediyse durum aciga cikarilmali
ui_beyansiz = analyze_category_fit_for_ui(ORNEK, KATEGORILER, None, RULES, SCORING)
check(
    "beyan edilen kategori verilmediginde bu durum bulgularda aciklaniyor",
    any("DEĞİLDİR" in b for b in ui_beyansiz["findings"]),
    str(ui_beyansiz["findings"]),
)

# 3d. Config'de tanimi olmayan kategori - zayif yontem uyarisi verilmeli
ozel_kategoriler = KATEGORILER + [
    {"id": "cat-99", "name": "Kuantum Hesaplama", "description": "Kubit, dolanıklık, kuantum devreleri."}
]
ui_tanimsiz = analyze_category_fit_for_ui(ORNEK, ozel_kategoriler, "cat-99", RULES, SCORING)
check(
    "anahtar kelime tanimi olmayan kategoride 'zayif yontem' uyarisi veriliyor",
    any("UYARI" in b for b in ui_tanimsiz["findings"]),
    str(ui_tanimsiz["findings"]),
)

# 3e. Kategori listesi bos
sonuc = analyze_category(ORNEK, [], None, RULES, SCORING)
check("bos kategori listesinde hata donuyor, cokmuyor", "hata" in sonuc)

# 3f. Adi bos olan kategori kayitla cokmemeli
sonuc = analyze_category(
    ORNEK, [{"id": "x", "name": ""}, {"id": "cat-2", "name": "AI & Machine Learning"}],
    "cat-2", RULES, SCORING,
)
check("adi bos kategori kaydi cokmeye yol acmiyor", "hata" not in sonuc)

# ---------------------------------------------------------------------------
print()
print("=" * 78)
print("4. KRITER DEGERLENDIRMESI")
print("=" * 78)

sonuc = evaluate_criteria(ORNEK, None, RULES, SCORING, motor="kural")
check("kural motoru cagirildiginda motor='kural' donuyor", sonuc["motor"] == "kural")
check(
    "rubrikteki 6 kriterin hepsi puanlaniyor",
    len(sonuc["kriter_puanlari"]) == 6,
    str(len(sonuc["kriter_puanlari"])),
)
check(
    "toplam puan 0-100 araliginda",
    0 <= sonuc["toplam_puan"] <= 100,
    str(sonuc["toplam_puan"]),
)
check(
    "onerilen sonuc frontend'in kabul ettigi uc degerden biri",
    sonuc["onerilen_sonuc"] in ("approve", "revise", "reject"),
    sonuc["onerilen_sonuc"],
)
check(
    "her kriterin somut bir gerekcesi var",
    all(len(k["gerekce"]) > 20 for k in sonuc["kriter_puanlari"]),
)
check(
    "agirliklar rubrikle ayni ve toplami 100",
    sum(k["agirlik"] for k in sonuc["kriter_puanlari"]) == 100,
)

# Agirlikli toplam gercekten agirlikli mi - elle yeniden hesapla
elle = round(
    sum(k["puan"] * k["agirlik"] for k in sonuc["kriter_puanlari"])
    / sum(k["agirlik"] for k in sonuc["kriter_puanlari"])
)
check(
    "toplam puan gercekten agirlikli ortalama (elle dogrulandi)",
    sonuc["toplam_puan"] == elle,
    f"modul={sonuc['toplam_puan']} elle={elle}",
)

# Determinizm: kural motoru ayni girdide ayni ciktiyi vermeli
sonuc2 = evaluate_criteria(ORNEK, None, RULES, SCORING, motor="kural")
check(
    "kural motoru deterministik (ayni PDF -> ayni puan)",
    sonuc["toplam_puan"] == sonuc2["toplam_puan"],
)

# Gerekce, hakem panelinde tek metin olarak gosterilecegi icin kriter
# kirilimini icermeli (arayuzde kriter bazli bilesen yok)
check(
    "gerekce metni kriter kirilimini iceriyor (arayuzde ayri bilesen olmadigi icin)",
    "Kriter kırılımı" in sonuc["gerekce"],
)
check(
    "gerekce, kararin hakemde oldugunu belirtiyor",
    "ÖNERİ" in sonuc["gerekce"] and "hakemin" in sonuc["gerekce"],
)
check(
    "gerekce hangi motorun kullanildigini soyluyor",
    "kural tabanlı" in sonuc["gerekce"],
)

# Veritabanindan gelen olculemeyen kriter aciga cikarilmali
db_kriterleri = [
    {"id": "crit-1", "title": "Language & Template Compliance", "max_score": 100},
    {"id": "crit-2", "title": "Technical Novelty", "max_score": 100},
    {"id": "crit-4", "title": "Ethical & Data Privacy Considerations", "max_score": 100},
]
sonuc_db = evaluate_criteria(ORNEK, db_kriterleri, RULES, SCORING, motor="kural")
check(
    "otomatik olculemeyen kriter (Ethical & Data Privacy) aciga cikariliyor",
    "Ethical & Data Privacy Considerations" in sonuc_db["olculemeyen_kriterler"],
    str(sonuc_db["olculemeyen_kriterler"]),
)
check(
    "eslesen kriter (Technical Novelty -> Özgünlük) olculemeyen sayilmiyor",
    "Technical Novelty" not in sonuc_db["olculemeyen_kriterler"],
)
check(
    "olculemeyen kriter icin UYDURMA PUAN uretilmiyor, hakeme yonlendiriliyor",
    any("hakem elle değerlendirmeli" in u for u in sonuc_db["uyarilar"]),
    str(sonuc_db["uyarilar"]),
)

# Bos / eksik bolumler
bos_rules = dict(RULES)
bos_rules["zorunlu_basliklar"] = ["Bulunmayan Baslik A", "Bulunmayan Baslik B"]
sonuc_eksik = evaluate_criteria(ORNEK, None, bos_rules, SCORING, motor="kural")
check(
    "rubrik bolumleri raporda hic yoksa eksik_bolumler doluyor",
    len(sonuc_eksik["eksik_bolumler"]) > 0,
    str(sonuc_eksik["eksik_bolumler"]),
)

# ---------------------------------------------------------------------------
print()
print("=" * 78)
print("5. HATA DAYANIKLILIGI - hicbiri istisna firlatmamali")
print("=" * 78)

for ad, fn in [
    ("analyze_category_fit_for_ui", lambda p: analyze_category_fit_for_ui(p, KATEGORILER, "cat-2", RULES, SCORING)),
    ("check_similarity_for_ui", lambda p: check_similarity_for_ui(p, [ORNEK], RULES, SCORING)),
    ("evaluate_criteria_for_ui", lambda p: evaluate_criteria_for_ui(p, None, RULES, SCORING, "kural")),
]:
    try:
        sonuc = fn("kesinlikle_olmayan_dosya.pdf")
        cokmedi = True
    except Exception as e:
        sonuc = None
        cokmedi = False
        hata = f"{type(e).__name__}: {e}"
    check(f"{ad}: olmayan dosyada cokmuyor", cokmedi, "" if cokmedi else hata)
    if cokmedi:
        anahtar = "suggested_score" if "criteria" in ad else "score"
        check(f"{ad}: olmayan dosyada {anahtar}=0 donuyor", sonuc[anahtar] == 0, str(sonuc[anahtar]))

# Bozuk (PDF olmayan) dosya
with tempfile.TemporaryDirectory() as tmp:
    bozuk = Path(tmp) / "bozuk.pdf"
    bozuk.write_bytes(b"bu bir PDF degil, sadece rastgele bayt")
    try:
        sonuc = check_similarity_for_ui(str(bozuk), [ORNEK], RULES, SCORING)
        check("bozuk PDF'te benzerlik analizi cokmuyor", True)
        check(
            "bozuk PDF'te ozet, bunun analiz hatasi oldugunu (ozgunluk kaniti degil) soyluyor",
            "yapılamadı" in sonuc["summary"],
            sonuc["summary"],
        )
    except Exception as e:
        check("bozuk PDF'te benzerlik analizi cokmuyor", False, f"{type(e).__name__}: {e}")

    # Korpustaki bir rapor bozuksa, digerleri yine karsilastirilmali
    sonuc = analyze_similarity(ORNEK, [ORNEK2, str(bozuk)], RULES, SCORING)
    check(
        "korpustaki bozuk rapor atlanip digerleriyle karsilastirmaya devam ediliyor",
        sonuc["karsilastirilan_rapor_sayisi"] == 1 and len(sonuc["hatalar"]) == 1,
        f"karsilastirilan={sonuc['karsilastirilan_rapor_sayisi']} hatalar={sonuc['hatalar']}",
    )

# KTR_08: font kodlamasi bozuk gercek rapor (Hasan'in testinde de gecen vaka)
ktr_08 = KTR_DIR / "KTR_08_PhJX36PYmJso87uscHkQSwbe2P7HyFbs.pdf"
if ktr_08.exists():
    try:
        sonuc = score_report(
            str(ktr_08), KATEGORILER, DOGRU_KATEGORI, [ORNEK], None, RULES, SCORING, "kural"
        )
        check("bozuk fontlu gercek rapor (KTR_08) tum hattan gecebiliyor", True)
        check(
            "KTR_08 icin yine de bir toplam puan uretiliyor",
            isinstance(sonuc["toplam_puan"], int),
            str(sonuc["toplam_puan"]),
        )
    except Exception as e:
        check("bozuk fontlu gercek rapor (KTR_08) tum hattan gecebiliyor", False, f"{type(e).__name__}: {e}")

# ---------------------------------------------------------------------------
print()
print("=" * 78)
print("6. BACKEND SOZLESMESI (backend/app/services/ai.py beklentileri)")
print("=" * 78)

ui_kat = analyze_category_fit_for_ui(ORNEK, KATEGORILER, DOGRU_KATEGORI, RULES, SCORING)
ui_ben = check_similarity_for_ui(ORNEK, [ORNEK2], RULES, SCORING)
ui_kri = evaluate_criteria_for_ui(ORNEK, None, RULES, SCORING, "kural")

for ad, sonuc in [("categoryMatch", ui_kat), ("similarity", ui_ben)]:
    check(
        f"{ad}: score/summary/findings anahtarlari var",
        set(sonuc) >= {"score", "summary", "findings"},
        str(set(sonuc)),
    )
    check(
        f"{ad}: score int ve 0-100 araliginda",
        isinstance(sonuc["score"], int) and 0 <= sonuc["score"] <= 100,
        str(sonuc["score"]),
    )
    check(f"{ad}: findings bos olmayan bir liste", isinstance(sonuc["findings"], list) and sonuc["findings"])
    check(
        f"{ad}: findings tum elemanlari string (backend json.dumps ediyor)",
        all(isinstance(b, str) for b in sonuc["findings"]),
    )
    check(f"{ad}: summary bos olmayan string", isinstance(sonuc["summary"], str) and sonuc["summary"])

check(
    "evaluate_criteria_for_ui: backend'in bekledigi uc anahtar var",
    set(ui_kri) >= {"suggested_score", "suggested_outcome", "rationale"},
    str(set(ui_kri)),
)
check(
    "suggested_score int ve 0-100 (frontend sayi girdisine varsayilan olarak veriliyor)",
    isinstance(ui_kri["suggested_score"], int) and 0 <= ui_kri["suggested_score"] <= 100,
)
check(
    "suggested_outcome frontend DECISION_LABELS anahtarlarindan biri",
    ui_kri["suggested_outcome"] in ("approve", "revise", "reject"),
)

# Frontend benzerligi TERS polarite ile okuyor: dusuk puan iyi.
# (frontend/src/lib/ai-analysis.ts, polarity: "negative")
check(
    "temiz raporda benzerlik puani 'Ozgun' bandinda (<=15) - ters polarite dogru kullanilmis",
    ui_ben["score"] <= SCORING["benzerlik"]["dikkat_esigi"],
    f"score={ui_ben['score']}",
)

# Tum cikti JSON'a serilestirilebilmeli (backend json.dumps ediyor)
try:
    json.dumps([ui_kat, ui_ben, ui_kri], ensure_ascii=False)
    check("tum ciktilar json.dumps edilebiliyor (backend boyle kaydediyor)", True)
except (TypeError, ValueError) as e:
    check("tum ciktilar json.dumps edilebiliyor", False, str(e))

# score_report - api-contract.md Bolum 2 sozlesmesi
tam = score_report(ORNEK, KATEGORILER, DOGRU_KATEGORI, [ORNEK2], None, RULES, SCORING, "kural")
for alan in (
    "kategori_onerisi", "kategori_guven_skoru", "en_benzer_raporlar",
    "kriter_puanlari", "guclu_yonler", "gelisim_onerileri",
):
    check(f"score_report: api-contract.md alani '{alan}' mevcut", alan in tam)

# ---------------------------------------------------------------------------
print()
print("=" * 78)
print("7. POZITIF KONTROL - 34 GERCEK FINALIST RAPORU")
print("   (Bunlarin gecmesi beklenir; amac YANLIS ALARM aramak)")
print("=" * 78)

kategori_puanlari = []
benzerlik_puanlari = []
kriter_puanlari = []
kazanan_kategoriler = {}

for pdf in RAPORLAR:
    digerleri = [str(p) for p in RAPORLAR if p != pdf]
    k = analyze_category(str(pdf), KATEGORILER, DOGRU_KATEGORI, RULES, SCORING)
    if "hata" not in k:
        kategori_puanlari.append(k["beyan_edilen_puani"])
        kazanan_kategoriler[k["kategori_onerisi"]] = (
            kazanan_kategoriler.get(k["kategori_onerisi"], 0) + 1
        )
    b = analyze_similarity(str(pdf), digerleri, RULES, SCORING)
    if "hata" not in b:
        benzerlik_puanlari.append(b["benzerlik_puani"])
    c = evaluate_criteria(str(pdf), None, RULES, SCORING, motor="kural")
    if "hata" not in c:
        kriter_puanlari.append(c["toplam_puan"])

dikkat = SCORING["benzerlik"]["dikkat_esigi"]
check(
    f"34 raporun HICBIRI intihal isaretlenmiyor (en yuksek %{max(benzerlik_puanlari)} <= {dikkat})",
    max(benzerlik_puanlari) <= dikkat,
    f"max=%{max(benzerlik_puanlari)}",
)
check(
    f"34 raporun tamami dogru kategoriye atanıyor (AI & Machine Learning: "
    f"{kazanan_kategoriler.get('AI & Machine Learning', 0)}/34)",
    kazanan_kategoriler.get("AI & Machine Learning", 0) == 34,
    str(kazanan_kategoriler),
)
check(
    f"34 raporun kategori uygunluk puani hicbirinde kritik banda dusmuyor "
    f"(en dusuk {min(kategori_puanlari)} >= 65)",
    min(kategori_puanlari) >= 65,
    f"min={min(kategori_puanlari)}",
)
check(
    f"34 gercek finalist raporunun hicbiri 'reject' onerisi almiyor "
    f"(en dusuk toplam {min(kriter_puanlari)})",
    min(kriter_puanlari) >= SCORING["karar_esikleri"]["revizyon"],
    f"min={min(kriter_puanlari)}",
)
# Tavan etkisi kontrolu: her seye 100 veren bir sistem de yukaridaki
# testleri gecerdi. Puanlarin GERCEKTEN dagilmasi lazim.
check(
    f"kriter puanlari tavana yapismiyor - ayirt edici bir dagilim var "
    f"({min(kriter_puanlari)}-{max(kriter_puanlari)})",
    max(kriter_puanlari) - min(kriter_puanlari) >= 15,
    f"aralik={max(kriter_puanlari) - min(kriter_puanlari)}",
)
check(
    "hicbir rapor 100'un uzerinde ya da 0'in altinda puan almiyor",
    all(0 <= p <= 100 for p in kriter_puanlari + kategori_puanlari + benzerlik_puanlari),
)

print()
print("-" * 78)
print(
    f"34 rapor ozeti: kategori puani {min(kategori_puanlari)}-{max(kategori_puanlari)} | "
    f"benzerlik %{min(benzerlik_puanlari)}-%{max(benzerlik_puanlari)} | "
    f"kriter toplami {min(kriter_puanlari)}-{max(kriter_puanlari)}"
)
print("-" * 78)

# ---------------------------------------------------------------------------
print()
print("=" * 78)
print("8. LLM SAGLAYICI SECIMI VE GIZLILIK KAPISI")
print("=" * 78)

import importlib  # noqa: E402
import os  # noqa: E402

import llm as llm_modulu  # noqa: E402

_LLM_ENV = (
    "AI_SCORING_LLM",
    "AI_SCORING_LLM_ONAY",
    "AI_SCORING_MODEL",
    "GOOGLE_API_KEY",
    "GEMINI_API_KEY",
    "ANTHROPIC_API_KEY",
    "AI_SCORING_DOTENV",
)
_kaydedilen = {k: os.environ.get(k) for k in _LLM_ENV}


def _llm_ortami(**env):
    """Ilgili ortam degiskenlerini sifirlayip verilenleri kurar.

    AI_SCORING_DOTENV=0 SART: llm.py modul yuklenirken backend/.env'i
    okuyor. Testler ortami sifirliyor ama modul her reload'da .env
    degerlerini geri enjekte ederse bu testler gelistiricinin makinesinde
    (.env varsa) patlar, CI'da (.env yoksa) gecer - yani sinsi bir sekilde
    ortama bagimli olurdu. Bu gercekten oldu ve bu testler yakaladi.
    """
    for k in _LLM_ENV:
        os.environ.pop(k, None)
    os.environ["AI_SCORING_DOTENV"] = "0"
    os.environ.update(env)
    importlib.reload(llm_modulu)
    return llm_modulu


try:
    m = _llm_ortami()
    kullanilabilir, aciklama = m.saglayici_durumu()
    check(
        "VARSAYILAN motor kural tabanli - hicbir veri disari cikmiyor",
        kullanilabilir is False and m.secili_saglayici() == "kural",
        aciklama,
    )

    # Anahtar ortamda duruyor diye rapor metni kendiliginden disari
    # gonderilmemeli; bu bilincli bir karar olmali.
    m = _llm_ortami(GOOGLE_API_KEY="sahte", ANTHROPIC_API_KEY="sahte")
    check(
        "ortamda anahtar VARSA BILE LLM kendiliginden acilmiyor",
        m.saglayici_durumu()[0] is False,
        m.saglayici_durumu()[1],
    )

    m = _llm_ortami(AI_SCORING_LLM="gemini")
    check(
        "gemini secili ama anahtar yoksa kullanilamaz deniyor",
        m.saglayici_durumu()[0] is False and "API_KEY" in m.saglayici_durumu()[1],
        m.saglayici_durumu()[1],
    )

    m = _llm_ortami(AI_SCORING_LLM="gemini", GOOGLE_API_KEY="sahte")
    kullanilabilir, aciklama = m.saglayici_durumu()
    check(
        "GIZLILIK KAPISI: ucretsiz Gemini icin acik onay sart",
        kullanilabilir is False and "ONAY" in aciklama,
        aciklama[:90],
    )
    check(
        "onay uyarisi nedenini acikliyor (Google icerigi urun gelistirmede kullaniyor)",
        "gelistirmek" in aciklama and "sartnamesi" in aciklama,
    )

    m = _llm_ortami(
        AI_SCORING_LLM="gemini", GOOGLE_API_KEY="sahte", AI_SCORING_LLM_ONAY="evet"
    )
    check(
        "acik onay verilince gemini kullanilabilir oluyor",
        m.saglayici_durumu()[0] is True,
        m.saglayici_durumu()[1],
    )
    check(
        "model adi ortam degiskeniyle degistirilebiliyor",
        _llm_ortami(
            AI_SCORING_LLM="gemini",
            GOOGLE_API_KEY="sahte",
            AI_SCORING_LLM_ONAY="evet",
            AI_SCORING_MODEL="gemini-3.5-flash",
        ).saglayici_durumu()[1].endswith("(gemini-3.5-flash)"),
    )

    # Gemini'nin response_schema'si JSON Schema'nin tamamini desteklemiyor.
    temiz = llm_modulu._gemini_semasini_temizle(
        {
            "type": "object",
            "additionalProperties": False,
            "properties": {"a": {"type": "string", "additionalProperties": False}},
        }
    )
    check(
        "gemini sema temizligi additionalProperties'i ozyinelemeli kaldiriyor",
        "additionalProperties" not in temiz
        and "additionalProperties" not in temiz["properties"]["a"],
        str(temiz),
    )
    check(
        "sema temizligi anlami bozmuyor (type/properties duruyor)",
        temiz["type"] == "object" and temiz["properties"]["a"]["type"] == "string",
    )

    # LLM istendi ama kullanilamiyorsa: cokmemeli, kural motoruna dusmeli
    # ve NEDENINI hakeme soylemeli.
    _llm_ortami(AI_SCORING_LLM="gemini")  # anahtar yok
    import criteria as criteria_modulu  # noqa: E402

    importlib.reload(criteria_modulu)
    sonuc_llm = criteria_modulu.evaluate_criteria(ORNEK, None, RULES, SCORING, motor="llm")
    check(
        "LLM kullanilamazken kural motoruna dusuluyor, cokmuyor",
        sonuc_llm.get("motor") == "kural",
        str(sonuc_llm.get("motor")),
    )
    check(
        "dusulme nedeni uyarilarda aciga cikariliyor",
        any("kullanılamıyor" in u for u in sonuc_llm.get("uyarilar", [])),
        str(sonuc_llm.get("uyarilar")),
    )
    check(
        "gerekce metni hangi motorun kullanildigini soyluyor",
        "kural tabanlı" in sonuc_llm["gerekce"],
    )
finally:
    # Ortami eski haline dondur, sonraki testleri etkilemesin.
    for k, v in _kaydedilen.items():
        os.environ.pop(k, None)
        if v is not None:
            os.environ[k] = v
    importlib.reload(llm_modulu)

print(f"\n{passed} basarili, {failed} basarisiz")
sys.exit(1 if failed else 0)
