# teknofest-degerlendirme

T3 Vakfı Yapay Zeka Creathonu — Problem 4: TEKNOFEST rapor değerlendirme
sürecini destekleyen, **AI'nın nihai karar vermediği** bir karar destek
sistemi. AI sadece analiz/öneri üretir, nihai kararı her zaman hakem verir.

Proje bağlamı, ekip, kararlar ve zaman planı için: [`docs/CLAUDE.md`](docs/CLAUDE.md)
ve [`docs/PROJECT_CONTEXT.md`](docs/PROJECT_CONTEXT.md).

## Klasörler ve sorumluluklar

| Klasör | Kişi | İçerik | Durum |
|---|---|---|---|
| `ai-doc-analysis/` | Hasan | Dil/şablon/başlık kontrolü | ✅ Çalışıyor, gerçek veriyle test edildi (32 test) |
| `ai-scoring/` | Hayrettin | Kategori, benzerlik, kriter puanlama | ✅ Çalışıyor, backend'e entegre edildi (76 test) — mock'lar kaldırıldı |
| `backend/` | Mustafa | FastAPI + SQLite — API, veri modeli, auth | ✅ Çalışıyor (auth, upload, analiz akışı, hakem kararı) — 9 test; iki hata düzeltildi (aşağıda) |
| `frontend/` | Mahmut | Next.js — rol bazlı paneller | ⚠️ Arayüz çalışıyor (74 test geçiyor) ama **backend'e hiç bağlı değil** — tüm veri mock (aşağıda) |
| `docs/` | — | Ortak dokümanlar, API sözleşmesi, MVP kuralları | Güncel |

## MVP'nin 6 zorunlu maddesi — güncel durum

| # | Madde | Durum |
|---|---|---|
| 1 | Dil/şablon kontrolü | ✅ Hasan — gerçek kod, backend'e bağlı |
| 2 | Başlık/içerik kontrolü | ✅ Hasan — gerçek kod, backend'e bağlı |
| 3 | Kategori uygunluğu | ✅ Hayrettin — gerçek kod, backend'e bağlı |
| 4 | Benzerlik analizi | ✅ Hayrettin — gerçek kod, backend'e bağlı |
| 5 | AI kriter değerlendirmesi (puan + gerekçe) | ✅ Hayrettin — gerçek kod, backend'e bağlı |
| 6 | Hakemin görüp nihai kararı verebildiği arayüz | ⚠️ **API tarafı çalışıyor, arayüz backend'e bağlı değil** |

Madde 1-5 uçtan uca doğrulandı: gerçek bir KTR PDF'i yükleyip API'den
analizi okuyup hakem kararı verme akışı 40 testle sınandı (aşağıya bakın).
Madde 6'nın backend yarısı (`POST /api/reports/{id}/decision`, hakemin AI
önerisini ezebilmesi) çalışıyor; eksik olan frontend'in API'ye bağlanması.

