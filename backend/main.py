import uuid
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.database import engine, Base, SessionLocal
from app.routes import (
    auth as auth_router,
    criteria as criteria_router,
    reports as reports_router,
    dashboard as dashboard_router,
    assignments as assignments_router,
    competitions as competitions_router,
)
from app import models, auth

# Create database tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="TEKNOFEST AI-Assisted Evaluation System Backend",
    description="Backend service detailing the DB and AI pipeline orchestration",
    version="1.0.0"
)

# Enable CORS for the Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth_router.router)
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
    db = SessionLocal()
    try:
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
                ("evaluator@teknofest.org", "password123", "Demo Değerlendirme Yöneticisi",
                 ["EVALUATION_MANAGER"]),
                # COK-ROLLU TEST HESABI: dort rolun hepsine sahip. Giriste
                # rol secim ekrani cikar; tek hesapla tum akislar denenebilir.
                ("asdfghjkl@gmail.com", "asdfghjkl", "Test Kullanıcısı",
                 list(models.ROLLER)),
            ]
            for email, pwd, ad, roller in default_users:
                db_user = models.User(
                    id=str(uuid.uuid4()),
                    email=email,
                    password_hash=auth.hash_password(pwd),
                    full_name=ad,
                )
                db.add(db_user)
                db.flush()
                for rol in roller:
                    db.add(models.UserRole(
                        id=str(uuid.uuid4()), user_id=db_user.id, role=rol
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
