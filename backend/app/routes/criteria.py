import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional

from ..database import get_db
from .. import models, schemas, auth, tenancy

router = APIRouter(prefix="/api", tags=["Categories & Criteria"])

# Category Endpoints
#
# NEDEN GIRIS SART: bu iki listeleme uc noktasi kimlik dogrulamasi
# istemiyordu, yani token'i olmayan herkes yarisma kategorilerini ve
# degerlendirme kriterlerini okuyabiliyordu. Kriterler bir yarismanin
# puanlama rubrigi; basvuru acikken disariya acik olmasi, yarismacilarin
# rapor yazmak yerine rubrige gore optimize etmesine kapi araliyor.
# Ayrica sartname T3 verilerinin ucuncu taraflarla paylasilmamasini
# sart kosuyor (bkz. docs/CLAUDE.md).
@router.get("/categories", response_model=List[schemas.CategoryResponse])
def get_categories(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    # Ortak kategoriler (organization_id bos) herkese gorunur; kurumun kendi
    # actiklari yalnizca o kuruma.
    return tenancy.kurum_filtresi(
        db.query(models.Category), models.Category, current_user
    ).all()

@router.post("/categories", response_model=schemas.CategoryResponse, status_code=status.HTTP_201_CREATED)
def create_category(
    category_in: schemas.CategoryBase,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.RoleChecker(["COMPETITION_MANAGER", "EVALUATION_MANAGER"]))
):
    cat_id = str(uuid.uuid4())
    db_category = models.Category(
        id=cat_id,
        name=category_in.name,
        description=category_in.description,
        # Yeni kategori ACAN KURUMUN. Ortak kategoriler yalnizca tohumlama
        # (seed) ile olusuyor - bir uc noktadan "herkese gorunur kategori"
        # acilabilseydi her yonetici tum kurumlarin listesine yazabilirdi.
        organization_id=tenancy.aktif_kurum(current_user),
    )
    db.add(db_category)
    db.commit()
    db.refresh(db_category)
    return db_category

# Criteria Endpoints
@router.get("/criteria", response_model=List[schemas.CriteriaResponse])
def get_criteria(
    category_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    # Kriter kapsamini KATEGORISINDEN aliyor: kendi `organization_id` alani
    # yok, kategoriye baglanarak ayni kapsami paylasiyor. Iki ayri alan
    # olsaydi ikisi zamanla birbirinden ayrisir ve hangisinin gecerli
    # oldugu belirsizlesirdi.
    gorunur = [
        k.id
        for k in tenancy.kurum_filtresi(
            db.query(models.Category), models.Category, current_user
        ).all()
    ]
    query = db.query(models.Criteria).filter(models.Criteria.category_id.in_(gorunur))
    if category_id:
        query = query.filter(models.Criteria.category_id == category_id)
    return query.all()

@router.post("/criteria", response_model=schemas.CriteriaResponse, status_code=status.HTTP_201_CREATED)
def create_criteria(
    criteria_in: schemas.CriteriaBase,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.RoleChecker(["COMPETITION_MANAGER", "EVALUATION_MANAGER"]))
):
    # Verify category exists
    category = db.query(models.Category).filter(models.Category.id == criteria_in.category_id).first()
    if category and not tenancy.ayni_kurum_mu(category, current_user):
        category = None  # yabanci kurumun kategorisi YOK sayilir
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found."
        )
        
    crit_id = str(uuid.uuid4())
    db_criteria = models.Criteria(
        id=crit_id,
        category_id=criteria_in.category_id,
        title=criteria_in.title,
        description=criteria_in.description,
        max_score=criteria_in.max_score
    )
    db.add(db_criteria)
    db.commit()
    db.refresh(db_criteria)
    return db_criteria
