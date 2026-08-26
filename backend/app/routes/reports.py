import contextlib
import json
import re
import os
import shutil
import uuid
import datetime
from pathlib import Path
import anyio.to_thread
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import FileResponse, Response
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import List, Optional

from ..database import get_db
from .. import models, schemas, auth, tenancy, dosya_adi
from ..services import ai
from ..services import storage
from . import competitions

router = APIRouter(prefix="/api/reports", tags=["Reports"])

UPLOAD_DIR = "uploads"
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)


def _dosyayi_diske_yaz(upload: UploadFile, hedef_yol: str) -> None:
    """Yuklenen dosyayi diske kopyalar. Bloklayan is - ayri bir is
    parcaciginda cagrilmali (bkz. upload_report)."""
    with open(hedef_yol, "wb") as buffer:
        shutil.copyfileobj(upload.file, buffer)

# Rapor kimligi deseni (RPT-2026-A1B2C3), istege bagli ".pdf" uzantisiyla.
_RAPOR_KIMLIGI = re.compile(r"\bRPT-\d{4}-[0-9A-Fa-f]{6,}(?:\.\w+)?")


def _benzerlik_bulgularini_maskele(bulgular):
    """Baska raporlarin KIMLIGINI yarismaciya gostermez.

    OLCULEN SIZINTI: benzerlik bulgusu "RPT-2026-06BBC8.pdf: %100.0 birebir
    ortusme" seklinde YAZILIYOR - yani karsilastirilan raporun kimligini
    metne basiyor (ai-scoring/similarity.py dosya adini kullaniyor, dosya adi
    da RPT-2026-XXXXXX.pdf). Bu bulgu yarismaciya da gidiyor: kendi
    raporunun analizinde BASKA BIR TAKIMIN basvuru kimligini okuyor.
    Dogrulandi: Zebot yarismacisi Glieser'in rapor kimligini gordu.

    Hakem icin bu bilgi GEREKLI (intihal suphesini takip etmesi lazim), o
    yuzden yalnizca COMPETITOR icin maskeleniyor. Ortusme YUZDESI duruyor -
    yarismacinin "raporum baska bir basvuruyla ortusuyor" bilgisini gormesi
    dogru; HANGI basvuru oldugunu bilmesi degil.
    """
    return [_RAPOR_KIMLIGI.sub("başka bir başvuru", b) for b in bulgular]


def _attach_analysis_results(report: models.Report, user=None) -> models.Report:
    """AiAnalysis kaydinin duz kolonlarini, API'nin dondugu ic ice `results`
    sozlugune cevirip nesneye ekler.

    NEDEN GEREKLI: schemas.AiAnalysisResponse `results: Dict[str, AiCheckResult]`
    alanini ZORUNLU tutuyor, ama models.AiAnalysis'te `results` diye bir
    kolon yok - veri tabaninda her kontrol dort ayri duz kolonda duruyor
    (language_template_score, ..._summary, ..._findings). Yani bu alanin
    her yanit oncesi elle uretilmesi sart.

    ONCEDEN NE KIRIKTI: bu donusum yalnizca get_report icinde yapiliyordu.
    list_reports (GET /api/reports) ayni ReportResponse semasini kullaniyor
    ama donusumu yapmiyordu; dolayisiyla veri tabaninda analiz edilmis TEK
    BIR rapor olur olmaz endpoint ResponseValidationError ile HTTP 500
    veriyordu ("Field required: ai_analysis.results"). Hakem panosunun ana
    listesi tam da bu endpoint'i kullaniyor. Mevcut testler yakalamamisti
    cunku analiz sonrasi liste endpoint'ini hic cagirmiyorlardi.

    Anahtar adlari camelCase: frontend/src/lib/ai-analysis.ts icindeki
    CHECK_KEYS ile birebir ayni olmali.
    """
    # Atama bilgisini yaniti hazirlarken ekliyoruz: yonetici paneli her rapor
    # icin ayri bir istek atmak zorunda kalmasin (N+1).
    # Takim adi da yanitla birlikte gidiyor: hakem/yonetici listede raporun
    # HANGI TAKIMA ait oldugunu gorebilmeli (arama da takim adiyla yapiliyor).
    setattr(report, "team_name", report.team.name if report.team else None)

    atama = report.assignment
    setattr(report, "assigned_referee_id", atama.referee_id if atama else None)
    setattr(
        report,
        "assigned_referee_email",
        atama.referee.email if atama and atama.referee else None,
    )

    analysis = report.ai_analysis
    if not analysis:
        return report

    def _findings(deger):
        if not deger:
            return []
        try:
            return json.loads(deger)
        except (json.JSONDecodeError, TypeError):
            # Bozuk JSON yuzunden tum endpoint dusmesin - hakem en azindan
            # puani ve ozeti gorsun.
            return ["Bulgular okunamadi (veri tabanindaki kayit bozuk)."]

    setattr(
        analysis,
        "results",
        {
            "languageTemplate": {
                "score": analysis.language_template_score,
                "summary": analysis.language_template_summary,
                "findings": _findings(analysis.language_template_findings),
            },
            "contentHeading": {
                "score": analysis.content_heading_score,
                "summary": analysis.content_heading_summary,
                "findings": _findings(analysis.content_heading_findings),
            },
            "categoryMatch": {
                "score": analysis.category_match_score,
                "summary": analysis.category_match_summary,
                "findings": _findings(analysis.category_match_findings),
            },
            "similarity": {
                "score": analysis.similarity_score,
                "summary": analysis.similarity_summary,
                # Yarismaci baska basvurularin KIMLIGINI gormemeli.
                "findings": (
                    _benzerlik_bulgularini_maskele(_findings(analysis.similarity_findings))
                    if getattr(user, "active_role", None) == "COMPETITOR"
                    else _findings(analysis.similarity_findings)
                ),
            },
        },
    )
    return report


def _benzerligi_isaretle(
    benzerlik: dict, toplam: int, okunan: int, atlanan: list
) -> dict:
    """Okunamayan karsilastirma raporlarini benzerlik sonucuna yansitir.

    Iki ayri durum var ve hakem icin anlamlari cok farkli:

      * HICBIRI okunamadi -> karsilastirma HIC yapilmadi. Modulun urettigi
        "bu sistemdeki ilk basvuru" ozeti bu durumda yanlis; ozetin kendisi
        degistiriliyor.
      * BAZILARI okunamadi -> karsilastirma eksik. Puan gecerli ama eksik
        bir kumeye dayaniyor; puana dokunmadan uyari ekleniyor.

    Puan iki durumda da YUKSELTILMIYOR: benzerlik puani "ne kadar kotu"
    olcusu, uydurma bir ceza puani hakemi baska yone yanıltirdi.
    """
    if okunan == 0:
        return {
            "score": benzerlik["score"],
            "summary": (
                f"Benzerlik karsilastirmasi YAPILAMADI: {toplam} rapor vardi, "
                "hicbiri okunamadi."
            ),
            "findings": [
                "Bu bir sistem hatasidir, ozgunluk kanitı DEGILDIR.",
                "Rapor elle intihal kontrolunden gecirilmeli.",
                *[f"Okunamayan rapor - {a}" for a in atlanan[:5]],
            ],
        }
    return {
        **benzerlik,
        "findings": [
            *benzerlik["findings"],
            f"UYARI: karsilastirma EKSIK - {toplam} rapordan {toplam - okunan} tanesi "
            "okunamadi. Gercek ortusme bu puandan yuksek olabilir.",
            *[f"Okunamayan rapor - {a}" for a in atlanan[:5]],
        ],
    }


