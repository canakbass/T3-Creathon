from pydantic import BaseModel, EmailStr, Field
from typing import List, Literal, Optional, Dict
from datetime import datetime

# --- Token Schemas ---
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None
    role: Optional[str] = None
    # Istegin yapildigi kurum. Rol artik tek basina bir kimlik degil -
    # "hakem" degil, "T3 Vakfi'nda hakem".
    organization_id: Optional[str] = None


# --- User Schemas ---
class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: Optional[str] = None
    # Bir kullanicinin birden fazla rolu olabilir.
    roles: Optional[List[str]] = None
    # Tekil `role`, tek rol gonderen eski istemciler icin kabul ediliyor.
    role: Optional[str] = None

class AdminUserCreate(BaseModel):
    """Yoneticinin actigi hesap. Sifre GONDERILMEZ - sistem uretir."""
    email: EmailStr
    full_name: Optional[str] = None
    roles: List[str] = ["COMPETITOR"]
    # Istege bagli: ayni islemde takima ekle.
    team_id: Optional[str] = None
    team_role: Optional[str] = None


class CreatedUser(BaseModel):
    id: str
    email: EmailStr
    full_name: Optional[str] = None
    roles: List[str]
    team_id: Optional[str] = None
    # YALNIZCA BU YANITTA doner; veri tabaninda yalnizca bcrypt ozeti var.
    #
    # BOS olabilir: e-posta baska bir kurumda zaten kayitliysa yeni hesap
    # acilmiyor, o kuruma UYELIK ekleniyor - ve mevcut sifre degistirilmiyor
    # (degistirilse, bir kurumun yoneticisi o kisinin baska kurumdaki
    # oturumunu dusurebilirdi).
    temporary_password: Optional[str] = None
    notice: str


class OrganizationResponse(BaseModel):
    """Kullanicinin HANGI KURUM ADINA calistigi.

    Arayuz bunu her ekranda gostermeli: yanlis kurumda islem yapmak, baska
    bir kurumun verisine dokunmak demek.
    """
    id: str
    name: str
    slug: str
    my_roles: List[str]
    member_count: int


class OrganizationMember(BaseModel):
    id: str
    email: EmailStr
    full_name: Optional[str] = None
    # BU KURUMDAKI roller. Ayni kisinin baska kurumdaki rolleri burada
    # GORUNMEZ - gorunsse bir kurumun sorumlusu, uyesinin baska kurumlardaki
    # konumunu ogrenirdi.
    roles: List[str]


class RoleGrant(BaseModel):
    role: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str

class RoleSelection(BaseModel):
    role: str
    # Hangi kurum adina. Verilmezse ve o role tek kurumda sahipse turetiliyor;
    # birden fazlaysa secim ZORUNLU - yanlis kurumda islem yapmak, baska bir
    # kurumun verisine dokunmak demek.
    organization_id: Optional[str] = None

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

# --- Competition Schemas ---
class CompetitionCreate(BaseModel):
    name: str
    description: Optional[str] = None
    # Kategori/seviye etiketi - SERBEST METIN, sabit listeden secilmiyor.
    # TEKNOFEST'te "Lise" / "Universite ve Uzeri" / "Mezun"; baska bir
    # kullanimda "Vize" ya da "Kidemli Backend" olabilir.
    category_label: Optional[str] = Field(default=None, max_length=80)
    # Eski global kategori tablosuna baglanti. Geriye donuk uyumluluk icin
    # duruyor; yeni yarismalarda gerekmiyor.
    category_id: Optional[str] = None
    submission_deadline: Optional[datetime] = None

class CompetitionTemplate(BaseModel):
    """Yarismanin sablon kurallari - AI dil/sablon/baslik kontrolu bunlari kullanir."""
    # Bu sablonun ait oldugu rapor asamasi (bkz. models.Competition.report_type_name).
    report_type_name: Optional[str] = Field(default=None, max_length=80)
    accepted_languages: List[str] = ["tr"]
    required_headings: List[str]
    heading_synonyms: Optional[Dict[str, List[str]]] = None
    min_pages: Optional[int] = None
    max_pages: Optional[int] = None
    min_section_chars: Optional[int] = None
    # Analiz edilmis raporlar varsa kurallari degistirmek onlarin puanlarini
    # gecersiz kilar (bkz. _degisim_etkisi). Yonetici bunu acikca onaylamali.
    confirm_reanalysis: bool = False

class CriterionInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: Optional[str] = None
    # Agirlik TEK TEK de dogrulanmali, yalnizca toplamı 100 olsun diye degil:
    # [{"A": 150}, {"B": -50}] toplamı 100 ediyordu ve kabul ediliyordu.
    # Negatif agirlik, agirlikli ortalamada iyi bir kriterin toplami
    # DUSURMESI anlamina gelirdi - hakemin anlayamayacagi bir sonuc.
    weight: int = Field(ge=1, le=100)

class CompetitionCriteriaSet(BaseModel):
    criteria: List[CriterionInput]
    confirm_reanalysis: bool = False

class CriterionResponse(BaseModel):
    id: str
    title: str
    description: Optional[str] = None
    weight: int
    display_order: int

class ExtractedCriterion(BaseModel):
    title: str
    weight: Optional[int] = None


class TemplateExtractResult(BaseModel):
    """POST /api/competitions/{id}/template/extract yaniti.

    Bu bir ONERI; hicbir sey kaydedilmiyor. Yonetici listeyi duzenleyip
    normal /template ve /criteria uc noktalariyla kaydediyor.
    """
    required_headings: List[str]
    criteria: List[ExtractedCriterion]
    # Cikarilan agirliklarin toplami. 100 degilse `warnings` sebebini soyluyor.
    weight_total: Optional[int] = None
    # Hangi sinyalden cikarildi ("docx:Balk1", "pdf:(stilsiz)"...). Yonetici
    # sonuca guvenip guvenmeyecegine karar verebilsin diye aciga cikariyoruz.
    source: Optional[str] = None
    warnings: List[str] = []


class ReportLookupItem(BaseModel):
    """Arama sonucu - KUNYE duzeyinde, degerlendirme icerigi YOK.

    Bilerek DISARIDA birakilanlar: ai_analysis (puan/gerekce/benzerlik
    bulgulari), final_decision (puan/gerekce), dosya yolu ve yarismaci
    kimligi. Arama "elimdeki kimligi cozumle" icindir, "envanteri tara"
    icin degil.
    """
    report_id: str
    project_name: str
    team_name: Optional[str] = None
    competition_name: Optional[str] = None
    # analiz_bekliyor | analiz_edildi | degerlendirildi | hata
    # Onay/ret AYRIMI YOK: bir raporun ONAYLANIP onaylanmadigi, o rapora
    # atanmamis bir hakemin bilmesi gereken bir sey degil.
    evaluation_state: str
    # Aramanin asil cevabi: "bu rapora kim bakiyor?"
    assigned_referee_email: Optional[EmailStr] = None
    # assigned  -> tam detaya yetkiniz var (arayuz oraya yonlendirir)
    # metadata_only -> yalnizca bu kunye
    access: str


class CompetitionStatusUpdate(BaseModel):
    status: str

class CompetitionResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    category_id: Optional[str] = None
    category_name: Optional[str] = None
    # Yarismanin kendi kategori/seviye etiketi (serbest metin).
    category_label: Optional[str] = None
    # Yarismanin sahibi kurum (kiraci). Su an bilgi amacli; kurum kapsami
    # devreye girdiginde erisim filtresinin dayanagi olacak.
    organization_id: Optional[str] = None
    status: str
    submission_deadline: Optional[datetime] = None
    created_at: datetime
    report_type_name: Optional[str] = None
    accepted_languages: List[str] = []
    required_headings: List[str] = []
    heading_synonyms: Dict[str, List[str]] = {}
    min_pages: Optional[int] = None
    max_pages: Optional[int] = None
    min_section_chars: Optional[int] = None
    criteria: List[CriterionResponse] = []
    referee_count: int = 0
    report_count: int = 0


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

