import datetime
from sqlalchemy import (
    Column,
    String,
    Integer,
    Boolean,
    DateTime,
    ForeignKey,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from .database import Base


def _utcnow() -> datetime.datetime:
    """datetime.datetime.utcnow() deprecated oldugu icin (Python 3.12+) -
    ayni naive-UTC davranisini timezone-aware API ile uretiyoruz."""
    return datetime.datetime.now(datetime.UTC).replace(tzinfo=None)


# Sistemdeki dort rol (bkz. docs/PROJECT_CONTEXT.md Bolum 2).
ROLLER = ("COMPETITION_MANAGER", "REFEREE", "COMPETITOR", "EVALUATION_MANAGER")


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    full_name = Column(String, nullable=True)
    created_at = Column(DateTime, default=_utcnow)

    # Rol artik BURADA DEGIL, ayri UserRole tablosunda.
    #
    # NEDEN: bir kullanicinin birden fazla rolu olabilir (ornegin ayni kisi
    # hem hakem hem degerlendirme yoneticisi). Tek bir `role` kolonu bunu
    # ifade edemiyordu. Kullanici giris yaptiktan sonra hangi rolle devam
    # edecegini seciyor ve token O ROLE gore imzalaniyor - yani yetki
    # kontrolu sunucu tarafinda kaliyor.
    roles = relationship(
        "UserRole", back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )

    reports = relationship("Report", back_populates="submitted_by")
    decisions = relationship("FinalDecision", back_populates="referee")
    assignments = relationship(
        "Assignment", back_populates="referee", foreign_keys="Assignment.referee_id"
    )

    @property
    def role_list(self) -> list:
        """Kullanicinin sahip oldugu rollerin duz listesi."""
        return [r.role for r in self.roles]


class UserRole(Base):
    __tablename__ = "user_roles"
    __table_args__ = (UniqueConstraint("user_id", "role", name="uq_user_role"),)

    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    role = Column(String, nullable=False)

    user = relationship("User", back_populates="roles")


class Category(Base):
    """Konu alani (Robotik, Yapay Zeka, Saglik...).

    Yarismadan FARKLI bir kavram: AI'nin "bu rapor beyan edilen alana ait
    mi" kontrolu bu listeye karsi calisiyor (ai-scoring/category.py).
    Bir yarisma tek bir kategoriye baglidir.
    """

    __tablename__ = "categories"

    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)

    competitions = relationship("Competition", back_populates="category")
    criteria_list = relationship("Criteria", back_populates="category")