def run_background_analysis(report_id: str, file_path: str, db: Session):
    try:
        # Get category information
        categories = db.query(models.Category).all()
        # description de geciyoruz: docs/scoring-rules.json'da anahtar kelime
        # tanimi olmayan (Yarisma Yoneticisi'nin sonradan ekledigi) bir
        # kategori icin ai-scoring, kategori adi+aciklamasi uzerinden
        # karakter n-gram benzerligine dusuyor - aciklama olmadan o yedek
        # yontemin elinde neredeyse hic sinyal kalmaz.
        categories_dict = [
            {"id": c.id, "name": c.name, "description": c.description} for c in categories
        ]
        
        # Benzerlik kontrolu icin daha once yuklenmis raporlar.
        #
        # DIKKAT: eskiden burada `os.path.exists(r.file_path)` ile filtre
        # vardi. Supabase Storage devreye girince file_path bir "sb://"
        # anahtari oluyor ve os.path.exists HER ZAMAN False donerdi - liste
        # sessizce bosalir, intihal kontrolu hicbir hata vermeden "benzer
        # rapor yok" demeye baslardi. Bu yuzden storage.local_path() ile
        # her nesne gecici bir yerel dosyaya indiriliyor.
        report = db.query(models.Report).filter(models.Report.id == report_id).first()

        karsilastirma_sorgusu = db.query(models.Report).filter(
            models.Report.id != report_id
        )
        # KURUMLAR ARASI KARSILASTIRMA YOK.
        #
        # Iki sebep: (1) GIZLILIK - bulgu metni karsilastirilan raporun
        # kimligini tasiyor; kurumlar arasi havuz, bir kurumun basvuru
        # kimliklerini digerine sizdirir. Sartname de "erisilen T3 Vakfi
        # verileri ucuncu taraflarla paylasilamaz" diyor. (2) DOGRULUK -
        # esikler tek bir yarismanin 34 gercek raporunda kalibre edildi;
        # havuza baska kurumlarin farkli sablonlu belgeleri karisinca taban
        # oran degisir ve hakeme gosterilen referans cumlesi yalan olur.
        # Ayrica hakem, gosteremedigi bir belgeye dayanan intihal suclamasi
        # yapamaz - islem yapilabilir bir bulgu degildir.
        # KOSULSUZ: onceden `if report.organization_id:` vardi, yani kurumu
        # BOS bir rapor her kurumun her raporuyla karsilastiriliyordu - ve
        # bulgu metni karsilastirilan raporun kimligini tasidigi icin bu,
        # kurumsuz tek bir kayitla butun sistemin basvuru kimliklerini
        # okumak demekti. Kurumsuz rapor artik kurumsuz havuzda kaliyor.
        karsilastirma_sorgusu = karsilastirma_sorgusu.filter(
            models.Report.organization_id == report.organization_id
        )
        # AYNI TAKIMIN kendi raporlari karsilastirmadan CIKARILIYOR.
        #
        # Sartname madde 5: "BASVURULAR ARASINDA yuksek benzerlik gosteren
        # icerikler tespit edilir." Bir takimin iki raporu iki AYRI BASVURU
        # degil, ayni basvurunun iki asamasidir - ustelik teknik sartname
        # madde 5 ikisini de ZORUNLU kiliyor: "On Tasarim Raporu yarisma
        # katilimi ve Final Tasarim Raporu puanlandirma surecinde
        # kullanilacagi icin iki raporun da teslim edilmesi sarttir."
        #
        # OLCULDU: bu filtre olmadan takimin FTR'si kendi OTR'sine karsi 100
        # benzerlik puani aliyor ve "Yuksek oranda birebir metin ortusmesi"
        # olarak isaretleniyordu. Yani sartnamenin zorunlu tuttugu davranis
        # intihal sayiliyordu.
        kendi_rapor_sayisi = 0
        if report.team_id:
            kendi_rapor_sayisi = karsilastirma_sorgusu.filter(
                models.Report.team_id == report.team_id
            ).count()
            karsilastirma_sorgusu = karsilastirma_sorgusu.filter(
                (models.Report.team_id.is_(None))
                | (models.Report.team_id != report.team_id)
            )
        other_reports = karsilastirma_sorgusu.all()

        # Kriterler: rapor bir YARISMAYA bagliysa o yarismanin kriterleri
        # (agirliklariyla birlikte) kullaniliyor. Degilse eski kategori
        # bazli kriter tablosuna dusuluyor.
        if report.competition and report.competition.criteria_list:
            criteria_dict = [
                {"id": k.id, "title": k.title, "weight": k.weight, "max_score": 100}
                for k in sorted(report.competition.criteria_list, key=lambda k: k.display_order)
            ]
        else:
            criteria = db.query(models.Criteria).filter(
                models.Criteria.category_id == report.category_id
            ).all()
            criteria_dict = [
                {"id": cr.id, "title": cr.title, "max_score": cr.max_score} for cr in criteria
            ]

        # Sablon kurallari: yarisma kendi kurallarini tanimladiysa ONLAR
        # kullaniliyor. Onceden bu degerler tum sistem icin
        # docs/mvp-rules.json'da SABITTI; artik her yarisma kendi zorunlu
        # basliklarini, dilini ve sayfa sinirini belirleyebiliyor.
        rules = competitions.yarismanin_kurallari(report.competition)

        # Run AI analysis.
        # declared_category_id: yarismacinin yukleme sirasinda sectigi
        # kategori. Bu olmadan kategori kontrolu yalnizca "en uygun kategori
        # hangisi" diyebiliyordu; asil sorulmasi gereken soru "rapor BEYAN
        # EDILEN kategoriye ait mi" oldugu icin bu bilgiyi da geciyoruz.
        # Analiz edilecek raporun ve karsilastirilacak tum raporlarin YEREL
        # yollari. ExitStack, hepsini tek blokta acip cikista temizliyor.
        with contextlib.ExitStack() as stack:
            yerel_hedef = stack.enter_context(storage.local_path(file_path))

            existing_paths = []
            atlanan = []
            for r in other_reports:
                # Yerel referanslarda dosya diskte yoksa atliyoruz (eski
                # davranis buydu); uzak referanslarda indirme denenip
                # basarisiz olursa asagidaki except yakaliyor.
                if not storage.is_remote(r.file_path) and not os.path.exists(r.file_path):
                    atlanan.append(f"{r.id}: dosya bulunamadi")
                    continue
                try:
                    existing_paths.append(stack.enter_context(storage.local_path(r.file_path)))
                except Exception as exc:
                    # Tek bir eski rapor okunamazsa tum analiz dusmemeli;
                    # o rapor karsilastirmadan cikariliyor.
                    atlanan.append(f"{r.id}: {exc}")
                    print(f"Karsilastirilacak rapor okunamadi ({r.id}): {exc}")

            analysis_data = ai.run_full_analysis(
                file_path=yerel_hedef,
                db_categories=categories_dict,
                existing_files=existing_paths,
                criteria_list=criteria_dict,
                declared_category_id=report.category_id,
                rules=rules,
            )

        # Benzerlik sonucunu DURUSTLESTIR.
        #
        # ai-scoring yalnizca KAC raporla karsilastirdigini bilir, kac rapor
        # OLMASI GEREKTIGINI bilmez. Karsilastirilacak rapor vardi ama hicbiri
        # okunamadiysa modul "Karsilastirilacak baska rapor yok - bu, sistemdeki
        # ilk basvuru" diyor. Hakemin ekranda okudugu bu cumle o durumda YANLIS
        # olur ve intihal kontrolunun hic calismadigini gizler - bir intihal
        # kontrolunun yapabilecegi en kotu hata budur.
        if atlanan:
            analysis_data["similarity"] = _benzerligi_isaretle(
                analysis_data["similarity"], len(other_reports), len(existing_paths), atlanan
            )

        # Neyin karsilastirilmadigi da hakemin bilgisi: "%0 benzerlik" ile
        # "kendi takiminin raporu haric %0 benzerlik" ayni sey degil.
        if kendi_rapor_sayisi:
            analysis_data["similarity"] = {
                **analysis_data["similarity"],
                "findings": [
                    *analysis_data["similarity"]["findings"],
                    f"Aynı takımın {kendi_rapor_sayisi} raporu karşılaştırma dışı "
                    "bırakıldı: bir takımın kendi başvurusunun diğer aşaması "
                    "(Ön Tasarım / Final Tasarım) intihal değildir.",
                ],
            }

        # Save analysis results
        db_analysis = models.AiAnalysis(
            id=str(uuid.uuid4()),
            report_id=report_id,
            analyzed_at=datetime.datetime.now(datetime.UTC).replace(tzinfo=None),
            engine_version="eval-engine v1.0",
            suggested_outcome=analysis_data["suggested_outcome"],
            suggested_score=analysis_data["suggested_score"],
            rationale=analysis_data["rationale"],
            
            language_template_score=analysis_data["language_template"]["score"],
            language_template_summary=analysis_data["language_template"]["summary"],
            language_template_findings=json.dumps(analysis_data["language_template"]["findings"]),
            
            content_heading_score=analysis_data["content_heading"]["score"],
            content_heading_summary=analysis_data["content_heading"]["summary"],
            content_heading_findings=json.dumps(analysis_data["content_heading"]["findings"]),
            
            category_match_score=analysis_data["category_match"]["score"],
            category_match_summary=analysis_data["category_match"]["summary"],
            category_match_findings=json.dumps(analysis_data["category_match"]["findings"]),
            
            similarity_score=analysis_data["similarity"]["score"],
            similarity_summary=analysis_data["similarity"]["summary"],
            similarity_findings=json.dumps(analysis_data["similarity"]["findings"])
        )
        
        db.add(db_analysis)
        
        # Update report status to analyzed
        report.status = "analyzed"
        db.commit()
    except Exception as e:
        print(f"Error analyzing report {report_id}: {str(e)}")
        # In a real app we'd log this, and set report status to error
        report = db.query(models.Report).filter(models.Report.id == report_id).first()
        if report:
            report.status = "error"
            db.commit()


