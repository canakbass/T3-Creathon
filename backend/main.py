import warnings
import os
import uuid
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.services import notify
from app.database import engine, Base, SessionLocal
from app.routes import (
    auth as auth_router,
    criteria as criteria_router,
    reports as reports_router,
    dashboard as dashboard_router,
    assignments as assignments_router,
    competitions as competitions_router,
    organizations as organizations_router,
)
from app import models, auth
from app.services import storage

# Create database tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="TEKNOFEST AI-Assisted Evaluation System Backend",
    description="Backend service detailing the DB and AI pipeline orchestration",
    version="1.0.0"
)

# CORS. Yayina alindiginda Vercel adresi de gerekiyor, o yuzden ortam
# degiskeninden okunuyor (virgulle ayrilmis liste).
#
# DIKKAT: tarayici HTTPS uzerinden servis edilen bir sayfadan HTTP bir
# backend'e istek atamaz (karisik icerik engeli) - dagitimda backend de
# HTTPS olmali.
_CORS_ORIGINS = [
    o.strip()
    for o in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
    if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth_router.router)
app.include_router(organizations_router.router)
app.include_router(criteria_router.router)
app.include_router(reports_router.router)
app.include_router(dashboard_router.router)
app.include_router(assignments_router.router)
app.include_router(competitions_router.router)


@app.get("/")
def read_root():
    return {"message": "TEKNOFEST AI-Assisted Evaluation System Backend is running"}


