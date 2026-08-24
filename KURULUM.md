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
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -r backend/requirements.txt
pip install -r ai-doc-analysis/requirements.txt
pip install -r ai-scoring/requirements.txt
```

## 3. Backend ayarları

```bash
cp backend/.env.example backend/.env
python -c "import secrets; print(secrets.token_hex(32))"
```

Çıkan değeri `backend/.env` içindeki `JWT_SECRET_KEY=` satırının sağına
yapıştırın. **Diğer satırları boş bırakabilirsiniz** — sistem tamamen
çalışır (bkz. Bölüm 6).

> `backend/.env` `.gitignore`'da; anahtarlarınız repoya sızmaz.

## 4. Frontend ayarları

```bash
cp frontend/.env.local.example frontend/.env.local
cd frontend && npm install && cd ..
```

## 5. Çalıştır (iki terminal)

**1. terminal — backend:**

```bash
cd T3-Creathon
source .venv/bin/activate
cd backend
python -m uvicorn main:app --reload --port 8000
```

**2. terminal — frontend:**

```bash
cd T3-Creathon/frontend
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

```bash
source .venv/bin/activate

python ai-doc-analysis/tests/test_analyzer.py     # 32 test
python ai-scoring/tests/test_scorer.py            # 88 test
cd backend && python -m pytest tests/ -v && cd .. #  9 test
cd frontend && npm test && cd ..                  # 87 test
```

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
| `python` bulunamadı (Windows) | `py -3` deneyin. |