def _epostalari_ayikla(ham) -> list:
    """Virgul/noktali virgul/bosluk/satir ile ayrilmis e-postalari ayiklar.

    Gercek kullanimda liste Excel'den ya da bir e-postadan kopyalaniyor;
    ayirici her zaman ayni olmuyor. Tekillestirme SIRA KORUNARAK yapiliyor -
    ilk yazilan uye takim kaptani sayiliyor.
    """
    if not ham:
        return []
    parcalar = [p for p in re.split(r"[\s,;]+", ham) if p]
    sonuc = []
    gorulen = set()
    for parca in parcalar:
        adres = dosya_adi.eposta_normalle(parca)
        # "@" ve nokta yoksa e-posta degil; sessizce atmak yerine hata
        # veriyoruz, cunku yonetici yanlis yazdigini bilmeli.
        if "@" not in adres or "." not in adres.split("@", 1)[1]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Gecerli bir e-posta degil: {parca}",
            )
        if adres not in gorulen:
            gorulen.add(adres)
            sonuc.append(adres)
    return sonuc


def _takimi_bul_ya_da_ac(db: Session, epostalar: list, current_user) -> models.Team:
    """E-posta kumesinden takimi bulur; yoksa acar.

    ANAHTAR SIRADAN BAGIMSIZ (dosya_adi.takim_anahtari): dosya adinda uye
    sirasi degisirse ayni ekip icin IKINCI bir takim acilmasi, o ekibin
    raporlarinin iki takima dagilmasi demekti - ve uyeler birbirinin
    sonucunu goremezdi.

    TAKIM OLUSTURMA BIZIM ISIMIZ DEGIL demistik; bu onunla celismiyor.
    Burada bir takim YONETMIYORUZ, teslim edilen dosyadan gelen veriyi
    KAYDEDIYORUZ. Gercek kayit hala KYS'de; `external_ref` ileride oradan
    gelen kimlikle eslestirmek icin duruyor.
    """
    kurum = tenancy.aktif_kurum(current_user)
    anahtar = dosya_adi.takim_anahtari(epostalar)

    takim = (
        db.query(models.Team)
        .filter(
            models.Team.external_ref == anahtar,
            models.Team.organization_id == kurum,
        )
        .first()
    )
    if takim is not None:
        return takim

    takim = models.Team(
        id=str(uuid.uuid4()),
        name=dosya_adi.takim_adi_uret(epostalar),
        external_ref=anahtar,
        organization_id=kurum,
    )
    db.add(takim)
    db.flush()

    for sira, adres in enumerate(epostalar):
        db.add(
            models.TeamMember(
                id=str(uuid.uuid4()),
                team_id=takim.id,
                email=adres,
                # HESABI VARSA HEMEN BAGLANIYOR - ama yalnizca e-postasi
                # DOGRULANMISSA. Dogrulanmamis bir adresi baglamak, "bir
                # takim uyesinin e-postasini ilk kaydettiren kisi o takimin
                # sonuclarini gorur" acigini geri acardi.
                user_id=_dogrulanmis_kullanici_id(db, adres),
                role="kaptan" if sira == 0 else "uye",
            )
        )
    db.flush()
    return takim


def _dogrulanmis_kullanici_id(db: Session, adres: str):
    """Bu adrese ait DOGRULANMIS hesabin kimligi (yoksa None).

    Dogrulama sarti pazarlik konusu degil: uyelik e-postaya bagli oldugu
    icin "bu adresin sahibi misin" sorusunun cevabi, o takimin butun
    sonuclarini gormeye yetiyor.
    """
    kullanici = (
        db.query(models.User)
        .filter(func.lower(models.User.email) == adres)
        .first()
    )
    if kullanici is None or not kullanici.email_verified:
        return None
    return kullanici.id


