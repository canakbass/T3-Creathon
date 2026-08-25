# Kurulum ve Çalıştırma

Projeyi sıfırdan indiren birinin **hiçbir kod dosyasına dokunmadan**
çalıştırabilmesi için gereken her şey burada.

> Kodda mutlak yol (`/home/...`) yok — tüm yollar dosyanın kendi konumuna
> göre hesaplanıyor. Repoyu nereye klonlarsanız klonlayın çalışır.

**Gereksinimler:** Python 3.10+ ve Node.js 20+

---

## 1. Depoyu al

```bash
git clone https://github.com/canakbass/T3-Creathon.git
cd T3-Creathon
```

## 2. Python ortamı ve bağımlılıklar

```bash
python3 -m venv .venv
```

> **Aktivasyona hiç gerek yok.** Aşağıdaki komutlar sanal ortamın Python'ını
> doğrudan çağırıyor (`.venv/bin/python`). Bu, **bash / zsh / fish / Windows
> fark etmeksizin** çalışır ve "activate" kaynaklı hataları tamamen ortadan
> kaldırır.
>
> `source .venv/bin/activate` **fish kabuğunda ÇALIŞMAZ** — o bir bash
> betiğidir ve fish `case ... in` sözdizimini anlamaz. Fish kullanıyorsanız
> ya `source .venv/bin/activate.fish` yazın ya da (önerilen) aktivasyonu hiç
> yapmayın.

**Linux / macOS:**

```bash
.venv/bin/pip install -r backend/requirements.txt \
                      -r ai-doc-analysis/requirements.txt \
                      -r ai-scoring/requirements.txt
```

**Windows (PowerShell):**

```powershell
.venv\Scripts\pip install -r backend\requirements.txt -r ai-doc-analysis\requirements.txt -r ai-scoring\requirements.txt
```

## 3. Backend ayarları

Tek komut — `.env` dosyasını gizli anahtarı **doldurulmuş halde** oluşturur.
Elle hiçbir şey yapıştırmanız gerekmez:

**Linux / macOS (bash, zsh, fish — hepsinde çalışır):**

```bash
.venv/bin/python -c "import secrets,pathlib; p=pathlib.Path('backend/.env'); p.write_text('JWT_SECRET_KEY='+secrets.token_hex(32)+'\n'); print('olusturuldu:', p)"
```

**Windows (PowerShell):**

```powershell
.venv\Scripts\python -c "import secrets,pathlib; p=pathlib.Path('backend/.env'); p.write_text('JWT_SECRET_KEY='+secrets.token_hex(32)+'\n'); print('olusturuldu:', p)"
```

Kontrol edin — çıktı `JWT_SECRET_KEY=` + 64 karakter olmalı:

```bash
cat backend/.env
```

> **Sık yapılan hata:** `JWT_SECRET_KEY=` satırının sağına komutun kendisini
> (`python -c "import secrets..."`) yazmayın; komutu **çalıştırıp çıkan
> değeri** yazın. Yukarıdaki tek satırlık komut bunu zaten sizin için
> yapıyor.

LLM ayarları (Bölüm 6) isteğe bağlı — **boş bırakırsanız sistem tamamen
çalışır.**

> `backend/.env` `.gitignore`'da; anahtarlarınız repoya sızmaz.

## 4. Frontend ayarları

```bash
cp frontend/.env.local.example frontend/.env.local
cd frontend && npm install && cd ..
```

## 5. Çalıştır (iki terminal)

**1. terminal — backend** (repo kökünden, aktivasyon gerekmez):

```bash
cd backend
../.venv/bin/python -m uvicorn main:app --reload --port 8000
```

Windows (PowerShell):

```powershell
cd backend
..\.venv\Scripts\python -m uvicorn main:app --reload --port 8000
```

`Uvicorn running on http://127.0.0.1:8000` görmelisiniz.

**2. terminal — frontend** (repo kökünden):

```bash
cd frontend
npm run dev
```

Tarayıcıda **http://localhost:3000** açın.

