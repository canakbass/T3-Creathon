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


# Sistemdeki roller (bkz. docs/PROJECT_CONTEXT.md Bolum 2).
#
# ORG_OWNER (kurum sorumlusu) sartnamedeki dort role sonradan eklendi.
# NEDEN: dort rol "bu kurumda kim ne yapar" sorusunu cevapliyordu ama "bu
# kurumda KIM VAR" sorusunu kimse cevaplamiyordu. Sonuc olarak hesap acma
# yetkisi yarisma yonetisindeydi ve her yonetici sinirsiz yonetici
# uretebiliyordu - yani yetki zinciri kendi kendini cogaltiyordu.
# Kurum sorumlusu bu zincirin kokunu tutuyor: kurumun uyelerini ve
# rollerini YALNIZCA o degistirir, ama YALNIZCA KENDI kurumunda.
ROLLER = (
    "ORG_OWNER",
    "COMPETITION_MANAGER",
    "REFEREE",
    "COMPETITOR",
    "EVALUATION_MANAGER",
)

# Kurumun tum verisini gorebilen roller. Yetki kapilari bu listeyi kullanir;
# uc ayri dosyada elle yazilan tuple'lar zamanla birbirinden ayrisiyordu.
YONETICI_ROLLERI = ("ORG_OWNER", "COMPETITION_MANAGER", "EVALUATION_MANAGER")

# YALNIZCA kurum sorumlusunun verebilecegi roller.
#
# NEDEN: bu roller kurumun TUM verisini gorebiliyor (ya da ORG_OWNER
# durumunda baskalarina yetki verebiliyor). Yarisma yoneticisi bunlari
# dagitabilseydi, tek bir yonetici hesabi ele gecirildiginde saldirgan
# kendine sinirsiz yonetici uretip kurumu kalici olarak elinde tutabilirdi.
# Yetki YUKARI DOGRU dagitilamaz.
AYRICALIKLI_ROLLER = ("ORG_OWNER", "COMPETITION_MANAGER", "EVALUATION_MANAGER")


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
        """TUM kurumlardaki rollerin duz listesi.

        !!! YETKILENDIRMEDE KULLANMAYIN !!!
        Bu liste kurum ayrimi YAPMAZ. Bir kullanicinin A kurumundaki hakem
        rolu, B kurumunda hicbir sey ifade etmemeli. Yetki kontrolu icin
        `roles_in(org_id)` kullanin.

        Geriye donuk uyumluluk icin duruyor (giris yaniti, hata mesajlari).
        """
        return sorted({r.role for r in self.roles})

    def roles_in(self, organization_id) -> list:
        """Kullanicinin BELIRLI BIR KURUMDAKI rolleri.

        Yetkilendirmenin dayanmasi gereken tek liste budur. `organization_id`
        None ise bos liste doner - "kurum secilmemis" durumu "her yetki" degil
        "hicbir yetki" anlamina gelmeli (rolde ogrenilen dersin birebir
        tekrari: eksik baglam, filtre yoklugu degil erisim yoklugudur).
        """
        if organization_id is None:
            return []
        return sorted({r.role for r in self.roles if r.organization_id == organization_id})

    @property
    def memberships(self) -> list:
        """[{organization_id, organization_name, roles}] - giris ekrani icin.

        Cok kurumlu kullanici giriste HANGI KURUM ADINA calisacagini secmeli;
        "hakem" tek basina bir kimlik degil, "T3 Vakfi'nda hakem" bir kimlik.
        """
        gruplu = {}
        for r in self.roles:
            if r.organization_id is None:
                continue
            kayit = gruplu.setdefault(
                r.organization_id,
                {
                    "organization_id": r.organization_id,
                    "organization_name": r.organization.name if r.organization else None,
                    "roles": set(),
                },
            )
            kayit["roles"].add(r.role)
        return [
            {**k, "roles": sorted(k["roles"])}
            for k in sorted(gruplu.values(), key=lambda x: x["organization_id"])
        ]