@router.post("/upload", response_model=schemas.ReportResponse, status_code=status.HTTP_201_CREATED)
async def upload_report(
    background_tasks: BackgroundTasks,
    # Proje adi ARTIK ZORUNLU DEGIL: verilmezse dosya adindan turetiliyor.
    # Toplu aktarimda yoneticinin her dosya icin ad yazmasi gereksiz bir
    # engeldi ve pratikte adi dosyanin kendisi tasiyor.
    project_name: str = Form(None),
    category_id: str = Form(None),
    competition_id: str = Form(None),
    team_id: str = Form(None),
    # TAKIM UYELERI - virgul/bosluk/satir ile ayrilmis e-postalar.
    #
    # Kullanicinin istegi: "yonetici raporu teslim eden kisilerin mailini
    # girsin ya da GONDERILEN DOSYALAR UZERINDEN isimlendirilebilsin".
    # Verilmezse dosya adindan cikariliyor; ikisi de yoksa `team_id`ye
    # dusuluyor.
    member_emails: str = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        auth.RoleChecker(list(models.YONETICI_ROLLERI))
    )
):
    """Raporu SISTEME AKTARIR ve AI analizini arka planda baslatir.

    YALNIZCA YONETICI AKTARABILIR. Yarismacinin yukleme yetkisi KALDIRILDI.

    NEDEN: sartname AKIS 01 (Yarisma Yoneticisi) "raporlari sisteme aktarir"
    diyor; AKIS 03 (Yarismaci) ise "Degerlendirme tamamlanir -> sonucunu
    goruntuler -> guclu ve gelisime acik yonlerini inceler -> onerileri
    gorur" - yani yarismaci akisinda YUKLEME ADIMI YOK. Yarismaci sistemde
    yalnizca SONUC GORUNTULEYEN taraf.

    Gercek hayatta da boyle: raporlar TEKNOFEST'in kendi sistemine
    (KYS / t3kys.com) teslim ediliyor, buraya degil. Bizim sistem o raporlari
    degerlendiren yardimci katman; toplama noktasi degil.

    `competition_id` verilirse yarismanin asamasi kontrol edilir ve kategori
    yarismadan alinir. Rapor hangi TAKIMA ait oldugu `team_id` ile
    belirtilir - sonucu kimin gorecegi buradan cikiyor.
    """
    # UC YABANCI ANAHTAR DA KAPIDAN GECIYOR.
    #
    # ONCEDEN GECMIYORDU ve tek guvence "yonetici misin"di - "BURADA yonetici
    # misin" degil. Olculdu: CBU yoneticisi `team_id=team-glieser` gonderip
    # T3 kurumuna rapor ENJEKTE etti (HTTP 201), rapor T3'un listesinde
    # gorundu ve yanit T3'un takim adini ("Glieser") geri verdi. Bunun uc
    # ayri sonucu vardi: (a) yabanci kurumun degerlendirme kuyruguna belge
    # sokmak - o kurumun kendi hakemlerine atanir, (b) yabanci kurumun
    # INTIHAL HAVUZUNA girmek, yani bir belgenin kopyasini yukleyip o
    # kurumun gercek basvurularini intihalci gostermek, (c) 201/404 farkiyla
    # yabanci takim ve yarisma kimliklerini saymak.
    competition = None
    if competition_id:
        competition = tenancy.yarisma_getir_yetkiliyse(competition_id, current_user, db)

        # ASAMA KONTROLU YOK - bilincli.
        #
        # Onceden yalnizca COMPETITOR icin "yarisma 'open' degilse yukleyemez"
        # kurali vardi; yarismaci artik hic yukleyemedigi icin o dal olu kod
        # oldu. Yoneticiye asama kisiti KOYMUYORUZ: gercek akista raporlar
        # basvuru kapandiktan SONRA toplu aktariliyor (KYS'den gelen dosyalar
        # elden gecirilip sisteme yukleniyor), yani 'closed' asamasinda
        # aktarim NORMAL durum. Kisit koymak, sistemin asil kullanim seklini
        # engellerdi.
        #
        # Kategori yarismadan geliyor - ayrica secilmesine gerek yok.
        category_id = competition.category_id

    if not category_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="category_id ya da competition_id verilmeli.",
        )

    # --- Raporun SAHIBI takim -------------------------------------------
    #
    # Sartname AKIS 01, yarisma yoneticisinin "raporlari sisteme aktardigini"
    # soyluyor. Bu durumda `submitted_by_id` yoneticidir ve raporun sahibi
    # DEGILDIR. Onceden sonucu kimin gordugu yukleyene bakiyordu; sonuc olarak
    # yoneticinin aktardigi bir raporun sonucunu HICBIR yarismaci goremiyordu.
    # Sahiplik artik takimdan geliyor.
    # --- Raporun SAHIBI takim -------------------------------------------
    #
    # RAPOR MUTLAKA BIR TAKIMA BAGLANIR. Sahipsiz bir rapor sisteme girer,
    # analiz edilir, hakem karar verir ve sonucunu HICBIR yarismaci goremez -
    # sartname AKIS 03 ("yarismaci sonucunu goruntuler") karsilanmaz.
    #
    # UC KAYNAK, SU SIRAYLA:
    #   1. `member_emails` - yonetici acikca yazdiysa en guvenilir kaynak
    #   2. dosya adi        - "232805068@ogr.cbu.edu.tr_can@gmail.com.pdf"
    #   3. `team_id`        - mevcut bir takima dogrudan baglama
    #
    # Takim kimligi ARTIK ZORUNLU DEGIL: yoneticinin elinde olmayan bir
    # bilgiydi. Elinde gercekten olan sey teslim edilen dosyalar ve o
    # dosyalari kimin gonderdigi.
    cozum = None
    if not team_id:
        epostalar = _epostalari_ayikla(member_emails)
        dosya_uyarilari = []
        if not epostalar:
            try:
                cozum = dosya_adi.cozumle(file.filename or "")
            except dosya_adi.DosyaAdiHatasi as hata:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail=str(hata)
                ) from hata
            epostalar = cozum["epostalar"]
            dosya_uyarilari = cozum["uyarilar"]
        if not epostalar:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Rapor hangi takima ait? Dosya adinda e-posta bulunamadi. "
                    "Takim uyelerinin e-postalarini girin (orn. "
                    "ogrenci@okul.edu.tr, arkadas@okul.edu.tr) ya da dosyayi "
                    "e-postalarla adlandirin."
                ),
            )
        takim = _takimi_bul_ya_da_ac(db, epostalar, current_user)
        if dosya_uyarilari:
            # Uyarilar sessizce kaybolmasin: yonetici dosya adindan cikan
            # belirsizligi (orn. "ZEKA_ali@..." yerel kismi) gormeli.
            for u in dosya_uyarilari:
                print(f"[yukleme uyarisi] {file.filename}: {u}")
    else:
        takim = db.query(models.Team).filter(models.Team.id == team_id).first()
        # "Yok" ile "baska kurumun" AYNI cevabi veriyor: ayirt edilebilseydi
        # yonetici rastgele kimlik deneyerek baska kurumlarin takim listesini
        # cikarabilirdi (olculdu: var olmayan takim 404, A kurumunun takimi
        # 201 + takim adi).
        if takim is None or not tenancy.ayni_kurum_mu(takim, current_user):
            raise HTTPException(status_code=404, detail="Takim bulunamadi.")

    # Proje adi verilmediyse dosya adindan turetiliyor.
    #
    # DOSYA ADINA DUSMUYORUZ: dosya adi cogu zaman SADECE e-postalardan
    # olusuyor ("ali@x.com_veli@y.com.pdf") ve onu proje adi olarak yazmak,
    # kullanicinin sikayet ettigi ekrani birebir uretirdi - listede proje adi
    # sutununda e-posta adresleri gorunuyordu.
    #
    # Bunun yerine TAKIM ADINA dusuyoruz: adi olmayan bir raporu listede
    # ayirt etmenin en dogru yolu kimin gonderdigi. "Isimsiz Rapor" gibi bir
    # sey UYDURMUYORUZ - o da butun adsiz raporlari ayirt edilemez kilardi.
    if not (project_name or "").strip():
        if cozum is None:
            try:
                cozum = dosya_adi.cozumle(file.filename or "")
            except dosya_adi.DosyaAdiHatasi:
                cozum = {"proje_adi": None}
        project_name = cozum.get("proje_adi") or (takim.name if takim else None) or "Rapor"

    category = db.query(models.Category).filter(models.Category.id == category_id).first()
    if category is not None and not tenancy.ayni_kurum_mu(category, current_user):
        category = None
    if not category:
        raise HTTPException(status_code=404, detail="Kategori bulunamadi.")

    # Check file extension
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in [".pdf", ".doc", ".docx"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Desteklenmeyen dosya turu. PDF ya da Word belgesi yukleyin."
        )
        
    report_id = f"RPT-2026-{str(uuid.uuid4())[:6].upper()}"
    depo_adi = f"{report_id}{ext}"
    # Once gecici bir dosyaya yaziyoruz; storage.save() onu kalici depoya
    # (yerel disk ya da Supabase Storage) tasiyip nihai referansi donuyor.
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    gecici_yol = os.path.join(UPLOAD_DIR, f".tmp-{depo_adi}")

    # Dosyayi diske YAZARKEN olay dongusunu (event loop) bloklamiyoruz.
    #
    # Onceki hali `with open(...) as buffer: buffer.write(await file.read())`
    # seklindeydi. Iki sorunu vardi (SonarQube: "Use an asynchronous file API
    # instead of synchronous open() in this async function"):
    #   1. open()/write() bloklayan sistem cagrilaridir. Bu fonksiyon
    #      `async def` oldugu icin olay dongusunun kendi is parcaciginda
    #      calisiyordu - yani buyuk bir PDF yazilirken sunucu O ANDA baska
    #      HICBIR istege yanit veremiyordu.
    #   2. `await file.read()` dosyanin TAMAMINI bellege aliyordu.
    #
    # anyio.to_thread.run_sync bloklayan isi ayri bir is parcacigina
    # tasiyor; shutil.copyfileobj ise parca parca kopyaladigi icin dosya
    # bellege sigmak zorunda kalmiyor. anyio yeni bir bagimlilik degil -
    # starlette (dolayisiyla FastAPI) zaten ona bagli.
    await anyio.to_thread.run_sync(_dosyayi_diske_yaz, file, gecici_yol)

    # Kalici depoya tasi. Supabase yapilandirilmissa "sb://..." referansi,
    # degilse "uploads/..." yolu doner - cagiran kod ikisini de ayni
    # sekilde kullaniyor (bkz. app/services/storage.py).
    try:
        file_path = await anyio.to_thread.run_sync(storage.save, gecici_yol, depo_adi)
    except Exception as exc:
        # Gecici dosya ortada kalmasin.
        if os.path.exists(gecici_yol):
            os.remove(gecici_yol)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Rapor dosyasi kaydedilemedi: {exc}",
        )

    # Create Report record (status = pending)
    db_report = models.Report(
        id=report_id,
        project_name=project_name,
        category_id=category_id,
        status="pending",
        file_path=file_path,
        # Diskteki ad RPT-2026-XXXXXX.pdf seklinde normalize ediliyor;
        # indirme sirasinda kullaniciya kendi verdigi adi gosterebilmek
        # icin orijinali de sakliyoruz.
        original_filename=file.filename,
        competition_id=competition.id if competition else None,
        submitted_by_id=current_user.id,
        team_id=takim.id if takim else None,
        # Kurum YUKLEYENIN TOKENINDEN geliyor, govdeden secilen takimdan
        # DEGIL. Takimdan turetildiginde, govdeye yabanci bir takim kimligi
        # yazmak raporu O KURUMDA dogurmaya yetiyordu. Kapi artik takimi da
        # dogruluyor - ama kaydin kurumunu yine de saldirganin sectigi bir
        # nesneden almak, kapinin ilerideki her degisikliginde bu delige
        # geri donme riski demek.
        organization_id=tenancy.aktif_kurum(current_user) or (
            takim.organization_id if takim else None
        ),
        submission_date=datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
    )
    
    db.add(db_report)
    db.commit()
    db.refresh(db_report)
    
    # Run analysis in background
    background_tasks.add_task(run_background_analysis, report_id, file_path, db)

    # _attach_analysis_results uzerinden donuyoruz: team_name ve atama alanlari
    # yanitta dolu olsun. Duz `return db_report` bu alanlari bos birakiyordu.
    return _attach_analysis_results(db_report, current_user)


