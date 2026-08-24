/**
 * Backend'in gönderdiği (snake_case, düz) gövdeleri arayüzün beklediği
 * (camelCase, iç içe) tiplere çevirir.
 *
 * NEDEN AYRI BİR KATMAN: iki taraf birbirinden habersiz geliştirildi ve
 * şekilleri üç ayrı noktada ayrışıyor:
 *   1. isimlendirme  — `project_name` vs `projectName`
 *   2. yuvalama      — backend `suggested_score/outcome/rationale`'ı DÜZ verir,
 *                      arayüz `suggestion: {score, outcome, rationale}` bekler
 *   3. kimlik        — backend `category_id` verir, arayüz kategori ADI gösterir
 * Bu çeviriyi bileşenlerin içine dağıtmak yerine tek yerde tutuyoruz;
 * böylece backend şeması değişirse tek dosya güncelleniyor.
 */

import { CHECK_KEYS, type AiAnalysis, type AiCheckKey, type AiCheckResult } from "@/lib/ai-analysis";
import { DECISION_OUTCOMES, type DecisionOutcome } from "@/lib/final-decision";
import type { EvaluationReport, ReportStatus } from "@/lib/mock-reports";
import { REPORT_STATUSES } from "@/lib/mock-reports";
import type { WireAiAnalysis, WireCategory, WireReport } from "./types";

/** Kategori kimliği -> görünen ad. Kategoriler API'den bir kez çekilip kurulur. */
export type CategoryNameMap = ReadonlyMap<string, string>;

export function buildCategoryNameMap(categories: WireCategory[]): CategoryNameMap {
  return new Map(categories.map((c) => [c.id, c.name]));
}

/**
 * Backend'den gelen serbest metni arayüzün kapalı `ReportStatus` birleşimine
 * indirger. Tanınmayan bir durum gelirse "pending"e düşüyoruz: bilinmeyen bir
 * değeri olduğu gibi geçirmek, `StatusBadge` gibi bileşenlerde `undefined`
 * etiket üretirdi.
 */
export function toReportStatus(raw: string): ReportStatus {
  return (REPORT_STATUSES as readonly string[]).includes(raw)
    ? (raw as ReportStatus)
    : "pending";
}

/**
 * `suggested_outcome` veri tabanında serbest bir metin kolonu. Arayüzde ise
 * `DECISION_LABELS[outcome]` ile etikete çevriliyor; tanınmayan bir değer
 * ekranda "undefined" gösterirdi. Bu yüzden doğrulayıp güvenli bir varsayılana
 * düşüyoruz.
 */
export function toDecisionOutcome(raw: string): DecisionOutcome {
  return (DECISION_OUTCOMES as readonly string[]).includes(raw)
    ? (raw as DecisionOutcome)
    : "revise";
}

export function toEvaluationReport(
  wire: WireReport,
  categoryNames?: CategoryNameMap,
): EvaluationReport {
  return {
    reportId: wire.id,
    projectName: wire.project_name,
    // Kategori adı çözülemezse kimliği gösteriyoruz - boş bırakmaktansa
    // hakemin en azından hangi kategori olduğunu takip edebilmesi daha iyi.
    category: categoryNames?.get(wire.category_id) ?? wire.category_id,
    status: toReportStatus(wire.status),
    submissionDate: wire.submission_date,
  };
}

/**
 * Tek bir kontrolü (languageTemplate, similarity, ...) arayüz tipine çevirir.
 *
 * `summary` backend'de nullable bir kolon ama arayüzde zorunlu `string`.
 * Null gelirse boş metin yerine açıklayıcı bir cümle koyuyoruz, çünkü bu alan
 * doğrudan hakem kartında gösteriliyor.
 */
function toCheckResult(raw: WireAiAnalysis["results"][string] | undefined): AiCheckResult {
  return {
    score: clampScore(raw?.score),
    summary: raw?.summary?.trim() || "Bu kontrol için özet üretilmedi.",
    findings: Array.isArray(raw?.findings) ? raw.findings.filter((f) => typeof f === "string") : [],
  };
}

/** Puanı 0-100'e sıkıştırır: `ConfidenceRing` bunun dışına çıkan değerde bozuluyor. */
function clampScore(value: unknown): number {
  const n = typeof value === "number" && Number.isFinite(value) ? value : 0;
  return Math.max(0, Math.min(100, Math.round(n)));
}

/**
 * Analiz gövdesini çevirir. Rapor henüz analiz edilmediyse backend
 * `ai_analysis: null` döner ve arayüz bu durumda "Analiz devam ediyor"
 * ekranını gösterir — bu yüzden null'ı olduğu gibi geçiriyoruz.
 */
export function toAiAnalysis(wire: WireAiAnalysis | null | undefined): AiAnalysis | null {
  if (!wire) return null;

  // `results` backend'de açık bir sözlük; arayüzdeki `Record<AiCheckKey, ...>`
  // ise TAM olmak zorunda. Dört anahtarı da kendimiz kuruyoruz ki eksik gelen
  // bir kontrol arayüzde `undefined.score` ile çökmesin.
  const results = Object.fromEntries(
    CHECK_KEYS.map((key) => [key, toCheckResult(wire.results?.[key])]),
  ) as Record<AiCheckKey, AiCheckResult>;

  return {
    reportId: wire.report_id,
    analyzedAt: wire.analyzed_at,
    engineVersion: wire.engine_version,
    results,
    // Backend bu üçünü DÜZ veriyor, arayüz iç içe bekliyor.
    suggestion: {
      score: clampScore(wire.suggested_score),
      outcome: toDecisionOutcome(wire.suggested_outcome),
      rationale: wire.rationale ?? "",
    },
  };
}
