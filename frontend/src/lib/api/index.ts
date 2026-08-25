/**
 * Backend uç noktalarının arayüz tarafındaki karşılıkları.
 *
 * Her fonksiyon tel formatını (snake_case) alır, `mappers.ts` ile arayüz
 * tiplerine çevirir ve öyle döner. Bileşenler `WireReport` gibi tipleri
 * hiç görmez.
 */

import type { AiAnalysis } from "@/lib/ai-analysis";
import type { DecisionOutcome } from "@/lib/final-decision";
import type { EvaluationReport } from "@/lib/mock-reports";
import { apiFetch, apiFetchBlob, ApiError } from "./client";
import {
  buildCategoryNameMap,
  toAiAnalysis,
  toDecisionOutcome,
  toEvaluationReport,
  type CategoryNameMap,
} from "./mappers";
import type {
  WireAutoAssignResult,
  WireCategory,
  WireCompetition,
  WireDashboardStats,
  WireFinalDecision,
  WireLoginResponse,
  WireRationaleDraft,
  WireReferee,
  WireReport,
  WireReportLookup,
  WireUser,
} from "./types";

export { ApiError, API_BASE_URL, NetworkError } from "./client";
export type { CategoryNameMap } from "./mappers";

/* ------------------------------------------------------------------ auth */

export interface Session {
  token: string;
  /** Kullanıcının sahip olduğu tüm roller. */
  roles: string[];
  /** Token'ın imzalandığı rol. null ise rol seçimi gerekiyor. */
  activeRole: string | null;
  userId: string;
  email: string;
  fullName: string | null;
}

function toSession(wire: WireLoginResponse): Session {
  return {
    token: wire.access_token,
    roles: wire.roles ?? [],
    activeRole: wire.active_role,
    userId: wire.user?.id ?? "",
    email: wire.user?.email ?? "",
    fullName: wire.user?.full_name ?? null,
  };
}

/**
 * Gerçek JWT girişi.
 *
 * Backend `OAuth2PasswordRequestForm` kullanıyor, yani gövde JSON DEĞİL
 * form-encoded ve e-posta alanının adı `username` (OAuth2 standardı böyle).
 * Bu, kolayca gözden kaçan bir ayrıntı — JSON gönderilse 422 alınır.
 *
 * Kullanıcının tek rolü varsa `activeRole` dolu döner ve arayüz doğrudan
 * panele geçer. Birden fazla rolü varsa null döner — arayüz rol seçimi
 * gösterip {@link selectRole} çağırmalı.
 */
export async function login(email: string, password: string): Promise<Session> {
  const form = new URLSearchParams({ username: email, password });
  const wire = await apiFetch<WireLoginResponse>("/api/auth/login", {
    method: "POST",
    formBody: form,
    skipAuth: true,
  });
  return toSession(wire);
}

/**
 * Aktif rolü seçer ve O ROLE göre imzalanmış YENİ bir token alır.
 *
 * Yetki kontrolü sunucuda kalıyor: arayüz "ben şimdi hakemim" diyerek rol
 * değiştiremez, rolü token taşıyor ve token'ı yalnızca sunucu imzalayabilir.
 */
export async function selectRole(role: string, token?: string): Promise<Session> {
  const wire = await apiFetch<WireLoginResponse>("/api/auth/select-role", {
    method: "POST",
    json: { role },
    token,
  });
  return toSession(wire);
}

export interface RegisterInput {
  email: string;
  password: string;
  fullName?: string;
  roles: string[];
}

export async function register(input: RegisterInput): Promise<WireUser> {
  return apiFetch<WireUser>("/api/auth/register", {
    method: "POST",
    skipAuth: true,
    json: {
      email: input.email,
      password: input.password,
      full_name: input.fullName || null,
      roles: input.roles,
    },
  });
}

export async function fetchMe(): Promise<WireUser> {
  return apiFetch<WireUser>("/api/auth/me");
}

/* ------------------------------------------------------- kategoriler */

export async function listCategories(): Promise<WireCategory[]> {
  return apiFetch<WireCategory[]>("/api/categories");
}