def _rol_yoksa_reddet(user: models.User) -> str:
    """Aktif rolu dondurur; secilmemisse istegi reddeder.

    NEDEN VAR: rol bazli filtreler `if rol == ...` zincirleriydi ve rolu
    olmayan token hicbir dala girmiyordu - yani filtre SESSIZCE devre disi
    kaliyordu. Cok-rollu bir kullanici giris yapip henuz rol secmemisken
    /api/reports tum yarismacilarin raporlarini donduruyordu. Eksik rol
    artik "filtre yok" degil, "erisim yok" anlamina geliyor.
    """
    aktif = getattr(user, "active_role", None)
    if aktif is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Rol secilmedi. /api/auth/select-role ile rolunuzu secin.",
        )
    return aktif


def _rapora_erisebilir_mi(report: models.Report, user: models.User) -> bool:
    """Bu kullanici bu rapora erisebilir mi.

    - Yarisma/Degerlendirme Yoneticisi: hepsi
    - Yarismaci: yalnizca kendi raporu
    - Hakem: yalnizca kendisine ATANMIS rapor
    - Rol secilmemis: hicbiri

    TEK YETKI KAPISI: rapora dokunan her uc nokta (detay, dosya, gerekce
    taslagi, karar) bunu cagirmali. Listeleme icin ayni kurallarin SQL
    karsiligi _erisim_filtresi'nde - ikisi birlikte degismeli.
    """
    # KURUM ON-EK VE-KAPISI - rol dallarindan ONCE.
    #
    # NEDEN ROL DALLARININ ICINDE DEGIL: yonetici dali `return True` ile
    # filtresiz donuyor. Kurum kontrolu dallarin icine yazilirsa TAM O SATIR
    # unutulur ve bir kurumun yoneticisi her kurumun her raporunu gorur.
    # On-ek olarak yazilinca, yarin eklenecek yeni bir rol dali da varsayilan
    # olarak kurum-kapali dogar (fail-closed).
    if not _ayni_kurum_mu(report, user):
        return False

    aktif = getattr(user, "active_role", None)
    if aktif in models.YONETICI_ROLLERI:
        return True
    if aktif == "COMPETITOR":
        return _yarismacinin_raporu_mu(report, user)
    if aktif == "REFEREE":
        return report.assignment is not None and report.assignment.referee_id == user.id
    return False


def _ayni_kurum_mu(report: models.Report, user: models.User) -> bool:
    """Rapor, istegin yapildigi kuruma mi ait.

    TEK TANIMA DEVREDIYOR (tenancy.ayni_kurum_mu). Onceden burada AYRI bir
    kopya vardi ve ikisi ayrismisti: bu kopya `KATI_KURUM` bayragini hic
    sormuyordu, yani bayrak acildiginda en hassas modul kapanmiyor ama
    kapandigi saniliyordu. Iki yerde yazilan bir kural, zamanla iki farkli
    kural demek.
    """
    return tenancy.ayni_kurum_mu(report, user)


def _yarismacinin_raporu_mu(report: models.Report, user: models.User) -> bool:
    """Bu rapor bu yarismacinin (ya da takiminin) raporu mu.

    TEKNOFEST'te basvuru birimi TAKIM, kisi degil. Takim arkadasi kendi
    takiminin sonucunu gorebilmeli; baska bir takimin sonucunu ASLA.

    Takimi olan raporda YALNIZCA takim uyeligine bakiyoruz - yukleyene
    DEGIL. Bunun iki sebebi var:
      * Sartname AKIS 01: raporu yarisma yoneticisi de aktarabiliyor. O
        durumda `submitted_by_id` yoneticidir ve raporun sahibi degildir.
      * Takimdan ayrilmis bir uye, bir zamanlar yuklemis olmasi sayesinde
        erisimini surdurmemeli.
    Takimi OLMAYAN raporda eski davranis geciyor (yalnizca yukleyen);
    yarisma akisi devreye girmeden once yuklenmis kayitlar boyle.
    """
    if report.team_id:
        return report.team is not None and user.id in report.team.member_ids
    return report.submitted_by_id == user.id


def _erisim_filtresi(query, user: models.User, db: Session):
    """_rapora_erisebilir_mi kurallarinin sorgu karsiligi.

    Ikisi ayni kurallari anlatmak ZORUNDA: liste bir raporu gosterip
    detayi 403 verirse arayuz tutarsiz gorunur, tersi durumda ise liste
    gormemesi gereken raporu sizdirir.
    """
    aktif = _rol_yoksa_reddet(user)

    # KURUM ON-EKI - rol dallarindan ONCE ve HEPSININ USTUNE.
    # Yonetici dali `return query` ile filtresiz donuyor; kurum kosulu o
    # dalin icine yazilirsa tek satirlik bir unutma sistemi tek kurumluga
    # geri dondurur ve hicbir mevcut test bunu yakalamaz.
    # Tek tanima devrediyor: kurumu OLMAYAN bir token artik hicbir sey
    # gormuyor. Onceden `if aktif_kurum is not None` filtreyi TAMAMEN
    # atliyordu - yani kurum secmemek, kurum secmekten DAHA COK yetki
    # veriyordu. Olculdu: org iddiasi olmayan imzali bir token 12 raporun
    # hepsini, baska kurumun yarismasini ve kategorilerini goruyordu.
    query = tenancy.kurum_filtresi(query, models.Report, user)

    if aktif in models.YONETICI_ROLLERI:
        return query
    if aktif == "COMPETITOR":
        takim_kimlikleri = [
            m.team_id
            for m in db.query(models.TeamMember)
            .filter(models.TeamMember.user_id == user.id)
            .all()
        ]
        # Kural _yarismacinin_raporu_mu ile BIREBIR ayni:
        #   * takimi OLAN rapor -> yalnizca takim uyeligi (yukleyen olmak
        #     yetmez; raporu yonetici de aktarmis olabilir, ayrica takimdan
        #     ayrilmis bir uye eski yuklemesi sayesinde erisimini surdurmemeli)
        #   * takimi OLMAYAN rapor -> eski davranis, yalnizca yukleyen
        kosul = models.Report.team_id.is_(None) & (
            models.Report.submitted_by_id == user.id
        )
        if takim_kimlikleri:
            kosul = kosul | models.Report.team_id.in_(takim_kimlikleri)
        return query.filter(kosul)
    if aktif == "REFEREE":
        # Ic birlesim (join): atamasi olmayan rapor hakemin listesine
        # DUSMEZ. Dagitimi yarisma yoneticisi yapar.
        return query.join(models.Assignment).filter(
            models.Assignment.referee_id == user.id
        )
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"'{aktif}' rolu rapor listeleyemez.",
    )