class UserRole(Base):
    """Kullanicinin BIR KURUMDAKI rolu (uyelik).

    NEDEN KURUM ALANI VAR: bu tablo (user_id, role) benzersizligiyle rolu
    GLOBAL yapan tek satirdi - bir kurumda hakem olan HER kurumda hakemdi.
    Kullanicinin sordugu senaryo tam olarak buydu: "ben hem TEKNOFEST
    yarismasi icin hem de odev sonucu kontrolu icin ayni maile bagliysam?"
    Cevap: ayni kisi A kurumunda hakem, B kurumunda yarismaci olabilmeli.

    User GLOBAL kalir (e-posta tekil), uyelik kuruma baglanir.
    """

    __tablename__ = "user_roles"
    __table_args__ = (
        UniqueConstraint("user_id", "organization_id", "role", name="uq_user_org_role"),
    )

    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    # Rolun gecerli oldugu kurum. Gecis suresince nullable; kurum kapisi
    # devreye girdiginde zorunlu olacak.
    organization_id = Column(
        String, ForeignKey("organizations.id"), nullable=True, index=True
    )
    role = Column(String, nullable=False)

    user = relationship("User", back_populates="roles")
    organization = relationship("Organization")


class Organization(Base):
    """KURUM (kiraci / tenant).

    NEDEN VAR: sistem bugune kadar TEK KURUMLUK calisiyordu - herkes ayni
    havuzdaydi. Bunun uc somut sonucu vardi:
      * Bir kurumda hakem olan, HER kurumda hakemdi (UserRole global).
      * "Bu yarisma kimin?" sorusunun cevabi sistemde YOKTU
        (Competition.created_by_id vardi ama hicbir yerde filtre degildi).
      * GET /api/reports/lookup ile bir kurumun hakemi, BASKA bir kurumun
        her basvurusunun kunyesini okuyabiliyordu.

    Ayni kullanici BIRDEN FAZLA kurumda olabilir ve rolleri kuruma gore
    DEGISEBILIR: ayni kisi TEKNOFEST'te hakem, kendi universitesinde odev
    degerlendiren egitmen olabilir.

    DIKKAT: bu tablo tek basina hicbir seyi KISITLAMIYOR. Kisitlama, erisim
    kapilarina kurum kapsami eklendiginde devreye girer. Kismi uygulama
    (alan var ama filtre yok) tehlikelidir - bu yuzden alanlar ve filtreler
    ayni adimda gitmeli.
    """

    __tablename__ = "organizations"

    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    # Kisa, insan-okunur kimlik ("t3-vakfi", "cbu-muhendislik").
    slug = Column(String, unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=_utcnow)

    competitions = relationship("Competition", back_populates="organization")
    teams = relationship("Team", back_populates="organization")


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
    # BOS = ortak/sistem kategorisi, her kurum gorur. Dolu = yalnizca o
    # kurumun kategorisi. Kategori adi masum gorunuyor ama bir kurumun
    # calistigi alanlari ("Vize Odevi - ML 101") disariya anlatiyor;
    # kurumun kendi actigi kategori kurumda kalmali.
    organization_id = Column(
        String, ForeignKey("organizations.id"), nullable=True, index=True
    )

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
    # Yarismanin SAHIBI kurum. `created_by_id` yalnizca "kim olusturdu"yu
    # soyluyor ve o kisi kurumdan ayrilabilir; sahiplik kisiye degil KURUMA
    # ait olmali.
    organization_id = Column(
        String, ForeignKey("organizations.id"), nullable=True, index=True
    )
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
    # Bu sablonun ait oldugu RAPOR ASAMASI ("On Tasarim Raporu", "Kritik
    # Tasarim Raporu"...).
    #
    # NEDEN VAR: bir TEKNOFEST yarismasinin TEK sablonu yok. 2026 Havacilikta
    # YZ teknik sartnamesi madde 5: "Yarismaci takimlardan IKI AYRI DOKUMAN
    # yazmalari beklenmektedir" - On Tasarim Raporu ve Final Tasarim Raporu,
    # sablonlari farkli tarihlerde yayimlaniyor. Ustelik ayni yarismanin
    # asamalari FARKLI puan agirliklari kullaniyor (bkz. sample_reports/
    # havacilikta_yz_ktr/Puan_Rubrigi.md: 2022 KTR agirliklari 2026 OTR
    # agirliklariyla ortusmüyor).
    #
    # Arayuzde bu deger "Sablon adi" diye soruluyordu ve HICBIR YERE
    # kaydedilmiyordu; artik hangi asamanin kurallarina bakildigi kayitli.
    report_type_name = Column(String, nullable=True)

    # Yarismanin KATEGORI/SEVIYE etiketi - SERBEST METIN.
    #
    # NEDEN GLOBAL TABLO DEGIL: sistemde "kategori" adiyla alti INGILIZCE
    # genel hackathon kategorisi seed ediliyordu ("Robotics & Automation",
    # "FinTech", "Game Design") ve bunun TEKNOFEST ile hicbir ilgisi yok.
    # TEKNOFEST'te kategori KATILIMCI SEVIYESI demek - 2026 Genel Sartname:
    # "Mezun kategorisi lise mezunu ve universite mezunlarini kapsamaktadir",
    # "Lise seviyesindeki takimlar bir danisman almak zorundadir". Teknoloji
    # alanini yarismanin ADI belirliyor ("Havacilikta Yapay Zeka").
    #
    # NEDEN SABIT LISTE DE DEGIL: bu sistem yalnizca TEKNOFEST icin degil.
    # Ayni degerlendirme hatti odev kontrolu ("Vize", "Final") ya da ise alim
    # taramasi ("Kidemli Backend") icin de kullanilabiliyor. Sabit bir enum
    # o kullanimlarin hepsini disarida birakirdi; her musteri kendi ayrimini
    # yaziyor.
    category_label = Column(String, nullable=True)

    accepted_languages = Column(Text, nullable=True)   # ["tr"]
    required_headings = Column(Text, nullable=True)    # ["Takım Şeması", ...]
    heading_synonyms = Column(Text, nullable=True)     # {"Kaynakça": ["Referanslar"]}
    min_pages = Column(Integer, nullable=True)
    max_pages = Column(Integer, nullable=True)
    min_section_chars = Column(Integer, nullable=True)

    category = relationship("Category", back_populates="competitions")
    organization = relationship("Organization", back_populates="competitions")
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