export async function loadCategoryNames(): Promise<CategoryNameMap> {
  try {
    return buildCategoryNameMap(await listCategories());
  } catch {
    // Kategori listesi alınamazsa rapor listesi yine gösterilmeli;
    // mapper kategori adı yerine kimliği gösterecek.
    return new Map();
  }
}

/* ------------------------------------------------------------ raporlar */

/** Hakemin verdiği nihai karar (henüz verilmediyse null). */
export interface RefereeDecision {
  outcome: DecisionOutcome;
  finalScore: number;
  rationale: string;
  submittedAt: string;
}

export interface ReportWithAnalysis {
  report: EvaluationReport;
  analysis: AiAnalysis | null;
  /** Ham backend durumu — "approved"/"rejected"/"error" gibi arayüz birleşiminde olmayan değerler dahil. */
  rawStatus: string;
  /** Hakem kararı verilmiş mi (verilmişse form tekrar gösterilmemeli). */
  hasDecision: boolean;
  decision: RefereeDecision | null;
}

export async function listReports(options: { status?: string } = {}): Promise<EvaluationReport[]> {
  const query = options.status ? `?status=${encodeURIComponent(options.status)}` : "";
  const [wire, categoryNames] = await Promise.all([
    apiFetch<WireReport[]>(`/api/reports${query}`),
    loadCategoryNames(),
  ]);
  return wire.map((r) => toEvaluationReport(r, categoryNames));
}

/**
 * Yönetici paneli için: rapor + atama + karar bilgisi, TEK istekte.
 *
 * `listReports` yalnızca arayüzün `EvaluationReport` tipini döndürüyor;
 * atama panelinin sorumlu hakemi ve karar durumunu da bilmesi gerekiyor.
 * Bunu her rapor için ayrı `getReport` çağırarak yapmak N+1 istek olurdu.
 */
export interface ReportRow {
  report: EvaluationReport;
  assignedRefereeId: string | null;
  assignedRefereeEmail: string | null;
  hasDecision: boolean;
  competitionId: string | null;
  /** Raporun sahibi takım — arama takım adıyla da yapılabiliyor. */
  teamId: string | null;
  teamName: string | null;
}

export async function listReportRows(): Promise<ReportRow[]> {
  const [wire, names] = await Promise.all([
    apiFetch<WireReport[]>("/api/reports"),
    loadCategoryNames(),
  ]);
  return wire.map((r) => ({
    report: toEvaluationReport(r, names),
    assignedRefereeId: r.assigned_referee_id,
    assignedRefereeEmail: r.assigned_referee_email,
    hasDecision: r.final_decision !== null,
    competitionId: r.competition_id,
    teamId: r.team_id,
    teamName: r.team_name,
  }));
}

export async function getReport(
  reportId: string,
  categoryNames?: CategoryNameMap,
  signal?: AbortSignal,
): Promise<ReportWithAnalysis> {
  const names = categoryNames ?? (await loadCategoryNames());
  // `signal`: yoklama iptal edildiğinde UÇUŞTAKİ istek de iptal edilmeli.
  // Önceden AbortController yalnızca bekleme (`sleep`) arasını kesiyordu;
  // o an sunucudan dönmekte olan istek tamamlanıp state'i yazıyordu. Sonuç:
  // hakem başka bir rapora geçtikten sonra ESKİ raporun verisi ekrana
  // düşebiliyordu.
  const wire = await apiFetch<WireReport>(`/api/reports/${encodeURIComponent(reportId)}`, {
    signal,
  });
  const decision = wire.final_decision;
  return {
    report: toEvaluationReport(wire, names),
    analysis: toAiAnalysis(wire.ai_analysis),
    rawStatus: wire.status,
    hasDecision: decision !== null,
    decision: decision
      ? {
          outcome: toDecisionOutcome(decision.outcome),
          finalScore: decision.final_score,
          rationale: decision.rationale,
          submittedAt: decision.submitted_at,
        }
      : null,
  };
}

/** Arama ölçütü — tam olarak BİRİ verilmeli. */
export type ReportLookupQuery =
  | { reportId: string }
  | { teamId: string }
  | { email: string };