> Frontend **3000** portunda olmalı: backend CORS'ta yalnızca
> `http://localhost:3000` adresine izin veriyor
> (`backend/main.py`). Başka bir port kullanacaksanız orayı da güncelleyin.

### Demo hesapları

İlk açılışta otomatik oluşur. Giriş ekranında rol kartına tıklamak, o rolün
hesabıyla **gerçek** bir giriş yapar (JWT alınır).

| Rol | E-posta | Şifre |
|---|---|---|
| Yarışma Yöneticisi | `manager@teknofest.org` | `password123` |
| Hakem | `referee@teknofest.org` | `password123` |
| Yarışmacı | `competitor@teknofest.org` | `password123` |
| Değerlendirme Yöneticisi | `evaluator@teknofest.org` | `password123` |

### Demo akışı

1. **Yarışma Yöneticisi** ile gir → proje adı + kategori yaz → bir PDF
   sürükle. Örnek raporlar hazır:
   `ai-doc-analysis/sample_reports/havacilikta_yz_ktr/reports/`
   Kategori olarak **AI & Machine Learning** seçin (bu raporlar havacılıkta
   yapay zeka raporları).
2. Analiz arka planda ~2 saniye sürer, ekranda "Analiz ediliyor…" görünür.
3. **Hakem** ile gir → raporu aç → dört AI kontrolünü ve "AI Dördüncü Göz"
   önerisini gör → kendi puanını ver (AI'nın önerisini değiştirebilirsin).
4. **Yarışmacı** ile gir → sonucunu, güçlü yönlerini ve gelişim önerilerini
   gör.
5. **Değerlendirme Yöneticisi** ile gir → tamamlanma oranını gör.

**Gösterilmesi güzel iki şey:** aynı PDF'i ikinci kez yükleyin — benzerlik
%100 çıkıp "Yüksek risk" bandına düşer. Ya da bir raporu yanlış kategoriyle
(örn. FinTech) yükleyin — kategori uyumu "Kritik" bandına düşer.

---

## 6. AI kriter değerlendirmesi: LLM isteğe bağlı

Sistem **varsayılan olarak yerel kural motoruyla** çalışır. Rapor içeriği
hiçbir yere gönderilmez. Demo için önerilen budur ve MVP madde 5 bu şekilde
tamamen karşılanır.

LLM açmak isterseniz `backend/.env` içinde:

```bash
AI_SCORING_LLM=gemini
GOOGLE_API_KEY=buraya-anahtariniz
AI_SCORING_LLM_ONAY=evet
```

Sonra `pip install google-genai` (Claude için `pip install anthropic` ve
`AI_SCORING_LLM=claude` + `ANTHROPIC_API_KEY`).

### ⚠️ Ücretsiz Gemini katmanı ile şartname çelişiyor

Google'ın [resmi koşulları](https://ai.google.dev/gemini-api/terms),
**ücretsiz** katman için: gönderdiğiniz içerik Google ürünlerini
geliştirmek için kullanılır, insan inceleyiciler okuyabilir, ve açıkça
*"Do not submit sensitive, confidential, or personal information to the
Unpaid Services."*

Creathon şartnamesi ise T3 Vakfı verilerinin üçüncü taraflarla
paylaşılmamasını şart koşuyor. **Ücretli** katmanda bu sorun yok
(*"Google doesn't use your prompts or responses to improve our products"*)
ve ayarlanacak bir gizlilik seçeneği **yoktur** — otomatiktir.

**Önemli tuzak:** "Ücretli" olmak için Google One AI Premium / Gemini
Advanced aboneliği **yetmez**. API anahtarınızın bağlı olduğu Google Cloud
projesine **Cloud Billing** bağlamanız gerekir. Hangi katmanda olduğunuzu
[aistudio.google.com](https://aistudio.google.com) → **Projects** →
**Billing Tier** sütunundan görebilirsiniz.

`AI_SCORING_LLM_ONAY=evet` tam da bu yüzden var: kimse bunu farkında olmadan
açmasın diye.

---

## 7. Testler

### Birim ve bileşen testleri

Repo kökünden, aktivasyon gerekmez:

```bash
.venv/bin/python ai-doc-analysis/tests/test_analyzer.py         #  32 test
.venv/bin/python ai-scoring/tests/test_scorer.py                #  95-102 test *
cd backend && ../.venv/bin/python -m pytest tests/ -q; cd ..    #  52 test
cd frontend && npm test; cd ..                                  # 105 test
```

\* `google-genai` kuruluysa 102, değilse 95 — Gemini'ye özel testler
opsiyonel SDK yokken atlanıyor.

**Dikkat:** `ai-doc-analysis` ve `ai-scoring` testleri pytest ile DEĞİL,
doğrudan çalıştırılıyor. Bunlar kendi `check()` fonksiyonlarını kullanan
betikler ve sonda `sys.exit()` çağırıyorlar; `pytest` ile toplanmaya
çalışılırsa `INTERNALERROR: SystemExit` verirler.

### Uçtan uca test (çalışan sunucuya karşı)

Birim testleri modülleri tek tek doğruluyor. Bu betik ise gerçek HTTP
üzerinden, dört rolün tamamıyla, bir yarışmanın baştan sona akışını
koşturuyor — demo öncesi "sistem gerçekten çalışıyor mu" sorusunun cevabı:

```bash
scripts/dev-backend.sh start
.venv/bin/python scripts/e2e-test.py      # 37 kontrol
scripts/dev-backend.sh stop
```

Kapsadıkları: rol seçimi zorunluluğu, yarışma kurulumu ve aşama geçişleri,
yarışmacı başvurusu, AI analizinin yarışmanın kriterleriyle puanlaması,
hakem ataması, yetki sınırları (atanmamış hakem raporu göremez/karar
veremez), karar doğrulama, veri bütünlüğü kuralları ve intihal tespiti.

---

## 8. Sorun giderme

| Belirti | Sebep / çözüm |
|---|---|
| Giriş ekranında "Backend'e ulaşılamadı" | Backend çalışmıyor. 1. terminali kontrol edin. |
| Girişte CORS hatası (tarayıcı konsolu) | Frontend 3000 dışında bir portta. `npm run dev -- -p 3000` |
| `JWT_SECRET_KEY ... RuntimeWarning` | `backend/.env` yok ya da değer boş. Bölüm 3. |
| Yükleme "Önce proje adını girin" diyor | Proje adı ve kategori zorunlu (backend öyle istiyor). |
| Analiz hep "Analiz ediliyor…" kalıyor | Backend terminalindeki hatayı okuyun. Bozuk PDF ise analiz yine biter, puan 0 döner. |
| Gemini "anahtar geçersiz" | Anahtar yanlış ya da AI Studio'dan alınmamış. Kural motoruna otomatik düşer, sistem çökmez. |
| Gemini "AI_SCORING_LLM_ONAY" uyarısı | Bilinçli bir kapı. Bölüm 6'yı okuyup `evet` yazın. |
| `python` bulunamadı (Windows) | `py -3 -m venv .venv` ile ortamı kurun. |
| **`activate (line 40): 'case' builtin not inside of switch block`** | **fish kabuğu** kullanıyorsunuz. `.venv/bin/activate` bir bash betiği. Ya `source .venv/bin/activate.fish` yazın ya da (önerilen) hiç aktive etmeyin — bu rehberdeki komutlar `.venv/bin/python`'ı doğrudan çağırıyor. |
| `No module named uvicorn` | Sistem Python'ı çalışıyor, venv'inki değil. `python` yerine `.venv/bin/python` (Windows: `.venv\Scripts\python`) kullanın. |
| `cd: The directory 'T3-Creathon' does not exist` | Zaten repo içindesiniz. Baştaki `cd T3-Creathon` satırını atlayın. |
| `RuntimeWarning: JWT_SECRET_KEY ... geri donuluyor` | `backend/.env` yok ya da boş. Bölüm 3'teki tek satırlık komutu çalıştırın. Sistem yine çalışır ama güvensiz bir varsayılan anahtar kullanır. |
