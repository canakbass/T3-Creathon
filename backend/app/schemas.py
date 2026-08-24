from pydantic import BaseModel, EmailStr
from typing import List, Optional, Dict
from datetime import datetime

# --- Token Schemas ---
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None
    role: Optional[str] = None


# --- User Schemas ---
class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: Optional[str] = None
    # Bir kullanicinin birden fazla rolu olabilir.
    roles: Optional[List[str]] = None
    # Tekil `role`, tek rol gonderen eski istemciler icin kabul ediliyor.
    role: Optional[str] = None

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class RoleSelection(BaseModel):
    role: str

class UserResponse(BaseModel):
    id: str
    email: EmailStr
    full_name: Optional[str] = None
    created_at: datetime
    roles: List[str] = []
    # Aktif rol (yoksa ilk rol). Tekil rol bekleyen eski istemciler icin.
    role: Optional[str] = None

    class Config:
        from_attributes = True

class RefereeSummary(BaseModel):
    id: str
    email: EmailStr
    full_name: Optional[str] = None
    # Uzerindeki rapor sayisi - yonetici dagilimi gorup mudahale edebilsin.
    assigned_count: int = 0

class RefereeAdd(BaseModel):
    referee_id: str

class AssignmentUpdate(BaseModel):
    referee_id: str

class AssignmentResponse(BaseModel):
    report_id: str
    referee_id: str
    referee_email: Optional[EmailStr] = None
    assigned_at: datetime
    auto_assigned: bool

class AutoAssignItem(BaseModel):
    report_id: str
    referee_id: str
    referee_email: EmailStr

class RefereeLoad(BaseModel):
    referee_id: str
    email: EmailStr
    assigned_count: int

class AutoAssignResult(BaseModel):
    assigned: int
    assignments: List[AutoAssignItem]
    load: List[RefereeLoad]


class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    # Kullanicinin SAHIP OLDUGU tum roller
    roles: List[str]
    # Token'in imzalandigi rol. Cok-rollu kullanici henuz secmediyse None -
    # arayuz bu durumda rol secim ekrani gosterir.
    active_role: Optional[str] = None
    user: UserResponse


# --- Category Schemas ---
class CategoryBase(BaseModel):
    name: str
    description: Optional[str] = None

class CategoryCreate(CategoryBase):
    id: str

class CategoryResponse(CategoryBase):
    id: str

    class Config:
        from_attributes = True


# --- Criteria Schemas ---
class CriteriaBase(BaseModel):
    category_id: str
    title: str
    description: Optional[str] = None
    max_score: int = 100

class CriteriaCreate(CriteriaBase):
    id: str

class CriteriaResponse(CriteriaBase):
    id: str

    class Config:
        from_attributes = True


# --- AI Analysis Details ---
class AiCheckResult(BaseModel):
    score: int
    summary: str
    findings: List[str]

class AiAnalysisResponse(BaseModel):
    id: str
    report_id: str
    analyzed_at: datetime
    engine_version: str
    suggested_outcome: str
    suggested_score: int
    rationale: str
    results: Dict[str, AiCheckResult]

    class Config:
        from_attributes = True


# --- Final Decision Schemas ---
class FinalDecisionCreate(BaseModel):
    outcome: str # approve, reject, revise
    final_score: int
    rationale: str

class FinalDecisionResponse(BaseModel):
    id: str
    report_id: str
    referee_id: str
    outcome: str
    final_score: int
    rationale: str
    submitted_at: datetime

    class Config:
        from_attributes = True


# --- Report Schemas ---
class ReportBase(BaseModel):
    project_name: str
    category_id: str

class ReportCreate(ReportBase):
    id: str
    file_path: str
    submitted_by_id: str

class ReportResponse(ReportBase):
    id: str
    status: str
    file_path: str
    submitted_by_id: str
    submission_date: datetime
    ai_analysis: Optional[AiAnalysisResponse] = None
    final_decision: Optional[FinalDecisionResponse] = None

    class Config:
        from_attributes = True


# --- Dashboard Stats Schemas ---
class DashboardStats(BaseModel):
    total_reports: int
    pending_reports: int
    analyzed_reports: int
    approved_reports: int
    rejected_reports: int
    revise_reports: int
    completion_rate: float
