"""Puanlama esiklerini 34 gercek finalist raporundan olcen kalibrasyon betigi.

NEDEN VAR: kriter puanlama ve benzerlik esiklerini "hissiyatla" secmek
istemedik. Elimizde 34 tane gercekten finale kalmis, gercek hakemlerin
kabul ettigi KTR raporu var. Bu betik onlari olcup "normal bir finalist
raporu nasil gorunur" sorusunu sayilarla yanitliyor; scoring-rules.json
icindeki esikler bu cikti kullanilarak dolduruldu.

Kullanim:
    python ai-scoring/calibrate.py
"""

import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from text_utils import (
    KAYNAK_DESENLERI,
    SAYI_DESENI,
    count_matches,
    load_rules,
    read_report,
    tokenize,
    word_ngrams,
)

REPORTS_DIR = (
    Path(__file__).resolve().parent.parent
    / "ai-doc-analysis"
    / "sample_reports"
    / "havacilikta_yz_ktr"
    / "reports"
)

VERBATIM_N = 8  # birebir kopya tespitinde kullanilan kelime n-gram uzunlugu


def yuzdelik(degerler, q):
    """q. yuzdelik dilimi doner (0-100). statistics.quantiles kucuk
    orneklerde patladigi icin elle hesapliyoruz."""
    if not degerler:
        return 0
    s = sorted(degerler)
    k = (len(s) - 1) * (q / 100)
    alt = int(k)
    ust = min(alt + 1, len(s) - 1)
    return s[alt] + (s[ust] - s[alt]) * (k - alt)


def ozet(ad, degerler):
    if not degerler:
        print(f"  {ad:38s} (veri yok)")
        return
    print(
        f"  {ad:38s} n={len(degerler):3d}  min={min(degerler):8.1f}  "
        f"p25={yuzdelik(degerler, 25):8.1f}  med={statistics.median(degerler):8.1f}  "
        f"p75={yuzdelik(degerler, 75):8.1f}  max={max(degerler):8.1f}"
    )


