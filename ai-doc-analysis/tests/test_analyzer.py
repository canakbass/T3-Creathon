"""Hafif, bagimsiz test scripti - pytest gerektirmez.
Calistirmak icin: python tests/test_analyzer.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from analyzer import check_template, detect_language, analyze_document, load_rules, analyze_document_for_ui
from template_extract import sablondan_cikar, _turkce_kucult, _alt_bolumleri_ele

passed = 0
failed = 0


def check(name, condition):
    global passed, failed
    if condition:
        print(f"PASS - {name}")
        passed += 1
    else:
        print(f"FAIL - {name}")
        failed += 1


rules = {"zorunlu_basliklar": ["Özet", "Problem Tanımı", "Yöntem", "Bulgular", "Sonuç"]}

# 1. Tum basliklar mevcutsa sablon uygun olmali
tam_metin = "ÖZET\n...\nPROBLEM TANIMI\n...\nYÖNTEM\n...\nBULGULAR\n...\nSONUÇ\n..."
sonuc = check_template(tam_metin, rules)
check("tum basliklar buyuk harfle yazilmis metinde bulunuyor", sonuc["sablon_uygun"] is True)

# 2. Bir baslik eksikse raporlanmali
eksik_metin = "Özet\n...\nProblem Tanımı\n...\nYöntem\n...\nBulgular\n..."
sonuc = check_template(eksik_metin, rules)
check("eksik baslik dogru tespit ediliyor", sonuc["eksik_basliklar"] == ["Sonuç"])

# 3. Turkce dotless-i / dotted-I uc durumu: "TANIMI" (buyuk, noktasiz I)
# vs rules'daki "Tanımı" (kucuk, noktasiz i) eslesmeli
buyuk_harf_metin = "ÖZET PROBLEM TANIMI YÖNTEM BULGULAR SONUÇ"
sonuc = check_template(buyuk_harf_metin, rules)
check("tamamen buyuk harfli Turkce metin dogru eslesiyor", sonuc["sablon_uygun"] is True)

# 3b. Esanlamli baslik: "Sonuc" yerine "Netice" yazilmis ama rules'da
# esanlamli olarak tanimli - eksik sayilmamali
esanlamli_rules = dict(rules, esanlamli_basliklar={"Sonuç": ["Netice"]})
esanlamli_metin = "Özet\n...\nProblem Tanımı\n...\nYöntem\n...\nBulgular\n...\nNetice\n..."
sonuc = check_template(esanlamli_metin, esanlamli_rules)
check("esanlamli baslik (Netice=Sonuc) eksik sayilmiyor", sonuc["sablon_uygun"] is True)

# 4. Bos metinde dil tespiti 'unknown' donmeli, hata firlatmamali
check("bos metinde dil 'unknown' donuyor", detect_language("") == "unknown")
check("cok kisa/anlamsiz metinde de cokmuyor", detect_language("...") == "unknown" or isinstance(detect_language("..."), str))

# 5. Var olmayan dosya - analyze_document cokmemeli, 'hata' alaniyla donmeli
sonuc = analyze_document("olmayan_dosya.pdf", rules)
check("var olmayan dosyada 'hata' alani doner, exception firlamaz", "hata" in sonuc)

# 6. docs/mvp-rules.json gercekten okunabiliyor mu
gercek_rules = load_rules()
check("mvp-rules.json okunabiliyor ve zorunlu_basliklar iceriyor", "zorunlu_basliklar" in gercek_rules)

# 7. Farkli yarismanin gercek raporlari (Saglikta YZ, PDR) - guncel kural seti
# artik Havacilikta YZ / KTR basliklarini iceriyor, bu yuzden bu raporlarin
# UYUMSUZ cikmasi beklenir (yanlis sablon kullanma senaryosunu test eder)
sample_dir = Path(__file__).resolve().parent.parent / "sample_reports"
for dosya in ["saglikta_yz_pdr_zebot-e1.pdf", "saglikta_yz_pdr_ckup.pdf"]:
    sonuc = analyze_document(str(sample_dir / dosya), gercek_rules)
    check(f"{dosya}: dil 'tr' tespit ediliyor", sonuc.get("dil") == "tr")
    check(f"{dosya}: farkli sablon oldugu icin sablon_uygun=False", sonuc.get("sablon_uygun") is False)

# 8. Havacilikta YZ / KTR - 34 gercek finalist raporundan orneklem (TEKNOFEST
# Derece Listesi'nden indirildi, bkz. sample_reports/havacilikta_yz_ktr/README.md)
ktr_dir = sample_dir / "havacilikta_yz_ktr" / "reports"

# Perplexity'nin dogrulama tablosunda "birebir" (tum basliklar uyumlu) olarak
# isaretlenen raporlar - kendi analyzer.py'mizle bagimsiz dogrulandi
for dosya in ["KTR_00_YXpGnt7IevOLKmM75xNlXyQlgHmz2bTM.pdf", "KTR_01_zrY5U4C9Q5AVFoTXPPQd6mkXHSI9dJhW.pdf"]:
    sonuc = analyze_document(str(ktr_dir / dosya), gercek_rules)
    check(f"{dosya}: sablon_uygun (tum basliklar birebir uyuyor)", sonuc.get("sablon_uygun") is True)

# ESANLAMLI BASLIK TESTI: bu raporlar gercekten dereceye girmis/finalist
# olmus (yani gercek hakemler onlari kabul etmis) ama bazi basliklari farkli
# kelimeyle yazmislar (orn. "Kaynakca" yerine "Referanslar"). Birebir string
# eslesmesi bunlari haksiz yere "eksik" sayardi - esanlamli_basliklar
# sayesinde artik dogru sekilde uygun sayiliyorlar.
esanlamli_gecen_raporlar = [
    "KTR_04_5j08MAXDiofjTNfVPzwdaJow1BYgFOee.pdf",  # "Veri Setleri ve Algoritmalar" -> Algoritmalar ve Sistem Mimarisi
    "KTR_13_R1bVfdsapUpMaHHTj8runrvxXZPt1Mr4.pdf",  # "Referanslar" -> Kaynakca
    "KTR_14_mYMgQVHFDGJqLncIfpFW4OKvkqwM96ep.pdf",  # "Referanslar"/"Kaynaklar" -> Kaynakca
    "KTR_22_AGMSZHBzFTW5FoWHy7FHSth9bgCOEJsD.pdf",  # "Referanslar"/"Kaynaklar" -> Kaynakca
]
for dosya in esanlamli_gecen_raporlar:
    sonuc = analyze_document(str(ktr_dir / dosya), gercek_rules)
    check(
        f"{dosya}: esanlamli baslik sayesinde sablon_uygun=True (gercekte hakemler de kabul etmisti)",
        sonuc.get("sablon_uygun") is True,
    )

# KTR_12: BU GERCEKTEN eksik - CSV'ye gore Kaynakca bolumu (ya da esanlamlisi)
# hic yok, farkli isimli bile degil. Esanlamli listesi bunu duzeltmemeli.
sonuc = analyze_document(str(ktr_dir / "KTR_12_iG0MdwwmzU4g74omya3paxGSLfsqawqd.pdf"), gercek_rules)
check("KTR_12: Kaynakca gercekten yok, esanlamli da bulunamiyor", "Kaynakça" in sonuc.get("eksik_basliklar", []))

# KTR_13: DUZELTME - bu rapor gercekte tamamen Turkce (icerigi bizzat kontrol
# edildi). Ilk versiyonda "dil=en" cikmisti ama bu, detect_language'in ilk
# 1000 karakteri kullanmasindan kaynaklanan YANLIS bir tespitti (Icindekiler +
# kisaltma listesindeki Ingilizce terimler langdetect'i yaniltmisti). Pencere
# duzeltmesinden sonra dogru sekilde 'tr' cikiyor - regresyon testi:
sonuc = analyze_document(str(ktr_dir / "KTR_13_R1bVfdsapUpMaHHTj8runrvxXZPt1Mr4.pdf"), gercek_rules)
check("KTR_13: aslinda Turkce, dogru tespit ediliyor (dil penceresi duzeltmesi)", sonuc.get("dil") == "tr")

# KTR_08: GERCEK bir sinir durumu - bu PDF'in font kodlamasi bozuk (Word/PDF
# donusturucu hatasi), bazi "İ" harfleri "Ġ" olarak cikiyor. Bu bizim kodun
# hatasi degil, kaynak dosyanin kendi sorunu - ama analyze_document yine de
# cokmemeli, sadece yanlis/belirsiz bir dil sonucu dondurebilir.
sonuc = analyze_document(str(ktr_dir / "KTR_08_PhJX36PYmJso87uscHkQSwbe2P7HyFbs.pdf"), gercek_rules)
check("KTR_08: bozuk font kodlamasina ragmen cokmuyor, bir sonuc donuyor", "hata" not in sonuc)

# 9. Yeni alanlar: dil_uygun, sayfa_sayisi/sayfa_uygun, icerik_yetersiz_basliklar
sonuc = analyze_document(str(ktr_dir / "KTR_00_YXpGnt7IevOLKmM75xNlXyQlgHmz2bTM.pdf"), gercek_rules)
check("dil_uygun alani var ve True (tr kabul edilen dil)", sonuc.get("dil_uygun") is True)
check("sayfa_sayisi sayi olarak donuyor", isinstance(sonuc.get("sayfa_sayisi"), int) and sonuc["sayfa_sayisi"] > 0)
check("sayfa_uygun True (8-18 sayfa araliginda)", sonuc.get("sayfa_uygun") is True)
check("icerik_yetersiz_basliklar bos liste (Takim Semasi istisnasi calisiyor)", sonuc.get("icerik_yetersiz_basliklar") == [])

# 10. analyze_document_for_ui: backend'in bekledigi score/summary/findings
# formatina cevirme katmani (bkz. t3creathon_web-master/backend/app/services/ai.py
# - takim orada baska bir sozlesme uzerine calismis, bu adaptor onu koprulyor)
sonuc = analyze_document_for_ui(str(ktr_dir / "KTR_00_YXpGnt7IevOLKmM75xNlXyQlgHmz2bTM.pdf"), gercek_rules)
check("analyze_document_for_ui: languageTemplate anahtari var", "languageTemplate" in sonuc)
check("analyze_document_for_ui: contentHeading anahtari var", "contentHeading" in sonuc)
check("tam uygun raporda languageTemplate skoru 100", sonuc["languageTemplate"]["score"] == 100)
check("tam uygun raporda contentHeading skoru 100", sonuc["contentHeading"]["score"] == 100)

sonuc = analyze_document_for_ui(str(ktr_dir / "KTR_12_iG0MdwwmzU4g74omya3paxGSLfsqawqd.pdf"), gercek_rules)
check(
    "eksik baslikli raporda languageTemplate skoru 85'in altina dusuyor (caution bandina girer)",
    sonuc["languageTemplate"]["score"] < 85,
)

sonuc = analyze_document_for_ui(str(ktr_dir / "KTR_08_PhJX36PYmJso87uscHkQSwbe2P7HyFbs.pdf"), gercek_rules)
check(
    "bozuk font/yanlis dil raporunda languageTemplate skoru 65'in altina dusuyor (critical bandina girer)",
    sonuc["languageTemplate"]["score"] < 65,
)

sonuc = analyze_document_for_ui("olmayan_dosya.pdf", gercek_rules)
check("olmayan dosyada analyze_document_for_ui cokmuyor, skor 0 donuyor", sonuc["languageTemplate"]["score"] == 0)

# --- Sablon dosyasindan otomatik cikarim ------------------------------------
#
# NEDEN VAR: Yarisma Yoneticisi zorunlu basliklari ve kriter agirliklarini
# TEK TEK elle giriyordu. TEKNOFEST'in resmi sablon dosyalari bu bilgiyi
# zaten makine-okunur bicimde tasiyor (Word baslik stilleri + "(N Puan)").
ORNEK_DIZIN = Path(__file__).resolve().parent.parent / "sample_reports"
OTR_SABLONU = ORNEK_DIZIN / "havacilikta_yz_ktr" / "sablon_OTR_2026.docx"
PDR_SABLONU = ORNEK_DIZIN / "referans_2026_pdr_sablonu_universite.docx"

check(
    "Turkce kucultme noktali I tuzagina dusmuyor",
    _turkce_kucult("ŞEKİL LİSTESİ") == "şekil listesi",
)
# Python'un kendi casefold'u burada "şeki̇l li̇stesi̇" uretiyor (i + birlesen
# nokta) ve duz metinle eslesmiyor - bu tuzak bu projede daha once gercek bir
# hataya yol acti.
check(
    "str.casefold() bu is icin YETERSIZ (tuzagin kendisi)",
    "ŞEKİL LİSTESİ".casefold() != "şekil listesi",
)

# Alt bolum eleme kurali: cocuklarin toplami ebeveynin puanina esitse elenir.
check(
    "alt bolumler (10+15+5=30) ana bolumun icinden eleniyor",
    [b["baslik"] for b in _alt_bolumleri_ele([
        {"baslik": "ANA", "agirlik": 30},
        {"baslik": "alt-1", "agirlik": 10},
        {"baslik": "alt-2", "agirlik": 15},
        {"baslik": "alt-3", "agirlik": 5},
        {"baslik": "SONRAKI", "agirlik": 70},
    ])] == ["ANA", "SONRAKI"],
)
check(
    "tek bir esit puanli komsu alt bolum SAYILMIYOR (kardes olabilir)",
    len(_alt_bolumleri_ele([
        {"baslik": "A", "agirlik": 50},
        {"baslik": "B", "agirlik": 50},
    ])) == 2,
)

if OTR_SABLONU.exists():
    otr = sablondan_cikar(str(OTR_SABLONU))
    check(
        "resmi OTR sablonundan 8 ana baslik cikariliyor",
        len(otr["basliklar"]) == 8,
    )
    check(
        "OTR agirliklari TAM 100'e topluyor (naif cikarim 130 verir)",
        otr["agirlik_toplami"] == 100,
    )
    check(
        "belge susleri (SEKIL LISTESI / TABLO LISTESI) basliklara girmiyor",
        not any("LİSTESİ" in b for b in otr["basliklar"]),
    )
    check(
        "sayfa numaralari basliga yapismiyor",
        "PROJE MEVCUT DURUM DEĞERLENDİRMESİ" in otr["basliklar"],
    )
    check("temiz cikarimda uyari uretilmiyor", otr["uyarilar"] == [])

if PDR_SABLONU.exists():
    pdr = sablondan_cikar(str(PDR_SABLONU))
    check(
        "universite PDR sablonu da tam 100'e topluyor",
        pdr["agirlik_toplami"] == 100,
    )
    check(
        "farkli sablon FARKLI baslik seti veriyor (sabit liste degil)",
        pdr["basliklar"] == ["GİRİŞ", "YÖNTEM", "BULGULAR", "SONUÇ", "KAYNAKÇA"],
    )

# Hata yollari: cokmuyor, sebebini soyluyor
bozuk = sablondan_cikar("olmayan_dosya.docx")
check("olmayan dosyada cokmuyor", bozuk["basliklar"] == [] and bozuk["uyarilar"])
desteksiz = sablondan_cikar("bir_dosya.txt")
check(
    "desteklenmeyen turde sebebi soyluyor",
    any("Desteklenmeyen" in u for u in desteksiz["uyarilar"]),
)
eski_doc = sablondan_cikar("eski.doc")
check(
    "eski .doc icin yol gosteriyor (.docx olarak kaydedin)",
    any(".docx" in u for u in eski_doc["uyarilar"]),
)

print(f"\n{passed} basarili, {failed} basarisiz")
sys.exit(1 if failed else 0)