**Not:** `backend/` ve `frontend/`, Mahmut/Mustafa'nın ayrı ilerlettiği
[t3creathon_web](https://github.com/mahmutconger/t3creathon_web) reposundan
bu monorepoya taşındı (2026-08-23). O repo artık kullanılmıyor — bundan
sonra tüm çalışma buradan devam etmeli, yoksa tekrar ayrışırız.

## Şu ana kadar tamamlanan: `ai-doc-analysis` + backend entegrasyonu

Rapor yüklendiğinde çalışan ilk kontrol katmanı. PDF'i alır, 5 şeyi kontrol
edip JSON döner: dil uygunluğu, sayfa sayısı uygunluğu, şablon uygunluğu
(zorunlu başlıklar), içeriği zayıf bölümler, hatalar.

**Referans veri seti:** TEKNOFEST Havacılıkta Yapay Zeka Yarışması, Kritik
Tasarım Raporu (KTR), 2022 sezonu — **34 gerçek finalist raporu** (uydurma
değil, TEKNOFEST'in kendi Derece Listesi'nden). Detay: [`ai-doc-analysis/README.md`](ai-doc-analysis/README.md).

**Son test sonucu** (`python ai-doc-analysis/tests/test_analyzer.py`):

```
32 başarılı, 0 başarısız
```

**34 gerçek rapor üzerinde toplu sonuç:**

| Sonuç | Adet | Açıklama |
|---|---|---|
| Tam uygun | 32/34 | Dil, sayfa sayısı, şablon, içerik — hepsi geçti |
| Gerçekten eksik bölüm | 1/34 | KTR_12 — "Kaynakça" (ya da eşanlamlısı) hiç yok |
| Kaynak dosya hatası | 1/34 | KTR_08 — PDF'in kendi font kodlaması bozuk (bizim kodun sorunu değil) |

Bu oranlar gerçek hakem kararlarına kasıtlı olarak yakınlaştırıldı: sistem,
"Kaynakça" yerine "Referanslar" yazan bir raporu artık haksız yere
reddetmiyor (bkz. `docs/mvp-rules.json` → `esanlamli_basliklar`).

**Backend entegrasyonu:** Ayrı ilerleyen repoyu incelerken, backend + hakem
panelinin benim modülümden **farklı bir JSON formatı** (0-100 puan +
özet/bulgu) beklediği ortaya çıktı — birbirimizden habersiz farklı
sözleşmeler üzerine çalışmışız. `analyze_document_for_ui()` adlı bir
adaptör yazıp `backend/app/services/ai.py`'ye bağladım, backend'in kendi
test suite'i (7/7) ve gerçek KTR PDF'leriyle uçtan uca (upload→analiz→get)
doğrulandı. Detay: `docs/api-contract.md` Bölüm 1.

## Hayrettin — `ai-scoring` tamamlandı (2026-08-24)

MVP'nin 3, 4 ve 5. maddeleri artık gerçek kod. `backend/app/services/ai.py`
içindeki üç mock fonksiyon (`evaluate_criteria`, `analyze_category_fit`,
`check_similarity`) kaldırıldı — o dosyada artık hiç mock yok, `random`
bağımlılığı da gitti (mock'lar rastgele puan üretiyordu, yani aynı rapor her
analizde farklı puan alıyordu).

Modülün tasarım gerekçeleri, ölçüm sonuçları ve bilinen sınırlamaları:
[`ai-scoring/README.md`](ai-scoring/README.md). En kritik iki karar:

- **Benzerlik puanı TF-IDF kosinüs benzerliğinden DEĞİL birebir kelime
  örtüşmesinden hesaplanıyor.** Ölçtük: birbirinden bağımsız 34 gerçek
  raporun kosinüs benzerliği %11.9–45.2 (hepsi aynı şablonu kullandığı için).
  Kosinüs intihal puanı olarak kullanılsaydı **gerçek ve masum raporların bir
  kısmı intihalle suçlanacaktı.** Aynı raporların birebir örtüşmesi %0–7.9.
- **Ölçülemeyen kritere puan verilmiyor.** Örn. "Ethical & Data Privacy"
  metinden güvenilir ölçülemez; sistem uydurma puan üretmek yerine "hakem
  elle değerlendirmeli" diyor.

Tüm eşikler `docs/scoring-rules.json`'da ve tahmin değil — 34 gerçek rapor
ölçülerek belirlendi (`python ai-scoring/calibrate.py`).

## Mustafa — backend'de iki hata düzeltildi

**1. `GET /api/reports` analiz edilmiş rapor varken HTTP 500 veriyordu.**
`schemas.AiAnalysisResponse` `results` alanını zorunlu tutuyor ama bu bir
veri tabanı kolonu değil — yanıt öncesi düz kolonlardan üretilmesi gerekiyor.
Bu dönüşüm sadece `get_report`'ta yapılıyordu, `list_reports`'ta
yapılmıyordu. Sonuç: veri tabanında analiz edilmiş **ilk** rapor oluşur
olmaz liste endpoint'i düşüyordu — yani **hakem panosunun ana listesi
kullanılamaz durumdaydı.** Dönüşüm `_attach_analysis_results()` yardımcısına
çıkarıldı, iki endpoint de onu kullanıyor. Kalıcı regresyon testi eklendi
(`test_report_list_serializes_analysis`).

**2. Backend test paketi aslında geçmiyordu.** README "7/7 geçti" diyordu
ama gerçek sonuç **1 geçti / 6 hata**'ydı. Sebep `tests/conftest.py`: her
testin sonunda `test_temp.db` dosyası siliniyor, ama SQLAlchemy'nin bağlantı
havuzu o dosyaya ait açık bir tanıtıcı tutmaya devam ediyor → sonraki
testler "attempt to write a readonly database" ile patlıyordu. Testler
**tek tek** çalıştırıldığında geçtiği için hata uzun süre görünmez kaldı.
Bellekte `StaticPool` kullanımına geçildi; şimdi gerçekten 9/9 geçiyor.

Sıradaki (senin kararın): `models.AiAnalysis`'e kriter kırılımı için kolon
eklemek. `evaluate_criteria` kriter bazlı puanları ve yarışmacıya
gösterilecek `guclu_yonler`/`gelisim_onerileri` alanlarını döndürüyor ama
şemada yer olmadığı için kaydedilemiyorlar; şimdilik `rationale` metninin
içine gömülü geliyorlar. Tek taraflı şema değişikliği yapmadım.

## Mahmut — kritik: frontend backend'e hiç bağlı değil

Arayüz çalışıyor ve 74 jest testi geçiyor, ama **hiçbir HTTP isteği
atmıyor.** `frontend/src` içinde `fetch`/`axios` çağrısı, API istemci
katmanı, `NEXT_PUBLIC_*` ortam değişkeni yok. Tüm veri yerel mock:

- `referee-dashboard.tsx` → `setTimeout(() => setReports(getMockReports()))` — sahte gecikme
- `report-upload.tsx` → `simulateUpload()` sahte progress bar, dosyayı hiç göndermiyor
- `dashboard/referee/[id]/page.tsx` → `getMockAnalysis(id)`
- `store/auth-store.ts` → sadece bir `role` string'i tutuyor, token yok, login çağrısı yok

Yani **MVP madde 6 henüz kapanmadı**: backend tarafı hazır ve test edildi
(hakem AI önerisini ezip nihai karar verebiliyor), eksik olan arayüzün API'ye
bağlanması. Demo Day'de gösterilecek akış bu, öncelik burada.

Bağlarken dikkat edilecek iki şey:

- **Alan adı/şekli uyuşmuyor.** Backend snake_case ve öneriyi **düz** veriyor
  (`suggested_score`, `suggested_outcome`, `rationale`); frontend camelCase ve
  **iç içe** bekliyor (`suggestion: {score, outcome, rationale}`). Ayrıca
  backend analizi `ReportResponse.ai_analysis` altında iç içe veriyor,
  frontend rapor ile analizi iki ayrı nesne olarak bekliyor. Bir eşleme
  katmanı gerekiyor. İçteki `results` haritası ise birebir uyuyor —
  `languageTemplate`/`contentHeading`/`categoryMatch`/`similarity`.
- **Analiz asenkron.** `POST /api/reports/upload` hemen `status: "pending"`
  ile dönüyor; analiz arka planda çalışıyor (gerçek PDF'lerde birkaç saniye).
  Arayüzün `status != "pending"` olana kadar yoklaması (polling) lazım —
  yükleme sonrası tek istek atıp analiz beklemek boş sonuç verir.

**Dil konusu kapandı:** senin arayüzü Türkçe'ye çevirmenle
(`c348853`) tutarsızlık bitti, tüm AI çıktıları da Türkçe.

## Kurulum ve test (herkes için)

```bash
# ai-doc-analysis (Hasan)          -> 32 test
pip install -r ai-doc-analysis/requirements.txt
python ai-doc-analysis/tests/test_analyzer.py

# ai-scoring (Hayrettin)           -> 76 test
pip install -r ai-scoring/requirements.txt
python ai-scoring/tests/test_scorer.py

# backend (Mustafa)                -> 9 test
pip install -r backend/requirements.txt
cd backend && python -m pytest tests/ -v

# frontend (Mahmut)                -> 74 test
cd frontend && npm install && npm test
cd frontend && npm run dev
```

**Backend'i gerçekten çalıştırmak için** `JWT_SECRET_KEY` ayarlanmalı, yoksa
public repoda duran güvensiz bir varsayılana düşer ve uyarı basar:

```bash
cd backend
cp .env.example .env   # ve içine bir değer yaz:
python -c "import secrets; print(secrets.token_hex(32))"
python -m uvicorn main:app --reload
```

Seed kullanıcıları (ilk açılışta oluşur): `manager@`, `referee@`,
`competitor@`, `evaluator@teknofest.org` — hepsinin şifresi `password123`.

### Son test durumu (2026-08-24)

| Paket | Sonuç |
|---|---|
| `ai-doc-analysis` | 32 başarılı, 0 başarısız |
| `ai-scoring` | 76 başarılı, 0 başarısız |
| `backend` (pytest) | 9 başarılı, 0 başarısız |
| `frontend` (jest) | 74 başarılı, 0 başarısız |
| `frontend` (next build) | başarılı |
| Uçtan uca (canlı sunucu + gerçek KTR PDF'leri) | 40 başarılı, 0 başarısız |

Uçtan uca testte doğrulananlar: 4 rolün girişi, gerçek PDF yükleme, dört
analizin veri tabanına yazılması, hakemin AI önerisini ezip nihai karar
vermesi, rol bazlı yetkilendirme (yarışmacı karar veremiyor, kendi raporundan
başkasını göremiyor), ve saldırgan vakalar: birebir kopyalanmış rapor %100
örtüşmeyle "Yüksek risk", yanlış kategori beyanı 10 puanla "Kritik", bozuk
dosya sistemi çökertmiyor.
