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
| `frontend/` | Mahmut | Next.js — rol bazlı paneller | ✅ Çalışıyor ve **backend'e bağlandı** — 87 test; tüm mock veri kaldırıldı |
| `docs/` | — | Ortak dokümanlar, API sözleşmesi, MVP kuralları | Güncel |

## MVP'nin 6 zorunlu maddesi — hepsi tamam

| # | Madde | Durum |
|---|---|---|
| 1 | Dil/şablon kontrolü | ✅ Hasan — gerçek kod, uçtan uca çalışıyor |
| 2 | Başlık/içerik kontrolü | ✅ Hasan — gerçek kod, uçtan uca çalışıyor |
| 3 | Kategori uygunluğu | ✅ Hayrettin — gerçek kod, uçtan uca çalışıyor |
| 4 | Benzerlik analizi | ✅ Hayrettin — gerçek kod, uçtan uca çalışıyor |
| 5 | AI kriter değerlendirmesi (puan + gerekçe) | ✅ Hayrettin — gerçek kod, uçtan uca çalışıyor |
| 6 | Hakemin görüp nihai kararı verebildiği arayüz | ✅ Arayüz canlı API'ye bağlı, hakem AI önerisini ezebiliyor |

**Demo akışı (gerçek veriyle doğrulandı):** Yarışma Yöneticisi giriş yapar →
proje adı + kategori girip gerçek bir PDF yükler → analiz arka planda çalışır
(~2 sn) → Hakem giriş yapar, raporu açar, dört AI kontrolünü ve "AI Dördüncü
Göz" önerisini görür → kendi puanını verip AI önerisini ezer → Yarışmacı
kendi panelinde sonucunu, güçlü yönlerini ve gelişim önerilerini görür
(benzerlik/intihal verisi ve AI'nın önerdiği puan yarışmacıya **gösterilmez**)
→ Değerlendirme Yöneticisi tamamlanma oranını izler.

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

## Mahmut — frontend backend'e bağlandı (2026-08-24)

Arayüz artık gerçek API'yi kullanıyor. Tüm mock veri uygulamadan kaldırıldı
(mock sabitleri yalnızca test fixture'ı olarak duruyor).

**Eklenen API katmanı** — `frontend/src/lib/api/`:

| Dosya | İş |
|---|---|
| `client.ts` | Tek `fetch` sarmalayıcı: token enjeksiyonu, `ApiError`/`NetworkError` ayrımı, 401'de oturum düşürme |
| `types.ts` | Backend'in tel formatı (snake_case). Bileşenler bu tipleri hiç görmez |
| `mappers.ts` | Tel → arayüz tipi çevirisi |
| `index.ts` | Uç nokta fonksiyonları + `pollUntilAnalyzed` |
| `errors.ts` | Hata → Türkçe cümle |

**Çözülen üç şekil uyuşmazlığı:** isimlendirme (snake_case ↔ camelCase),
yuvalama (backend `suggested_score/outcome/rationale`'ı **düz** verir, arayüz
`suggestion: {score, outcome, rationale}` bekler), ve kimlik (backend
`category_id` verir, arayüz kategori **adı** gösterir — `/api/categories`'ten
haritalanıyor).

**Bağlanan ekranlar:** giriş (gerçek JWT), hakem panosu + rapor detayı +
nihai karar, rapor yükleme (gerçek multipart), yarışmacı sonuç paneli,
değerlendirme yöneticisi istatistikleri.

**Dikkat edilmesi gereken üç nokta:**

- **Analiz asenkron.** `POST /api/reports/upload` hemen `status: "pending"`
  döner; analiz arka planda çalışır (gerçek PDF'te ~2 sn). `pollUntilAnalyzed`
  bunu hallediyor — yükleme sonrası tek istek atmak boş sonuç verir.
- **`generateStaticParams` kaldırıldı.** Rapor detay sayfası MOCK_REPORTS
  kimliklerinden statik üretiliyordu, yani gerçek bir `RPT-2026-XXXXXX`
  kimliğiyle açıldığında 404 veriyordu. Artık dinamik. JWT localStorage'da
  durduğu için veri çekme **istemcide** olmak zorunda — sunucu bileşeni
  token'a erişemez.
- **CORS.** Backend yalnızca `http://localhost:3000`'e izin veriyor
  (`backend/main.py`). Frontend'i başka bir porttan servis ederseniz orayı da
  güncelleyin. Doğrulandı: `Authorization` başlığı için preflight geçiyor,
  yabancı origin 400 alıyor.

**Dil konusu kapandı:** senin arayüzü Türkçe'ye çevirmenle (`c348853`)
tutarsızlık bitti, tüm AI çıktıları da Türkçe.

### Hâlâ açık olan (senin kararın)

- `criteria-template-form.tsx` (Yarışma Yöneticisi'nin kriter tanımlama
  formu) hâlâ hiçbir yere kaydetmiyor — backend'de o şekle karşılık gelen bir
  uç nokta yok (`POST /api/criteria` farklı bir şema bekliyor: tek kriter,
  `category_id`+`title`+`max_score`). Bu MVP maddesi değil, o yüzden
  dokunmadım.
- Yarışmacının **kendi** raporunu yükleyebileceği bir ekran yok; yükleme
  yalnızca Yarışma Yöneticisi panelinde. Backend her iki role de izin
  veriyor (`RoleChecker(["COMPETITION_MANAGER", "COMPETITOR"])`).

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

# frontend (Mahmut)                -> 87 test
cd frontend && npm install && npm test
```

**Sistemi çalıştırmak (iki terminal gerekiyor):**

```bash
# 1. terminal — backend
cd backend
cp .env.local.example .env 2>/dev/null || true
python -c "import secrets; print(secrets.token_hex(32))"   # cikan degeri .env'e JWT_SECRET_KEY olarak yaz
python -m uvicorn main:app --reload --port 8000

# 2. terminal — frontend
cd frontend
cp .env.local.example .env.local          # NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev                                # http://localhost:3000
```

Frontend **3000** portunda çalışmalı: backend CORS'ta yalnızca
`http://localhost:3000` adresine izin veriyor.

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
| `frontend` (jest) | 87 başarılı, 0 başarısız |
| `frontend` (next build) | başarılı |
| Uçtan uca — API akışı | 40 başarılı, 0 başarısız |
| Uçtan uca — arayüz istek şekilleri (canlı backend) | 32 başarılı, 0 başarısız |

Uçtan uca testte doğrulananlar: 4 rolün girişi, gerçek PDF yükleme, dört
analizin veri tabanına yazılması, hakemin AI önerisini ezip nihai karar
vermesi, rol bazlı yetkilendirme (yarışmacı karar veremiyor, kendi raporundan
başkasını göremiyor), ve saldırgan vakalar: birebir kopyalanmış rapor %100
örtüşmeyle "Yüksek risk", yanlış kategori beyanı 10 puanla "Kritik", bozuk
dosya sistemi çökertmiyor.

İkinci uçtan uca test, arayüzün **ürettiği istek şekillerini** canlı
backend'e karşı doğruluyor. Bu ayrı bir test çünkü jest testleri `fetch`'i
taklit ediyor — yani arayüz kodunun şeklini sınar, backend'in o şekli kabul
edip etmediğini değil. Doğrulananlar: form-encoded giriş (`username` alan
adıyla), multipart yükleme, JSON karar gövdesi, CORS preflight, ve
`GET /api/reports`'un analiz edilmiş rapor varken artık 500 vermemesi.