# Seed database with initial data on startup if empty
@app.on_event("startup")
def seed_db():
    # GELISTIRME BAYRAKLARI ACIKSA YUKSEK SESLE SOYLE.
    #
    # `DEV_EXPOSE_EMAIL_TOKEN` dogrulama jetonunu API yanitinda gosteriyor -
    # yani "bu kutunun sahibi misin" sorusunu kendi kendine cevaplatiyor.
    # Uretimde acik kalmasi, e-posta dogrulamayi tamamen anlamsiz kilar.
    if notify.jeton_yanitta_gorunsun_mu():
        warnings.warn(
            "DEV_EXPOSE_EMAIL_TOKEN acik: e-posta dogrulama jetonlari API "
            "yanitinda gorunuyor. Bu YALNIZCA gelistirme icindir - uretimde "
            "kapatin (EMAIL_BACKEND=smtp iken zaten calismaz).",
            RuntimeWarning,
        )

    # Dosya deposunu hazirla (Supabase bucket'i ya da yerel uploads dizini).
    storage.ensure_bucket()

    db = SessionLocal()
    try:
        # --- Kurumlar ------------------------------------------------------
        #
        # Varsayilan kurum, geriye donuk uyum icin: mevcut tum kayitlar buna
        # baglaniyor ve sistem bozulmadan devam ediyor. Ikinci kurum, kurumlar
        # arasi yalitimin DEMO EDILEBILMESI icin - tek kurumla "A kurumu B'yi
        # goremiyor" kurali hic sinanamaz.
        if db.query(models.Organization).count() == 0:
            print("Seeding organizations...")
            for org_id, ad, slug in [
                ("org-t3", "T3 Vakfı", "t3-vakfi"),
                ("org-cbu", "Manisa Celal Bayar Üniversitesi", "cbu"),
            ]:
                db.add(models.Organization(id=org_id, name=ad, slug=slug))
            db.commit()

        # Check if users are seeded
        if db.query(models.User).count() == 0:
            print("Seeding default users...")
            default_users = [
                # (e-posta, sifre, ad, roller)
                ("manager@teknofest.org", "password123", "Demo Yarışma Yöneticisi",
                 ["COMPETITION_MANAGER"]),
                ("referee@teknofest.org", "password123", "Demo Hakem",
                 ["REFEREE"]),
                ("referee2@teknofest.org", "password123", "Demo Hakem 2",
                 ["REFEREE"]),
                ("competitor@teknofest.org", "password123", "Demo Yarışmacı",
                 ["COMPETITOR"]),
                # Takim arkadaslari: "takimdaki HERKES sonucu gorebilmeli"
                # kuralinin demo edilebilmesi icin en az iki uye gerekiyor.
                ("competitor2@teknofest.org", "password123", "Takım Arkadaşı",
                 ["COMPETITOR"]),
                # BASKA bir takimin uyesi: "takimda degilsen GOREMEZSIN"
                # kuralini gostermek icin.
                ("rakip@teknofest.org", "password123", "Rakip Takım Üyesi",
                 ["COMPETITOR"]),
                ("evaluator@teknofest.org", "password123", "Demo Değerlendirme Yöneticisi",
                 ["EVALUATION_MANAGER"]),
                # COK-ROLLU TEST HESABI: her role sahip - ORG_OWNER dahil.
                # Kullanicinin tarif ettigi hesap bu: "asdfghjkl hesabi gibi
                # superuserlar olmali, kendi kurumundaki hakemleri
                # yoneticileri herkesi degistirebilmeli". Giriste kurum+rol
                # secim ekrani cikar; tek hesapla tum akislar denenebilir.
                ("asdfghjkl@gmail.com", "asdfghjkl", "Test Kullanıcısı",
                 list(models.ROLLER)),
            ]

            # IKINCI KURUM (CBU) HESAPLARI. Tek kurumla "A kurumu B'yi
            # goremiyor" kurali HIC sinanamaz; yalitimi gostermek icin
            # karsi tarafta da gercek hesaplar gerekiyor. Bu hesaplar
            # KASITLI olarak org-t3'te HICBIR role sahip degil.
            cbu_users = [
                ("sorumlu@cbu.edu.tr", "parola123", "CBÜ Kurum Sorumlusu",
                 ["ORG_OWNER"]),
                ("ogretim@cbu.edu.tr", "parola123", "CBÜ Öğretim Elemanı",
                 ["COMPETITION_MANAGER"]),
                ("asistan@cbu.edu.tr", "parola123", "CBÜ Asistan",
                 ["REFEREE"]),
                ("ogrenci@cbu.edu.tr", "parola123", "CBÜ Öğrencisi",
                 ["COMPETITOR"]),
            ]

            for kurum_id, hesaplar in (("org-t3", default_users), ("org-cbu", cbu_users)):
                for email, pwd, ad, roller in hesaplar:
                    db_user = models.User(
                        id=str(uuid.uuid4()),
                        email=email,
                        password_hash=auth.hash_password(pwd),
                        full_name=ad,
                        # Tohum hesaplarini YONETICI acmis sayiyoruz: kimlige
                        # kefil olan var, dogrulama beklemeye gerek yok.
                        email_verified=True,
                    )
                    db.add(db_user)
                    db.flush()
                    for rol in roller:
                        db.add(models.UserRole(
                            id=str(uuid.uuid4()),
                            user_id=db_user.id,
                            organization_id=kurum_id,
                            role=rol,
                        ))
            db.commit()

        # --- Takimlar -------------------------------------------------------
        #
        # TAKIM YONETIMI BU SISTEMIN ISI DEGIL. Gercek kayitlar TEKNOFEST'in
        # kendi sisteminde (KYS / t3kys.com) tutuluyor; sartname raporlarin
        # oraya teslim edildigini soyluyor. Biz o veriyi TUKETEN bir
        # degerlendirme katmaniyiz - bu yuzden takim olusturma/uye duzenleme
        # arayuzu YOK, kayitlar disaridan besleniyor. `external_ref` gercek
        # entegrasyonda eslestirme anahtari; burada demo icin seed ediliyor.
        #
        # Kurulan demo yapisi (kullanicinin istedigi gibi):
        #   Glieser      -> competitor@ (kaptan) + competitor2@ (uye)
        #   ADYU AI TEAM -> competitor@ (uye)      <- ayni kisi IKI takimda
        #   Zebot        -> rakip@ (kaptan)        <- digerlerini GOREMEZ
        if db.query(models.Team).count() == 0:
            print("Seeding demo teams...")

            def _kullanici(eposta):
                return db.query(models.User).filter(models.User.email == eposta).first()

            takimlar = [
                ("team-glieser", "Glieser", "KYS-2026-000431",
                 [("competitor@teknofest.org", "kaptan"),
                  ("competitor2@teknofest.org", "uye")]),
                ("team-adyu", "ADYU AI TEAM", "KYS-2026-000902",
                 [("competitor@teknofest.org", "uye")]),
                ("team-zebot", "Zebot", "KYS-2026-001177",
                 [("rakip@teknofest.org", "kaptan")]),
            ]
            for takim_id, ad, dis_ref, uyeler in takimlar:
                db.add(models.Team(
                    id=takim_id, name=ad, external_ref=dis_ref, organization_id="org-t3"
                ))
                db.flush()
                for eposta, gorev in uyeler:
                    u = _kullanici(eposta)
                    # E-POSTA kalici kimlik, `user_id` yalnizca baglanti.
                    # Tohum hesaplari yonetici acmis sayiliyor, yani
                    # dogrulanmis - bu yuzden dogrudan baglaniyorlar.
                    db.add(models.TeamMember(
                        id=str(uuid.uuid4()),
                        team_id=takim_id,
                        email=eposta.strip().lower(),
                        user_id=u.id if u else None,
                        role=gorev,
                    ))
            db.commit()

        # Check if categories are seeded
        if db.query(models.Category).count() == 0:
            print("Seeding default categories...")
            categories = [
                ("cat-1", "Robotics & Automation", "Drones, industrial robots, automation algorithms and hardware implementations."),
                ("cat-2", "AI & Machine Learning", "Neural networks, NLP models, computer vision pipelines and data analysis."),
                ("cat-3", "Sustainability & Energy", "Green technology, carbon capture, renewable systems and load balancing."),
                ("cat-4", "FinTech", "Cryptographic ledgers, micro-lending platforms, automated trading and finance tools."),
                ("cat-5", "HealthTech", "Remote patient monitoring, diagnostic assistants, wearable sensors and health data."),
                ("cat-6", "Game Design", "Procedural generator engines, interactive stories, VR/AR and gameplay mechanics.")
            ]
            for cat_id, name, desc in categories:
                db_category = models.Category(id=cat_id, name=name, description=desc)
                db.add(db_category)
            db.commit()
            
        # Check if criteria are seeded
        if db.query(models.Criteria).count() == 0:
            print("Seeding default criteria templates...")
            criteria_items = [
                ("crit-1", "cat-2", "Language & Template Compliance", "Evaluation of how closely the report follows the formatting guide and language requirements.", 100),
                ("crit-2", "cat-2", "Technical Novelty", "Novelty of the model architecture, training protocols, or data collection methods.", 100),
                ("crit-3", "cat-2", "Experimental Rigour", "Ablation studies, benchmark testing, and evaluation metrics clarity.", 100),
                ("crit-4", "cat-2", "Ethical & Data Privacy Considerations", "Discussion on dataset licensing, model bias, and privacy preservation.", 100),
            ]
            for crit_id, cat_id, title, desc, max_val in criteria_items:
                db_criteria = models.Criteria(
                    id=crit_id,
                    category_id=cat_id,
                    title=title,
                    description=desc,
                    max_score=max_val
                )
                db.add(db_criteria)
            db.commit()
            
    except Exception as e:
        print(f"Error seeding database: {str(e)}")
        db.rollback()
    finally:
        db.close()