def _rapor_getir_yetkiliyse(report_id: str, user: models.User, db: Session) -> models.Report:
    """Raporu bulur ve yetki kapisindan gecirir.

    Bulunamayan ve yetkisiz durum AYNI 404'u dondurmuyor: yetkisiz erisimde
    403 veriyoruz cunku rapor kimliklerinin (RPT-2026-xxxx) tahmin edilmesi
    zaten kolay, gizlemenin bir degeri yok; net hata mesaji ise hakemin
    "neden goremiyorum" sorusunu cevapliyor.
    """
    report = db.query(models.Report).filter(models.Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Rapor bulunamadi.")
    _rol_yoksa_reddet(user)

    # YABANCI KURUM -> 404, kayit hic yokmus gibi. AYNI govde metniyle.
    #
    # Kurum ICINDE 403 dogru tercih (yukaridaki gerekce gecerli: kimlikler
    # tahmin edilebilir, net mesaj hakeme yardim eder). Kurum SINIRINDA ise
    # 403 "bu kimlik baska bir kurumda VAR" bilgisini onaylar - yani bir
    # varlik kahini (oracle) olur. Kimligi elinde tutan biri, 403 ile 404
    # farkindan baska kurumun basvuru kimliklerini dogrulayabilir.
    if not _ayni_kurum_mu(report, user):
        raise HTTPException(status_code=404, detail="Rapor bulunamadi.")

    if not _rapora_erisebilir_mi(report, user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bu rapora erisim yetkiniz yok.",
        )
    return report


@router.get("", response_model=List[schemas.ReportResponse])
def list_reports(
    status: Optional[str] = None,
    competition_id: Optional[str] = None,
    category_label: Optional[str] = None,
    undecided: Optional[bool] = None,
    active_only: Optional[bool] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    # Rol bazli filtreleme, istegin AKTIF ROLUNE gore yapiliyor.
    # Cok-rollu bir kullanici hakem rolundeyken yarismaci raporlarini
    # gormemeli; hangi rolle hareket ettigi belirleyici.
    query = _erisim_filtresi(db.query(models.Report), current_user, db)

    if status:
        query = query.filter(models.Report.status == status)

    # --- Filtreler -------------------------------------------------------
    #
    # Hepsi YETKI FILTRESININ USTUNE biniyor, onun yerine gecmiyor: filtre
    # daraltir, genisletmez. Bir hakem `competition_id` vererek kendisine
    # atanmamis raporlari goremez - _erisim_filtresi zaten uygulandi.
    if competition_id:
        query = query.filter(models.Report.competition_id == competition_id)

    if category_label:
        # Yarismanin kategori/seviye etiketine gore ("Lise", "Vize"...).
        query = query.join(
            models.Competition, models.Report.competition_id == models.Competition.id
        ).filter(models.Competition.category_label == category_label)

    if undecided:
        # Hakem karari VERILMEMIS raporlar - "elimde ne kaldi" sorusu.
        query = query.outerjoin(
            models.FinalDecision, models.FinalDecision.report_id == models.Report.id
        ).filter(models.FinalDecision.id.is_(None))

    if active_only:
        # Yalnizca SUREN yarismalar. Bitmis bir yarismanin raporlari
        # hakemin gunluk listesini gereksiz sisiriyor.
        query = query.join(
            models.Competition, models.Report.competition_id == models.Competition.id
        ).filter(models.Competition.status.in_(("open", "closed", "evaluating")))

    # ai_analysis.results her yanit oncesi uretilmek zorunda (bkz.
    # _attach_analysis_results). Bu eksik oldugu icin endpoint, analiz
    # edilmis ilk rapordan sonra HTTP 500 veriyordu.
    return [_attach_analysis_results(r, current_user) for r in query.all()]


# ARAMA UC NOKTASI - /{report_id}'DEN ONCE TANIMLANMALI.
#
# FastAPI rotalari TANIM SIRASINA gore esler. Bu blok asagidaki
# @router.get("/{report_id}") satirindan SONRA gelseydi, /api/reports/lookup
# istegi get_report(report_id="lookup") olarak eslesir ve "Report not found"
# 404'u donerdi. Hata mesaji yetkilendirmeyi hic akla getirmez; sessiz ve
# uzun suren bir hata olurdu. Testi bu yuzden 404 OLMADIGINI da dogruluyor.
_ARAMA_ROLLERI = auth.RoleChecker(
    ["REFEREE", *models.YONETICI_ROLLERI]
)


def _degerlendirme_durumu(report: models.Report) -> str:
    """Rapor durumunu kunye duzeyine INDIRGER.

    approve/reject ayrimi bilerek yok: bir raporun onaylanip onaylanmadigi,
    o rapora atanmamis bir hakemin bilmesi gereken bir sey degil.
    """
    if report.final_decision is not None:
        return "degerlendirildi"
    if report.status == "error":
        return "hata"
    if report.status == "pending":
        return "analiz_bekliyor"
    return "analiz_edildi"


@router.get("/lookup", response_model=List[schemas.ReportLookupItem])
def lookup_reports(
    report_id: Optional[str] = None,
    team_id: Optional[str] = None,
    email: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(_ARAMA_ROLLERI),
):
    """Basvuru kimligi / takim kimligi / yarismaci e-postasi ile rapor arar.

    NEDEN AYRI BIR UC NOKTA: hakem kendisine ATANMAMIS raporlari da
    arayabilmeli ("bu basvuruya kim bakiyor?"), ama bu bir GEVSETME - bu
    oturumda tam tersi bir acik kapatildi (atanmamis hakem baska bir
    yarismacinin tam AI analizini okuyabiliyordu). Gevsetmeyi savunulabilir
    kilan uc sey:

      1. Yanit KUNYE ile sinirli. Mevcut /api/reports uc noktasina ?q=
         eklemek en kolay yol olurdu ama o ucun yanit modeli ai_analysis ve
         final_decision iceriyor - yani kapatilan acigi geri acardi.
      2. Arama TAM ESLESME. Substring/joker/bos sorgu YOK: substring
         araması envanter taramaktir, tam eslesme "elimde zaten olan bir
         kimligi cozumle" demektir.
      3. Atanmamis erisimler IZ BIRAKIYOR (ReportAccessLog).

    Yarismaci bu uc noktayi kullanamaz (kullanicinin istegi: "ayni aramayi
    basvuran yarismaci HARIC her rol yapabilecek"). Yetki RoleChecker'da -
    arayuzde dugmeyi gizlemek yeterli olmazdi.
    """
    verilenler = [x for x in (report_id, team_id, email) if x]
    if len(verilenler) != 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Tam olarak bir arama olcutu verin: report_id, team_id ya da "
                "email. Bos ya da coklu sorgu kabul edilmiyor."
            ),
        )

    q = db.query(models.Report)
    if report_id:
        q = q.filter(models.Report.id == report_id)
        anahtar = "report_id"
    elif team_id:
        q = q.filter(models.Report.team_id == team_id)
        anahtar = "team_id"
    else:
        # E-posta buyuk/kucuk harf duyarsiz ama TAM eslesme.
        #
        # `ilike` KULLANMIYORUZ: LIKE'in `%` ve `_` jokerlerini yorumluyor ve
        # `?email=%` tek bir istekle rastgele bir kullaniciyi getiriyordu -
        # oysa bu ucun savunmasi "arama TAM ESLESME, joker yok" iddiasina
        # dayaniyor. Kurum filtresi yine de tutuyordu, ama iki savunmadan
        # birinin calismadigini bilmeden digerine guvenmis oluyorduk.
        kullanici = (
            db.query(models.User)
            .filter(func.lower(models.User.email) == email.strip().lower())
            .first()
        )
        if not kullanici:
            return []
        takim_kimlikleri = [
            m.team_id
            for m in db.query(models.TeamMember)
            .filter(models.TeamMember.user_id == kullanici.id)
            .all()
        ]
        kosul = models.Report.submitted_by_id == kullanici.id
        if takim_kimlikleri:
            kosul = kosul | models.Report.team_id.in_(takim_kimlikleri)
        q = q.filter(kosul)
        anahtar = "email"

    aktif = getattr(current_user, "active_role", None)
    aktif_kurum = getattr(current_user, "active_org_id", None)

    # YABANCI KURUM -> sonuc kumesinden CIKARILIYOR, hata donmuyor.
    #
    # Bu bir LISTE uc noktasi ve sozlesmesi zaten "eslesme yoksa 200 + []"
    # (olmayan e-posta icin aynen bunu yapiyor). 403 "bu kayit var ama senin
    # degil" demektir; e-posta anahtariyla birlesince "bu kisinin sistemde
    # basvurusu var mi" kahinine donusur - baska bir kurumun katilimci
    # listesini sizdirmak demektir.
    if aktif_kurum is not None:
        q = q.filter(
            (models.Report.organization_id == aktif_kurum)
            | (models.Report.organization_id.is_(None))
        )

    sonuc = []
    for r in q.order_by(models.Report.submission_date.desc()).limit(50).all():
        atanmis = r.assignment is not None and r.assignment.referee_id == current_user.id
        tam_yetki = atanmis or aktif in models.YONETICI_ROLLERI

        if not tam_yetki:
            db.add(
                models.ReportAccessLog(
                    id=str(uuid.uuid4()),
                    report_id=r.id,
                    user_id=current_user.id,
                    lookup_by=anahtar,
                )
            )

        sonuc.append(
            {
                "report_id": r.id,
                "project_name": r.project_name,
                "team_name": r.team.name if r.team else None,
                "competition_name": r.competition.name if r.competition else None,
                "evaluation_state": _degerlendirme_durumu(r),
                "assigned_referee_email": (
                    r.assignment.referee.email
                    if r.assignment and r.assignment.referee
                    else None
                ),
                "access": "assigned" if tam_yetki else "metadata_only",
            }
        )
    db.commit()
    return sonuc


