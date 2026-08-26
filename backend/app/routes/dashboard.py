from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ..database import get_db
from .. import models, schemas, auth, tenancy

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])

@router.get("/stats", response_model=schemas.DashboardStats)
def get_dashboard_stats(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.RoleChecker(["COMPETITION_MANAGER", "EVALUATION_MANAGER"]))
):
    # Sayilar KURUMLA sinirli. Toplam sayilar zararsiz gorunuyor ama bir
    # kurumun kac basvuru aldigi ve kacini reddettigi o kuruma ait bir bilgi;
    # ustelik sayac, ekleme-cikarma ile baska kurumun hareketlerini takip
    # etmeye de yarar (bugun 12, yarin 15 -> "3 basvuru geldi").
    def sayac(durum=None):
        q = tenancy.kurum_filtresi(db.query(models.Report), models.Report, current_user)
        if durum:
            q = q.filter(models.Report.status == durum)
        return q.count()

    total = sayac()
    pending = sayac("pending")
    analyzed = sayac("analyzed")
    approved = sayac("approved")
    rejected = sayac("rejected")
    revise = sayac("revise")
    
    # Completion rate: proportion of reports with final decisions (approved + rejected + revise) over total reports
    completed = approved + rejected + revise
    rate = (completed / total * 100.0) if total > 0 else 0.0
    
    return {
        "total_reports": total,
        "pending_reports": pending,
        "analyzed_reports": analyzed,
        "approved_reports": approved,
        "rejected_reports": rejected,
        "revise_reports": revise,
        "completion_rate": round(rate, 2)
    }