/**
 * Başvuru kimliği / takım kimliği / yarışmacı e-postası ile rapor arar.
 *
 * Hakem kendisine ATANMAMIŞ raporları da arayabilir ama yalnızca KÜNYE
 * görür — puan, gerekçe, benzerlik bulgusu ve PDF dönmez. Yarışmacı bu ucu
 * hiç kullanamaz (backend 403).
 *
 * Arama TAM EŞLEŞMEDİR: substring/joker yok. Sebep, aramanın envanter
 * taramaya dönüşmemesi.
 */
export async function lookupReports(
  sorgu: ReportLookupQuery,
): Promise<WireReportLookup[]> {
  const p = new URLSearchParams();
  if ("reportId" in sorgu) p.set("report_id", sorgu.reportId);
  else if ("teamId" in sorgu) p.set("team_id", sorgu.teamId);
  else p.set("email", sorgu.email);
  return apiFetch<WireReportLookup[]>(`/api/reports/lookup?${p.toString()}`);
}

export interface UploadReportInput {
  projectName: string;
  /**
   * Raporun sahibi takım. Yönetici aktarımında ZORUNLU — aksi halde rapor
   * sahipsiz kalır ve sonucunu hiçbir yarışmacı göremez.
   */
  teamId?: string | null;
  /** Yarışma verilirse kategori ondan alınır; ayrıca seçmeye gerek yok. */
  competitionId?: string;
  categoryId?: string;
  file: File;
}

/**
 * Rapor yükler. Yanıt HEMEN döner ve durum "pending" olur — analiz arka
 * planda çalışıyor. Analizi görmek için `pollUntilAnalyzed` kullanın.
 */
export async function uploadReport(input: UploadReportInput): Promise<EvaluationReport> {
  const form = new FormData();
  form.append("project_name", input.projectName);
  if (input.competitionId) form.append("competition_id", input.competitionId);
  if (input.categoryId) form.append("category_id", input.categoryId);
  if (input.teamId) form.append("team_id", input.teamId);
  form.append("file", input.file);

  const wire = await apiFetch<WireReport>("/api/reports/upload", {
    method: "POST",
    formBody: form,
  });
  return toEvaluationReport(wire, await loadCategoryNames());
}

export interface SubmitDecisionInput {
  reportId: string;
  outcome: DecisionOutcome;
  finalScore: number;
  /** Hakemin gerekçesi. Backend alanın adı `rationale`, arayüzde `refereeNotes`. */
  rationale: string;
  /** Denetim izi: gerekçe AI taslağından mı geldi, hakem değiştirdi mi. */
  rationaleAiDrafted?: boolean;
  rationaleEditedByReferee?: boolean;
}

export async function submitDecision(input: SubmitDecisionInput): Promise<WireFinalDecision> {
  return apiFetch<WireFinalDecision>(
    `/api/reports/${encodeURIComponent(input.reportId)}/decision`,
    {
      method: "POST",
      json: {
        outcome: input.outcome,
        // Backend kolonu INTEGER; ondalık gönderilirse Pydantic reddeder.
        final_score: Math.round(input.finalScore),
        rationale: input.rationale,
        rationale_ai_drafted: input.rationaleAiDrafted ?? false,
        rationale_edited_by_referee: input.rationaleEditedByReferee ?? false,
      },
    },
  );
}

/**
 * Analizi ÇÖKMÜŞ bir raporun analizini yeniden çalıştırır (yönetici).
 *
 * Çökme çoğu zaman geçici (depolama kesintisi, geçici dosya hatası); tekrar
 * denemek raporu yeniden yüklemekten iyi, çünkü yeniden yükleme yeni bir
 * kayıt üretiyor ve eskisi sistemde asılı kalıyor.
 */
export async function reanalyzeReport(reportId: string): Promise<WireReport> {
  return apiFetch<WireReport>(
    `/api/reports/${encodeURIComponent(reportId)}/reanalyze`,
    { method: "POST" },
  );
}

/**
 * Raporun kendi dosyasını (PDF) getirir.
 *
 * Blob olarak indiriyoruz çünkü `<iframe src="...">` Authorization
 * başlığını GÖNDERMEZ — token'lı bir uç noktayı doğrudan iframe'e vermek
 * çalışmaz. Blob'dan üretilen object URL ise sorunsuz gömülebiliyor.
 * Çağıran taraf işi bitince `URL.revokeObjectURL` ÇAĞIRMALI.
 */