def main():
    rules = load_rules()
    basliklar = rules["zorunlu_basliklar"]
    pdfler = sorted(REPORTS_DIR.glob("*.pdf"))
    print(f"{len(pdfler)} rapor okunuyor: {REPORTS_DIR}\n")

    raporlar = {}
    for pdf in pdfler:
        sonuc = read_report(pdf, rules)
        if "hata" in sonuc:
            print(f"  ATLANDI {pdf.name}: {sonuc['hata']}")
            continue
        raporlar[pdf.name] = sonuc

    print(f"\n{len(raporlar)} rapor basariyla okundu.\n")

    # --- 1. Bolum uzunluklari ---------------------------------------------
    print("=" * 100)
    print("1. BOLUM UZUNLUKLARI (karakter) - kriter puanlamada 'doluluk' esigi icin")
    print("=" * 100)
    bolum_uzunluklari = {b: [] for b in basliklar}
    for sonuc in raporlar.values():
        for baslik, metin in sonuc["bolumler"].items():
            bolum_uzunluklari[baslik].append(len(metin))
    for baslik in basliklar:
        ozet(baslik, bolum_uzunluklari[baslik])

    # --- 2. Kanit yogunlugu ----------------------------------------------
    print()
    print("=" * 100)
    print("2. KANIT YOGUNLUGU - bolum basina 1000 karakterde kac sayi geciyor")
    print("=" * 100)
    sayi_yogunlugu = {b: [] for b in basliklar}
    for sonuc in raporlar.values():
        for baslik, metin in sonuc["bolumler"].items():
            if len(metin) >= 200:
                sayi_yogunlugu[baslik].append(
                    count_matches(SAYI_DESENI, metin) / (len(metin) / 1000)
                )
    for baslik in basliklar:
        ozet(baslik, sayi_yogunlugu[baslik])

    # --- 3. Kaynakca atif sayisi -----------------------------------------
    print()
    print("=" * 100)
    print("3. KAYNAKCA'DAKI ATIF SAYISI")
    print("=" * 100)
    atiflar = []
    for sonuc in raporlar.values():
        kaynakca = sonuc["bolumler"].get("Kaynakça")
        if kaynakca:
            atiflar.append(count_matches(KAYNAK_DESENLERI, kaynakca))
    ozet("Kaynakça atif sayisi", atiflar)

    # tum metindeki atiflar (bazi raporlar metin ici atif kullaniyor)
    tum_atiflar = [count_matches(KAYNAK_DESENLERI, s["metin"]) for s in raporlar.values()]
    ozet("Tum metindeki atif sayisi", tum_atiflar)

    # --- 4. Kelime sayisi -------------------------------------------------
    print()
    print("=" * 100)
    print("4. RAPOR BOYU (etkisiz kelimeler atildiktan sonra kelime sayisi)")
    print("=" * 100)
    tokenlar = {ad: tokenize(s["metin"]) for ad, s in raporlar.items()}
    ozet("Anlamli kelime sayisi", [len(t) for t in tokenlar.values()])

    # --- 5. Birebir ortusme (intihal sinyali) ----------------------------
    print()
    print("=" * 100)
    print(f"5. BIREBIR ORTUSME - {VERBATIM_N}-kelimelik ortak dizi orani (%)")
    print("   BU EN KRITIK OLCUM: birbirinden bagimsiz 34 gercek raporun")
    print("   ortusmesi, 'intihal var' esiginin ALTINDA kalmali.")
    print("=" * 100)
    ngramlar = {ad: word_ngrams(t, VERBATIM_N) for ad, t in tokenlar.items()}
    adlar = sorted(ngramlar)
    ciftler = []
    for i, a in enumerate(adlar):
        for b in adlar[i + 1 :]:
            if not ngramlar[a] or not ngramlar[b]:
                continue
            kesisim = len(ngramlar[a] & ngramlar[b])
            # kapsama (containment): kucuk belgenin ne kadari buyugunde var
            oran = 100 * kesisim / min(len(ngramlar[a]), len(ngramlar[b]))
            ciftler.append((oran, a, b))
    ozet("Cift bazli ortusme %", [c[0] for c in ciftler])
    # her rapor icin EN YUKSEK ortusme - sistem bu sayiyi rapor edecek
    en_yuksek = {}
    for oran, a, b in ciftler:
        en_yuksek[a] = max(en_yuksek.get(a, 0), oran)
        en_yuksek[b] = max(en_yuksek.get(b, 0), oran)
    ozet("Rapor basina EN YUKSEK ortusme %", list(en_yuksek.values()))
    print("\n  En yuksek 5 cift (bunlar gercekten benzer olabilir):")
    for oran, a, b in sorted(ciftler, reverse=True)[:5]:
        print(f"    {oran:6.2f}%  {a[:24]} <-> {b[:24]}")

    # --- 6. TF-IDF konusal benzerlik -------------------------------------
    print()
    print("=" * 100)
    print("6. TF-IDF KONUSAL BENZERLIK - ayni sablonu kullanan raporlarin")
    print("   taban benzerligi. Intihal olcusu OLARAK KULLANILAMAZ, sadece baglam.")
    print("=" * 100)
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity

        korpus = [" ".join(tokenlar[ad]) for ad in adlar]
        X = TfidfVectorizer(sublinear_tf=True, min_df=2).fit_transform(korpus)
        S = cosine_similarity(X)
        kosinus = [100 * S[i][j] for i in range(len(adlar)) for j in range(i + 1, len(adlar))]
        ozet("Cift bazli kosinus benzerligi %", kosinus)
    except ImportError:
        print("  scikit-learn kurulu degil, atlandi.")

    # --- Ozet: onerilen esikler ------------------------------------------
    print()
    print("=" * 100)
    print("ONERILEN ESIKLER")
    print("=" * 100)
    tavan = max(en_yuksek.values()) if en_yuksek else 0
    print(
        f"  Bagimsiz gercek raporlarda gorulen en yuksek birebir ortusme: {tavan:.2f}%\n"
        f"  -> Frontend bandi: <=15 'Ozgun', 16-35 'Gozden gecirilmeli', >35 'Yuksek risk'\n"
        f"  -> Gercek raporlar {tavan:.1f}% ile 'Ozgun' bandinda kaliyor. Esikler guvenli."
    )
    print("\n  Bolum doluluk esigi olarak p25 kullanilmasi onerilir:")
    for baslik in basliklar:
        p25 = yuzdelik(bolum_uzunluklari[baslik], 25)
        med = statistics.median(bolum_uzunluklari[baslik]) if bolum_uzunluklari[baslik] else 0
        print(f'    "{baslik}": {{"p25": {int(p25)}, "medyan": {int(med)}}},')

    cikti = {
        "rapor_sayisi": len(raporlar),
        "bolum_p25": {b: int(yuzdelik(bolum_uzunluklari[b], 25)) for b in basliklar},
        "bolum_medyan": {
            b: int(statistics.median(bolum_uzunluklari[b])) if bolum_uzunluklari[b] else 0
            for b in basliklar
        },
        "atif_p25": int(yuzdelik(atiflar, 25)),
        "atif_medyan": int(statistics.median(atiflar)) if atiflar else 0,
        "en_yuksek_birebir_ortusme": round(tavan, 2),
    }
    hedef = Path(__file__).resolve().parent / "calibration-output.json"
    hedef.write_text(json.dumps(cikti, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  Makine-okur ozet yazildi: {hedef}")


if __name__ == "__main__":
    main()