@router.get("/{report_id}", response_model=schemas.ReportResponse)
def get_report(
    report_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    # Detay, dosyanin kendisiyle AYNI yetki kapisindan geciyor. Onceden
    # yalnizca yarismaci kontrol ediliyordu: atanmamis bir hakem baska bir
    # yarismacinin tam AI analizini (puan, gerekce, benzerlik) okuyabiliyordu.
    report = _rapor_getir_yetkiliyse(report_id, current_user, db)

    # ai_analysis.results semada zorunlu ama veri tabaninda kolon degil -
    # yanit oncesi duz kolonlardan uretiliyor (bkz. _attach_analysis_results).
    return _attach_analysis_results(report, current_user)


@router.post("/{report_id}/reanalyze", response_model=schemas.ReportResponse)
def reanalyze_report(
    report_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        auth.RoleChecker(list(models.YONETICI_ROLLERI))
    ),
):
    """Analizi COKMUS bir raporun analizini yeniden calistirir.

    NEDEN EKLENDI: analiz cokerse rapor "error" durumunda kaliyordu ve
    kurtarmanin tek yolu raporu yeniden YUKLEMEKTI. Ama yeniden yukleme
    yeni bir kayit uretiyor; eski kayit sistemde asili kaliyor, hakemin
    listesinde gorunuyor ve hicbir zaman karara baglanamiyor. Cogu cokme
    gecici (depolama kesintisi, gecici dosya hatasi) oldugu icin tekrar
    denemek dogru cozum.

    Yalnizca "error" durumundaki raporlar icin: analiz edilmis bir raporu
    yeniden analiz etmek, hakemin uzerinde calistigi puanlari sessizce
    degistirirdi.
    """
    # YETKI KAPISINDAN GECIYOR. Onceden rapor dogrudan kimlikle cekiliyordu
    # ve tek kontrol RoleChecker'di - yani "rolun var mi", "bu rapor senin mi"
    # degil. Bugun zararsiz (yonetici zaten hepsini goruyor) ama diger sekiz
    # uc noktanin hepsi bu kapidan geciyor; tek istisna birakmak, kurum
    # kapsami eklendiginde SESSIZ bir yazma deligi olurdu - hem baska kurumun
    # AiAnalysis kaydini siler hem yanitla takim adini sizdirirdi.
    report = _rapor_getir_yetkiliyse(report_id, current_user, db)
    if report.status != "error":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Yalnizca analizi basarisiz olan raporlar yeniden analiz "
                f"edilebilir (bu raporun durumu: '{report.status}')."
            ),
        )

    # Eski (yarim kalmis) analiz kaydi varsa temizleniyor; run_background_analysis
    # her calismada yeni bir AiAnalysis ekliyor ve iki kayit kalirsa hangisinin
    # gecerli oldugu belirsiz olurdu.
    if report.ai_analysis:
        db.delete(report.ai_analysis)
    report.status = "pending"
    db.commit()
    db.refresh(report)

    background_tasks.add_task(run_background_analysis, report_id, report.file_path, db)
    return _attach_analysis_results(report, current_user)


@router.get("/{report_id}/file")
def get_report_file(
    report_id: str,
    download: bool = False,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """Raporun kendisini (PDF/Word) servis eder.

    NEDEN EKLENDI: boyle bir uc nokta HIC YOKTU. Hakem, okuyamadigi bir
    raporu degerlendiriyordu - sistemde yalnizca AI'nin ozeti vardi, belgenin
    kendisi yoktu. Bir hakem karar destek sisteminde bu temel bir eksik.

    `download=false` (varsayilan) tarayicinin gomulu goruntuleyicisinde
    acilmasi icin `inline` doner; `download=true` indirme baslatir.
    """
    # TEK KAPIDAN geciyor. Onceden kendi sorgusunu yapip
    # _rapora_erisebilir_mi cagiriyordu; sonuc olarak yabanci kurumun raporu
    # icin 403 donuyordu - yani "bu kayit VAR ama senin degil" diyordu.
    # /{report_id} 404 donerken bu uc nokta 403 donunce, saldirgan iki ucu
    # karsilastirarak baska kurumun rapor kimliklerini DOGRULAYABILIYORDU.
    # Uc uc noktanin da ayni kapidan gecmesi, ayni cevabi vermelerini garanti
    # ediyor.
    report = _rapor_getir_yetkiliyse(report_id, current_user, db)

    uzanti = Path(report.file_path).suffix.lower()
    medya_tipi = storage.media_type(report.file_path)
    gosterim_adi = report.original_filename or f"{report.id}{uzanti}"
    yerlesim = "attachment" if download else "inline"

    # Supabase Storage referansi: dosya diskte degil, bayt olarak akitiyoruz.
    #
    # Yol dogrulamasi burada GEREKMIYOR ve UYGULANAMAZ: "sb://" bir dosya
    # sistemi yolu degil, bucket icindeki bir nesne anahtari. Dizin
    # gezinmesi (../) bucket API'sinden mumkun degil.
    if storage.is_remote(report.file_path):
        try:
            icerik = storage.read_bytes(report.file_path)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Rapor dosyasi depodan alinamadi: {exc}",
            )
        return Response(
            content=icerik,
            media_type=medya_tipi,
            headers={
                "Content-Disposition": f'{yerlesim}; filename="{gosterim_adi}"',
            },
        )

    # Yol dogrulamasi: file_path veri tabanindan geliyor ama yine de
    # UPLOAD_DIR disina cikmadigini kontrol ediyoruz. Veri tabanina bir
    # sekilde "../../etc/passwd" yazilsa bile dosya servis edilmemeli.
    kok = Path(UPLOAD_DIR).resolve()
    try:
        hedef = Path(report.file_path).resolve()
        hedef.relative_to(kok)
    except (ValueError, OSError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Rapor dosyasinin yolu gecersiz.",
        )

    if not hedef.is_file():
        raise HTTPException(
            status_code=404,
            detail="Rapor kaydi var ama dosya diskte bulunamadi.",
        )

    # Dosya adini HER IKI durumda da veriyoruz: Starlette, filename=None
    # oldugunda Content-Disposition basligini hic gondermiyor ve tarayicinin
    # varsayilanina kaliyoruz. Basligi acikca gondermek, gomulu
    # goruntuleyicide acilmasini garantiliyor.
    return FileResponse(
        path=str(hedef),
        media_type=medya_tipi,
        filename=gosterim_adi,
        content_disposition_type=yerlesim,
    )