# Takim uyeliginde kisinin gorevi. TEKNOFEST 2026 Genel Sartnamesi'nden:
#   "Takim Kaptani: Takimin organizasyonundan sorumlu olan ve sureclerde
#    liderlik gorevini ustlenen kisi"
#   "Takim Danismani: Her takim icin EN FAZLA BIR (1) ogretmen/egitmen/
#    akademisyen"
TAKIM_GOREVLERI = ("kaptan", "uye", "danisman")


class Team(Base):
    """Basvuru birimi: TAKIM.

    NEDEN VAR: TEKNOFEST'te basvuruyu bir KISI degil bir TAKIM yapiyor
    (2026 Genel Sartname: takim kaptani + uyeler + en fazla bir danisman).
    Sistemimizde ise rapor yalnizca `submitted_by_id` ile bir KISIYE
    bagliydi ve bunun iki somut sonucu vardi:
      * Takim arkadasi kendi takiminin sonucunu GOREMIYORDU.
      * Yonetici bir raporu sisteme aktardiginda (sartname AKIS 01: "raporlari
        sisteme aktarir") rapor YONETICININ raporu oluyor ve HICBIR yarismaci
        sonucunu goremiyordu.

    TAKIM YONETIMI BU SISTEMIN ISI DEGIL. Gercek kayitlar TEKNOFEST'in kendi
    sisteminde (KYS / t3kys.com) tutuluyor; sartname raporlarin oraya teslim
    edildigini soyluyor. Biz o veriyi TUKETEN bir degerlendirme katmaniyiz.
    Bu yuzden takim olusturma/uye duzenleme icin arayuz YOK; kayitlar
    disaridan besleniyor (`external_ref` eslestirme anahtari) ve demo icin
    seed ediliyor.
    """

    __tablename__ = "teams"

    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    # KYS'deki takim kimligi. Gercek entegrasyonda eslestirme bu alandan
    # yapilir; bizim id'lerimiz KYS'nin id'leri olmak zorunda degil.
    external_ref = Column(String, nullable=True, index=True)
    # Takimin bagli oldugu kurum. Ayni takim adi farkli kurumlarda
    # bulunabilir; `external_ref` de yalnizca kurum icinde benzersizdir.
    organization_id = Column(
        String, ForeignKey("organizations.id"), nullable=True, index=True
    )
    created_at = Column(DateTime, default=_utcnow)

    organization = relationship("Organization", back_populates="teams")
    members = relationship(
        "TeamMember", back_populates="team", cascade="all, delete-orphan", lazy="selectin"
    )
    reports = relationship("Report", back_populates="team")

    @property
    def member_ids(self) -> set:
        return {m.user_id for m in self.members}


