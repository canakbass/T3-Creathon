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
import { apiFetch, ApiError } from "./client";
import {
  buildCategoryNameMap,
  toAiAnalysis,
  toDecisionOutcome,
  toEvaluationReport,
  type CategoryNameMap,
} from "./mappers";
import type {
  WireCategory,
  WireDashboardStats,
  WireFinalDecision,
  WireReport,
  WireToken,
  WireUser,
} from "./types";

export { ApiError, API_BASE_URL, NetworkError } from "./client";
export type { CategoryNameMap } from "./mappers";

/* ------------------------------------------------------------------ auth */

export interface LoggedInUser {
  id: string;
  email: string;
  role: string;
  token: string;
}

/**
 * Gerçek JWT girişi.
 *
 * Backend `OAuth2PasswordRequestForm` kullanıyor, yani gövde JSON DEĞİL
 * form-encoded ve e-posta alanının adı `username` (OAuth2 standardı böyle).
 * Bu, kolayca gözden kaçan bir ayrıntı — JSON gönderilse 422 alınır.
 */
export async function login(email: string, password: string): Promise<LoggedInUser> {
  const form = new URLSearchParams({ username: email, password });
  const token = await apiFetch<WireToken>("/api/auth/login", {
    method: "POST",
    formBody: form,
    skipAuth: true,
  });

  // Rolü token'ın içini çözerek DEĞİL, /me'ye sorarak alıyoruz: JWT gövdesi
  // arayüzde doğrulanamaz, sunucunun söylediği role güvenmek doğru olan.
  // Token henüz store'a yazılmadığı için elle geçiyoruz.
  const user = await apiFetch<WireUser>("/api/auth/me", { token: token.access_token });

  return { id: user.id, email: user.email, role: user.role, token: token.access_token };
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

export async function getReport(
  reportId: string,
  categoryNames?: CategoryNameMap,
): Promise<ReportWithAnalysis> {
  const names = categoryNames ?? (await loadCategoryNames());
  const wire = await apiFetch<WireReport>(`/api/reports/${encodeURIComponent(reportId)}`);
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

export interface UploadReportInput {
  projectName: string;
  categoryId: string;
  file: File;
}

/**
 * Rapor yükler. Yanıt HEMEN döner ve durum "pending" olur — analiz arka
 * planda çalışıyor. Analizi görmek için `pollUntilAnalyzed` kullanın.
 */
export async function uploadReport(input: UploadReportInput): Promise<EvaluationReport> {
  const form = new FormData();
  form.append("project_name", input.projectName);
  form.append("category_id", input.categoryId);
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
      },
    },
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

    last = await getReport(reportId, names);
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