class AutoAssignOptions(BaseModel):
    """Otomatik dagitim havuzunu daraltma secenekleri.

    Kullanicinin istegi: "hakemi olmayan raporlara KAC HAKEM eklenecegini,
    HANGILERININ eklenecegini de belirleyebilsin."

    Bu, rapor basina kac hakem DEGIL (o hala tek), DAGITIM HAVUZUNA kac/hangi
    hakem girecegi demek. Ikisi de verilmezse davranis eskisi gibi: yarismada
    gorevli TUM hakemler havuza girer.
    """
    # Havuzu elle sec. Bos/verilmemisse yarismanin tum gorevli hakemleri.
    referee_ids: Optional[List[str]] = None
    # "En az yuklu N hakemi tek tikla havuz yap." Kullanicinin "rastgele en az
    # projeden sorumlu olan hakeme direkt ekleyebilsin" istegi bu.
    limit_least_loaded: Optional[int] = Field(default=None, ge=1, le=100)


class SkippedAssignment(BaseModel):
    report_id: str
    reason: str


class AutoAssignResult(BaseModel):
    assigned: int
    assignments: List[AutoAssignItem]
    load: List[RefereeLoad]
    # Dagitilamayan raporlar. SESSIZ ATLAMA YOK: bir rapor atanamadiysa
    # yonetici bunu gormeli, aksi halde "dagitim tamam" sanip hic
    # degerlendirilmeyen bir rapor birakir.
    skipped: List[SkippedAssignment] = []


class Membership(BaseModel):
    organization_id: str
    organization_name: Optional[str] = None
    roles: List[str]


class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    # Kullanicinin SAHIP OLDUGU tum roller
    roles: List[str]
    # Token'in imzalandigi rol. Cok-rollu kullanici henuz secmediyse None -
    # arayuz bu durumda rol secim ekrani gosterir.
    active_role: Optional[str] = None
    # Token'in imzalandigi kurum. Rol gibi, secilmemisse None.
    active_organization_id: Optional[str] = None
    # Kullanicinin hangi kurumda hangi rollere sahip oldugu. Arayuz secim
    # ekranini bundan kuruyor.
    memberships: List[Membership] = []
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
class RationaleDraft(BaseModel):
    """AI'nin urettigi gerekce TASLAGI - nihai gerekce degil."""
    draft: str
    notice: str
    suggested_score: int
    suggested_outcome: str

class FinalDecisionCreate(BaseModel):
    # NEDEN Literal: bu deger dogrudan Report.status'a yaziliyordu. Serbest
    # metin oldugu icin {"outcome": "SACMA"} gonderen bir istek raporun
    # durumunu "SACMA" yapiyor, rapor da hicbir arayuz filtresine
    # dusmedigi icin ortadan kayboluyordu.
    outcome: Literal["approve", "reject", "revise"]
    # Puan 0-100 arasi; arayuz de bu araligi gosteriyor.
    final_score: int = Field(ge=0, le=100)
    # Gerekce zorunlu: hakem karari yazili dayanak olmadan kaydedilmemeli.
    # Ust sinir, veri tabanina sinirsiz metin yazilmasini engelliyor.
    rationale: str = Field(min_length=20, max_length=10000)
    # Denetim izi: gerekce AI taslagindan mi geldi, hakem degistirdi mi.
    # Arayuz taslak dugmesini kullandiysa bunlari gonderir.
    rationale_ai_drafted: bool = False
    rationale_edited_by_referee: bool = False

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
    original_filename: Optional[str] = None
    competition_id: Optional[str] = None
    # Raporun SAHIBI takim. Sonucu kimin gorecegini bu belirliyor -
    # submitted_by_id yalnizca YUKLEYENI soyluyor ve ikisi ayni olmak
    # zorunda degil (sartname AKIS 01: yonetici raporlari sisteme aktarir).
    team_id: Optional[str] = None
    team_name: Optional[str] = None
    submitted_by_id: str
    submission_date: datetime
    ai_analysis: Optional[AiAnalysisResponse] = None
    final_decision: Optional[FinalDecisionResponse] = None
    # Atama bilgisi listede de donuyor: yonetici panelinin her rapor icin
    # ayri bir istek atmasini (N+1) onlemek icin.
    assigned_referee_id: Optional[str] = None
    assigned_referee_email: Optional[EmailStr] = None

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