class TeamMember(Base):
    __tablename__ = "team_members"
    __table_args__ = (UniqueConstraint("team_id", "user_id", name="uq_takim_uye"),)

    id = Column(String, primary_key=True, index=True)
    team_id = Column(String, ForeignKey("teams.id"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    # kaptan | uye | danisman  (bkz. TAKIM_GOREVLERI)
    role = Column(String, nullable=False, default="uye")

    team = relationship("Team", back_populates="members")
    user = relationship("User")


class ReportAccessLog(Base):
    """Hakemin KENDISINE ATANMAMIS bir rapora kunye duzeyinde erisimi.

    NEDEN VAR: hakemin atanmamis raporlari arayabilmesi bilincli bir
    GEVSETME. Bu oturumda tam tersi bir acik kapatildi ("atanmamis hakem
    baska bir yarismacinin tam AI analizini okuyabiliyordu"). Gevsetmeyi
    savunulabilir kilan sey, erisimin (a) yalnizca kunyeyle sinirli olmasi
    ve (b) IZ BIRAKMASI. Iz birakmayan bir gevsetme, kapattigimiz acigin
    daha kucuk bir kopyasi olurdu.

    Yalnizca ATANMAMIS erisimler yaziliyor: atanmis hakemin kendi raporunu
    okumasi normal is akisi, loglanirsa kayit gurultuye bogulur ve icinden
    gercek anormallik secilemez.

    Kaydi Degerlendirme Yoneticisi okur - sartname: "degerlendirme akisini
    izler; gerekli operasyonel aksiyonlari yonetir."
    """

    __tablename__ = "report_access_log"

    id = Column(String, primary_key=True, index=True)
    report_id = Column(String, ForeignKey("reports.id"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    # Hangi anahtarla arandi: report_id | team_id | email
    lookup_by = Column(String, nullable=False)
    accessed_at = Column(DateTime, default=_utcnow, index=True)

    report = relationship("Report")
    user = relationship("User")


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
    # Raporun SAHIBI takim. `submitted_by_id` yalnizca YUKLEYENI soyluyor ve
    # ikisi ayni kisi olmak zorunda degil: sartname AKIS 01, yarisma
    # yoneticisinin raporlari sisteme AKTARDIGINI soyluyor. Sonucu kimin
    # gorecegi buradan belirleniyor, yukleyenden degil.
    #
    # nullable: yarisma akisi devreye girmeden once yuklenmis eski kayitlar
    # ve takim kavrami olmayan test/demo raporlari icin. Takimi olmayan
    # raporda erisim eski davranisa (yalnizca yukleyen) dusuyor.
    team_id = Column(String, ForeignKey("teams.id"), nullable=True, index=True)
    # Raporun ait oldugu KURUM.
    #
    # NEDEN TURETILMIYOR: kurum Competition uzerinden turetilebilirdi ama
    # `competition_id` NULLABLE. Ic birlesimle turetirsek yarismasiz raporlar
    # HERKESTEN gizlenir; dis birlesimle turetirsek kurum NULL kalir ve
    # HERKESE gorunur. Ikinci hata sessizdir - tam olarak "kismi
    # cok-kurumluluk" tuzagi. Kendi kolonu olmasi, hicbir yolun kurumsuz
    # rapor uretememesini de garanti ediyor.
    organization_id = Column(
        String, ForeignKey("organizations.id"), nullable=True, index=True
    )
    submission_date = Column(DateTime, default=_utcnow)

    submitted_by = relationship("User", back_populates="reports")
    team = relationship("Team", back_populates="reports")

    def cikar_catismasi_var_mi(self, hakem) -> bool:
        """Bu hakem bu raporu degerlendiremez mi.

        NEDEN MODELDE: kural uc ayri yerde uygulanmak zorunda (otomatik
        dagitim, elle atama, karar). Uc kopya kacinilmaz olarak birbirinden
        ayrisir; tek tanim burada.

        NEDEN SUBMITTED_BY YETMIYOR: takim kavrami eklendikten sonra raporun
        SAHIBI takim, yukleyen degil. Sartname AKIS 01'de raporu yarisma
        yoneticisi de aktarabiliyor; o durumda `submitted_by_id` yoneticidir
        ve takimin bir uyesi ayni zamanda hakemse "yukleyen mi" kontrolu
        BOSA DUSER. Yani kisi kendi takiminin raporunu onaylayabilirdi.
        """
        if self.team_id and self.team is not None:
            if hakem.id in self.team.member_ids:
                return True
        return hakem.id == self.submitted_by_id
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