@router.post("/{report_id}/rationale-draft", response_model=schemas.RationaleDraft)
def rationale_draft(
    report_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.RoleChecker(["REFEREE"])),
):
    """Hakemin gerekcesi icin AI TASLAGI uretir.

    ETIK CERCEVE - bu uc noktanin tasarimi bilincli:

    Gerekce, bir insanin raporu GERCEKTEN inceledi̇gi̇ni̇n kanitidir. AI'nin
    gerekceyi hayalet yazar gibi yazmasi, projenin ana ilkesini ("AI karar
    verici degildir") terse cevirirdi. Bu yuzden:

      * Taslak OTOMATIK DOLDURULMUYOR - hakem acikca istemek zorunda.
      * Taslak yeni bir yargi URETMIYOR; yalnizca analizin ZATEN buldugu
        somut bulgulari duzenli bir metne donusturuyor. Yani hakemin
        okudugu seyleri toparliyor, onun yerine karar vermiyor.
      * Metnin basinda AI tarafindan uretildigi yaziyor.
      * Karar kaydedilirken bu metnin taslaktan gelip gelmedigi ve hakemin
        DEGISTIRIP degistirmedigi veri tabaninda saklaniyor
        (FinalDecision.rationale_ai_drafted / rationale_edited_by_referee).
        Sonradan itiraz olursa "bu gerekceyi kim yazdi" sorusunun cevabi
        kayitli.
    """
    # TEK KAPIDAN geciyor (bkz. get_report_file). Eski hali "Bu rapor size
    # atanmamis." diyordu - raporun VAR OLDUGUNU ve BIRINE ATANDIGINI birden
    # sizdiran bir mesaj.
    report = _rapor_getir_yetkiliyse(report_id, current_user, db)
    if not report.ai_analysis:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bu rapor icin henuz AI analizi yok; taslak uretilemez.",
        )

    a = report.ai_analysis
    kontroller = [
        ("Dil ve şablon uyumu", a.language_template_score, a.language_template_summary,
         a.language_template_findings, False),
        ("İçerik ve başlık kontrolü", a.content_heading_score, a.content_heading_summary,
         a.content_heading_findings, False),
        ("Kategori uyumu", a.category_match_score, a.category_match_summary,
         a.category_match_findings, False),
        # Benzerlik TERS polarite: dusuk puan iyi sonuc.
        ("Benzerlik / intihal", a.similarity_score, a.similarity_summary,
         a.similarity_findings, True),
    ]

    guclu, zayif = [], []
    for ad, puan, ozet, bulgular_json, ters in kontroller:
        iyi = (puan <= 15) if ters else (puan >= 85)
        satir = f"{ad}: {puan}/100 — {(ozet or '').strip()}"
        (guclu if iyi else zayif).append(satir)

    parcalar = [
        "[Bu taslak AI analizinden üretilmiştir. Göndermeden önce kendi "
        "değerlendirmenizi ekleyin ve gerekli düzeltmeleri yapın.]",
        "",
    ]
    if guclu:
        parcalar.append("Güçlü bulunan noktalar:")
        parcalar += [f"- {s}" for s in guclu]
        parcalar.append("")
    if zayif:
        parcalar.append("Gözden geçirilmesi gereken noktalar:")
        parcalar += [f"- {s}" for s in zayif]
        parcalar.append("")

    # Kriter kirilimi zaten AI gerekcesinin icinde; hakeme oldugu gibi
    # veriyoruz ki puanin nasil olustugunu gorebilsin.
    if a.rationale:
        parcalar.append("Motorun kriter değerlendirmesi:")
        parcalar.append(a.rationale.strip())

    return {
        "draft": "\n".join(parcalar).strip(),
        "notice": (
            "Bu metin AI analizinden üretilmiş bir TASLAKTIR. Nihai gerekçe "
            "sizin değerlendirmenizdir; gönderdiğiniz metnin taslaktan "
            "değiştirilip değiştirilmediği kayıt altına alınır."
        ),
        "suggested_score": a.suggested_score,
        "suggested_outcome": a.suggested_outcome,
    }


@router.post("/{report_id}/decision", response_model=schemas.FinalDecisionResponse)
def submit_decision(
    report_id: str,
    decision_in: schemas.FinalDecisionCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.RoleChecker(["REFEREE"]))
):
    # ATAMA KONTROLU. Onceden yalnizca "hakem mi" diye bakiliyordu: sistemdeki
    # HERHANGI bir hakem, kendisine atanmamis bir raporu -hatta okuma yetkisi
    # olmadigi icin hic acamadigi bir raporu- onaylayip reddedebiliyordu.
    # Karar, sistemin geri alinamayan tek eylemi; en dar kapi burada olmali.
    report = _rapor_getir_yetkiliyse(report_id, current_user, db)

    # CIKAR CATISMASI - ikinci kapi. Atama kontrolu bunu zaten engellemeli
    # (atanamayan hakem karar da veremez), ama karar geri alinamayan tek
    # eylem: atama tarafinda ileride acilacak bir bosluk buraya sizmasin.
    if report.cikar_catismasi_var_mi(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Kendi takiminizin raporunu degerlendiremezsiniz (cikar catismasi)."
            ),
        )

    # Ensure it's analyzed first
    if report.status == "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Hakem karari verilmeden once raporun AI analizi tamamlanmali."
        )
        
    # Check if decision already exists
    existing_decision = db.query(models.FinalDecision).filter(models.FinalDecision.report_id == report_id).first()
    if existing_decision:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bu rapor icin karar zaten verilmis."
        )
        
    # Create decision
    decision_id = str(uuid.uuid4())
    db_decision = models.FinalDecision(
        id=decision_id,
        report_id=report_id,
        referee_id=current_user.id,
        outcome=decision_in.outcome,
        final_score=decision_in.final_score,
        rationale=decision_in.rationale,
        # Denetim izi: gerekce AI taslagindan mi geldi, hakem degistirdi mi.
        # Sonradan itiraz olursa "bu gerekceyi kim yazdi" sorusunun cevabi
        # kayitli olsun diye saklaniyor (bkz. rationale-draft uc noktasi).
        rationale_ai_drafted=decision_in.rationale_ai_drafted,
        rationale_edited_by_referee=decision_in.rationale_edited_by_referee,
        submitted_at=datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
    )
    
    # Karar -> rapor durumu. Acik harita: onceden `report.status` once
    # ham `outcome` ile yaziliyor, sonra iki dal ile duzeltiliyordu; ucuncu
    # deger (revise) tesadufen dogru calisiyordu. Arayuzun tanidigi degerler
    # frontend/src/lib/mock-reports.ts:REPORT_STATUSES ile ayni olmali.
    report.status = {"approve": "approved", "reject": "rejected", "revise": "revise"}[
        decision_in.outcome
    ]


    db.add(db_decision)
    db.commit()
    db.refresh(db_decision)
    return db_decision