class Competition(Base):
    """Bir yarisma (orn. "Havacilikta Yapay Zeka 2026").

    NEDEN EKLENDI: onceden sistemde "yarisma" diye bir kavram YOKTU, yalnizca
    Category vardi. Bu yuzden:
      * bir yarisma yoneticisi birden fazla yarismayi ayri ayri yonetemiyordu
      * sablon kurallari (zorunlu basliklar, dil, sayfa siniri) tum sistem
        icin TEK bir dosyada (docs/mvp-rules.json) sabitti
      * "basvurular ne zaman acik" gibi bir asama kavrami yoktu
    """

    __tablename__ = "competitions"

    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    category_id = Column(String, ForeignKey("categories.id"), nullable=False)
    created_by_id = Column(String, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=_utcnow)

    # Yarismanin asamasi. Yarismacinin rapor yukleyip yukleyemeyecegini ve
    # AI analizinin calisip calismayacagini bu belirliyor:
    #   draft      - hazirlik, yarismaci goremez
    #   open       - basvuru acik, yarismaci yukleyebilir, AI analizi OTOMATIK calisir
    #   closed     - basvuru kapandi, yeni yukleme yok, analizler tamamlaniyor
    #   evaluating - hakemler degerlendiriyor
    #   completed  - bitti, sonuclar yarismaciya acik
    status = Column(String, nullable=False, default="draft")
    submission_deadline = Column(DateTime, nullable=True)

    # --- Sablon kurallari (Kriter ve Sablon Tanimi ekrani bunlari doldurur) ---
    # JSON metni olarak saklaniyor: SQLite'ta yerel JSON tipi yok ve Postgres'e
    # gectigimizde de ayni kod calissin istiyoruz.
    accepted_languages = Column(Text, nullable=True)   # ["tr"]
    required_headings = Column(Text, nullable=True)    # ["Takım Şeması", ...]
    heading_synonyms = Column(Text, nullable=True)     # {"Kaynakça": ["Referanslar"]}
    min_pages = Column(Integer, nullable=True)
    max_pages = Column(Integer, nullable=True)
    min_section_chars = Column(Integer, nullable=True)

    category = relationship("Category", back_populates="competitions")
    created_by = relationship("User", foreign_keys=[created_by_id])
    reports = relationship("Report", back_populates="competition")
    criteria_list = relationship(
        "CompetitionCriterion",
        back_populates="competition",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    referees = relationship(
        "CompetitionReferee",
        back_populates="competition",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class CompetitionCriterion(Base):
    """Bir yarismanin degerlendirme kriteri ve AGIRLIGI.

    Eski `Criteria` tablosundan farki: yarismaya bagli ve `weight` tasiyor.
    AI kriter puanlamasi (ai-scoring/criteria.py) bu agirliklari kullanabilsin
    diye eklendi - onceden agirliklar docs/scoring-rules.json'da sabitti.
    """

    __tablename__ = "competition_criteria"

    id = Column(String, primary_key=True, index=True)
    competition_id = Column(String, ForeignKey("competitions.id"), nullable=False, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    weight = Column(Integer, nullable=False, default=0)
    display_order = Column(Integer, nullable=False, default=0)

    competition = relationship("Competition", back_populates="criteria_list")


class CompetitionReferee(Base):
    """Bir yarismada gorevli hakemler.

    Rapor atamasi yalnizca bu listedeki hakemlere yapilabiliyor.
    """

    __tablename__ = "competition_referees"
    __table_args__ = (
        UniqueConstraint("competition_id", "referee_id", name="uq_competition_referee"),
    )

    id = Column(String, primary_key=True, index=True)
    competition_id = Column(String, ForeignKey("competitions.id"), nullable=False, index=True)
    referee_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    added_at = Column(DateTime, default=_utcnow)

    competition = relationship("Competition", back_populates="referees")
    referee = relationship("User", foreign_keys=[referee_id])


class Criteria(Base):
    """ESKI kriter tablosu - kategori bazli, agirliksiz.

    Geriye donuk uyumluluk icin duruyor (mevcut /api/criteria uc noktalari ve
    testleri bunu kullaniyor). Yeni is CompetitionCriterion uzerinden
    yurutulmeli.
    """

    __tablename__ = "criteria"

    id = Column(String, primary_key=True, index=True)
    category_id = Column(String, ForeignKey("categories.id"), nullable=False)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    max_score = Column(Integer, default=100)

    category = relationship("Category", back_populates="criteria_list")


class Report(Base):
    __tablename__ = "reports"

    id = Column(String, primary_key=True, index=True)
    project_name = Column(String, nullable=False)
    category_id = Column(String, ForeignKey("categories.id"), nullable=False)
    # Yarismaya baglanti. Eski kayitlar icin nullable - mevcut testler
    # yarisma olusturmadan rapor yukluyor.
    competition_id = Column(String, ForeignKey("competitions.id"), nullable=True, index=True)
    status = Column(String, default="pending")  # pending, analyzed, approved, rejected, revise, error
    file_path = Column(String, nullable=False)
    # Yuklenen dosyanin KULLANICININ verdigi adi. Indirme sirasinda bunu
    # kullaniyoruz; diskteki ad RPT-2026-XXXXXX.pdf seklinde normalize edilmis.
    original_filename = Column(String, nullable=True)
    submitted_by_id = Column(String, ForeignKey("users.id"), nullable=False)
    submission_date = Column(DateTime, default=_utcnow)

    submitted_by = relationship("User", back_populates="reports")
    category = relationship("Category")
    competition = relationship("Competition", back_populates="reports")
    ai_analysis = relationship("AiAnalysis", back_populates="report", uselist=False)
    final_decision = relationship("FinalDecision", back_populates="report", uselist=False)
    assignment = relationship(
        "Assignment", back_populates="report", uselist=False, cascade="all, delete-orphan"
    )


class Assignment(Base):
    """Bir raporun hangi hakeme atandigi.

    NEDEN EKLENDI: onceden atama diye bir sey YOKTU - her hakem her raporu
    goruyordu. Gercek bir degerlendirme surecinde raporlar hakemler arasinda
    dagitilir ve her hakem yalnizca kendi sorumlulugundakini gorur.
    """

    __tablename__ = "assignments"

    id = Column(String, primary_key=True, index=True)
    report_id = Column(String, ForeignKey("reports.id"), unique=True, nullable=False, index=True)
    referee_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    assigned_by_id = Column(String, ForeignKey("users.id"), nullable=False)
    assigned_at = Column(DateTime, default=_utcnow)
    # Otomatik dagitimla mi yoksa yonetici elle mi atadi (denetim izi)
    auto_assigned = Column(Boolean, default=True)

    report = relationship("Report", back_populates="assignment")
    referee = relationship("User", back_populates="assignments", foreign_keys=[referee_id])
    assigned_by = relationship("User", foreign_keys=[assigned_by_id])


class AiAnalysis(Base):
    __tablename__ = "ai_analyses"

    id = Column(String, primary_key=True, index=True)
    report_id = Column(String, ForeignKey("reports.id"), unique=True, nullable=False)
    analyzed_at = Column(DateTime, default=_utcnow)
    engine_version = Column(String, default="eval-engine v1.0")
    suggested_outcome = Column(String, nullable=False)  # approve, reject, revise
    suggested_score = Column(Integer, nullable=False)
    rationale = Column(Text, nullable=False)

    language_template_score = Column(Integer, default=0)
    language_template_summary = Column(Text, nullable=True)
    language_template_findings = Column(Text, nullable=True)  # JSON string

    content_heading_score = Column(Integer, default=0)
    content_heading_summary = Column(Text, nullable=True)
    content_heading_findings = Column(Text, nullable=True)  # JSON string

    category_match_score = Column(Integer, default=0)
    category_match_summary = Column(Text, nullable=True)
    category_match_findings = Column(Text, nullable=True)  # JSON string

    similarity_score = Column(Integer, default=0)
    similarity_summary = Column(Text, nullable=True)
    similarity_findings = Column(Text, nullable=True)  # JSON string

    report = relationship("Report", back_populates="ai_analysis")


class FinalDecision(Base):
    __tablename__ = "final_decisions"

    id = Column(String, primary_key=True, index=True)
    report_id = Column(String, ForeignKey("reports.id"), unique=True, nullable=False)
    referee_id = Column(String, ForeignKey("users.id"), nullable=False)
    outcome = Column(String, nullable=False)  # approve, reject, revise
    final_score = Column(Integer, nullable=False)
    rationale = Column(Text, nullable=False)
    submitted_at = Column(DateTime, default=_utcnow)

    # --- AI taslak gerekce denetim izi ---
    #
    # Hakem "AI taslak oner" dugmesini kullandiysa bu isaretleniyor ve
    # gonderilen metnin taslaktan DEGISTIRILIP degistirilmedigi kaydediliyor.
    #
    # NEDEN: gerekce, bir insanin gercekten inceledigi̇nin kanitidir. AI'nin
    # hayalet yazar olmasi projenin ana ilkesini ("AI karar verici degildir")
    # terse cevirirdi. Taslak sunmak kabul edilebilir, ama HANGI metnin
    # AI'dan geldigi denetlenebilir kalmali - sonradan itiraz olursa
    # "bu gerekceyi kim yazdi" sorusunun cevabi kayitli olsun.
    rationale_ai_drafted = Column(Boolean, default=False)
    rationale_edited_by_referee = Column(Boolean, default=False)

    report = relationship("Report", back_populates="final_decision")
    referee = relationship("User", back_populates="decisions")