export async function fetchReportFile(reportId: string): Promise<{ url: string; blob: Blob }> {
  const blob = await apiFetchBlob(
    `/api/reports/${encodeURIComponent(reportId)}/file`,
  );
  return { url: URL.createObjectURL(blob), blob };
}

/** İndirme bağlantısı — tarayıcıya kaydettirir. */
export async function downloadReportFile(reportId: string, fileName: string): Promise<void> {
  const blob = await apiFetchBlob(
    `/api/reports/${encodeURIComponent(reportId)}/file?download=true`,
  );
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = fileName;
  document.body.appendChild(a);
  a.click();
  a.remove();
  // Object URL'i AYNI görevde iptal etmiyoruz.
  //
  // `a.click()` indirmeyi kuyruğa alıyor ama başlatmıyor; hemen ardından
  // `revokeObjectURL` çağrılırsa Firefox indirme daha okumaya başlamadan
  // bağlantıyı geçersizleştiriyor ve dosya boş/başarısız iniyor. Chrome
  // toleranslı olduğu için hata yalnızca bazı tarayıcılarda görünüyordu.
  // Bir sonraki göreve ertelemek indirmenin başlamasına zaman tanıyor;
  // yine de iptal ediyoruz ki blob bellekte kalmasın.
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

/* ------------------------------------------------------------ yarismalar */

export async function listCompetitions(): Promise<WireCompetition[]> {
  return apiFetch<WireCompetition[]>("/api/competitions");
}

export async function getCompetition(id: string): Promise<WireCompetition> {
  return apiFetch<WireCompetition>(`/api/competitions/${encodeURIComponent(id)}`);
}

export async function createCompetition(input: {
  name: string;
  description?: string;
  categoryId: string;
}): Promise<WireCompetition> {
  return apiFetch<WireCompetition>("/api/competitions", {
    method: "POST",
    json: {
      name: input.name,
      description: input.description || null,
      category_id: input.categoryId,
    },
  });
}

export interface TemplateInput {
  /** Bu sablonun ait oldugu rapor asamasi ("Kritik Tasarim Raporu" gibi). */
  reportTypeName?: string | null;
  acceptedLanguages: string[];
  requiredHeadings: string[];
  headingSynonyms?: Record<string, string[]>;
  minPages?: number | null;
  maxPages?: number | null;
  minSectionChars?: number | null;
}

/**
 * `confirmReanalysis`: yarışmada ZATEN ANALİZ EDİLMİŞ rapor varsa backend
 * HTTP 409 döner. Kuralları değiştirmek o raporları eski, yeni raporları
 * yeni ölçütle puanlardı; aynı yarışmada iki yarışmacı farklı kurallarla
 * değerlendirilmiş olurdu. Onay verilirse mevcut analizler silinip yeni
 * kurallarla yeniden çalıştırılıyor.
 */
export async function setCompetitionTemplate(
  id: string,
  t: TemplateInput,
  confirmReanalysis = false,
): Promise<WireCompetition> {
  return apiFetch<WireCompetition>(`/api/competitions/${encodeURIComponent(id)}/template`, {
    method: "PUT",
    json: {
      report_type_name: t.reportTypeName ?? null,
      accepted_languages: t.acceptedLanguages,
      required_headings: t.requiredHeadings,
      heading_synonyms: t.headingSynonyms ?? {},
      min_pages: t.minPages ?? null,
      max_pages: t.maxPages ?? null,
      min_section_chars: t.minSectionChars ?? null,
      confirm_reanalysis: confirmReanalysis,
    },
  });
}

/** `confirmReanalysis` için bkz. {@link setCompetitionTemplate}. */
export async function setCompetitionCriteria(
  id: string,
  criteria: { title: string; description?: string; weight: number }[],
  confirmReanalysis = false,
): Promise<WireCompetition> {
  return apiFetch<WireCompetition>(`/api/competitions/${encodeURIComponent(id)}/criteria`, {
    method: "PUT",
    json: {
      criteria: criteria.map((k) => ({
        title: k.title,
        description: k.description || null,
        weight: k.weight,
      })),
      confirm_reanalysis: confirmReanalysis,
    },
  });
}

export async function setCompetitionStatus(
  id: string,
  status: string,
): Promise<WireCompetition> {
  return apiFetch<WireCompetition>(`/api/competitions/${encodeURIComponent(id)}/status`, {
    method: "PUT",
    json: { status },
  });
}

/* ------------------------------------------------------------- atamalar */

export async function listReferees(competitionId?: string): Promise<WireReferee[]> {
  const q = competitionId ? `?competition_id=${encodeURIComponent(competitionId)}` : "";
  return apiFetch<WireReferee[]>(`/api/assignments/referees${q}`);
}

export async function addRefereeToCompetition(
  competitionId: string,
  refereeId: string,
): Promise<WireReferee> {
  return apiFetch<WireReferee>(
    `/api/assignments/competitions/${encodeURIComponent(competitionId)}/referees`,
    { method: "POST", json: { referee_id: refereeId } },
  );
}

export async function autoAssign(competitionId: string): Promise<WireAutoAssignResult> {
  return apiFetch<WireAutoAssignResult>(
    `/api/assignments/competitions/${encodeURIComponent(competitionId)}/auto-assign`,
    { method: "POST" },
  );
}

export async function reassignReport(reportId: string, refereeId: string) {
  return apiFetch(`/api/assignments/${encodeURIComponent(reportId)}`, {
    method: "PUT",
    json: { referee_id: refereeId },
  });
}

/* ------------------------------------------------- AI taslak gerekce */

export async function fetchRationaleDraft(reportId: string): Promise<WireRationaleDraft> {
  return apiFetch<WireRationaleDraft>(
    `/api/reports/${encodeURIComponent(reportId)}/rationale-draft`,
    { method: "POST" },
  );
}

/* --------------------------------------------------------------- pano */

export async function getDashboardStats(): Promise<WireDashboardStats> {
  return apiFetch<WireDashboardStats>("/api/dashboard/stats");
}

/* ------------------------------------------------------------ yoklama */

export interface PollOptions {
  intervalMs?: number;
  timeoutMs?: number;
  signal?: AbortSignal;
  categoryNames?: CategoryNameMap;
  /** Her denemeden sonra çağrılır — arayüzün "analiz sürüyor" durumunu tazelemesi için. */
  onTick?: (current: ReportWithAnalysis) => void;
}

/**
 * Analiz bitene kadar raporu yoklar.
 *
 * NEDEN GEREKLİ: `POST /api/reports/upload` yanıtı hemen dönüyor ve analiz
 * FastAPI BackgroundTasks ile yanıt gönderildikten SONRA çalışıyor. Gerçek
 * PDF'lerde bu birkaç saniye sürüyor. Yükleme sonrası tek bir GET atmak her
 * zaman "pending" görür — arayüzün beklemesi şart.
 *
 * "pending" DIŞINDAKİ ilk durumda durur; "error" da bir bitiş durumudur
 * (analiz çöktü) ve çağıran tarafın bunu görmesi gerekir.
 */
export async function pollUntilAnalyzed(
  reportId: string,
  options: PollOptions = {},
): Promise<ReportWithAnalysis> {
  const { intervalMs = 1500, timeoutMs = 120_000, signal, categoryNames, onTick } = options;
  const names = categoryNames ?? (await loadCategoryNames());
  const deadline = Date.now() + timeoutMs;

  let last: ReportWithAnalysis | null = null;
  for (;;) {
    if (signal?.aborted) throw new DOMException("Yoklama iptal edildi", "AbortError");

    last = await getReport(reportId, names, signal);
    onTick?.(last);

    if (last.rawStatus !== "pending") return last;
    if (Date.now() >= deadline) {
      throw new ApiError(
        408,
        "Analiz beklenenden uzun sürdü. Rapor yüklendi ve analiz arka planda " +
          "devam ediyor olabilir; sayfayı yenileyip tekrar bakın.",
      );
    }
    await sleep(intervalMs, signal);
  }
}

function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      signal?.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    function onAbort() {
      clearTimeout(timer);
      reject(new DOMException("Yoklama iptal edildi", "AbortError"));
    }
    signal?.addEventListener("abort", onAbort, { once: true });
  });
}
