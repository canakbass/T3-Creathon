/**
 * Canlı API verisinden yarışmacıya gösterilecek özeti kurar.
 *
 * GİZLİLİK SINIRI — DİKKAT:
 * Bu modül bir {@link PublishedEvaluation} üretir ve onu MUTLAKA
 * `toCompetitorSummary()` ile projekte eder. O fonksiyon alan alan bir
 * beyaz liste; nesne yayma (spread) KULLANMIYOR, böylece hakem-özel bir
 * alan yanlışlıkla yarışmacıya sızamıyor. Buradaki kod o projeksiyonu
 * ATLAMAMALI.
 *
 * Ayrıca benzerlik/intihal verisi bilinçli olarak yarışmacıya sunulan
 * anlatının DIŞINDA tutuluyor: `competitor-dashboard.test.tsx` bunu
 * doğruluyor ve `competitor-feedback.ts` similarityScore'u hakem-özel
 * alanlar arasında sayıyor.
 */

import { CHECK_DEFINITIONS, type AiAnalysis, type AiCheckKey } from "@/lib/ai-analysis";
import type { RefereeDecision } from "@/lib/api";
import {
  toCompetitorSummary,
  type CompetitorEvaluationSummary,
  type FeedbackPoint,
  type PublishedEvaluation,
} from "@/lib/competitor-feedback";
import type { DecisionOutcome } from "@/lib/final-decision";
import type { EvaluationReport } from "@/lib/mock-reports";

/**
 * Yarışmacıya gösterilebilecek kontroller.
 *
 * `similarity` KASITLI OLARAK YOK: intihal/benzerlik bulguları hakem-özel.
 * Bir yarışmacıya "şu raporla %X örtüşüyorsunuz" demek, hem başka bir
 * takımın başvurusu hakkında bilgi sızdırır hem de itiraz sürecini
 * hakemin elinden alır.
 */
const COMPETITOR_VISIBLE_CHECKS: AiCheckKey[] = [
  "languageTemplate",
  "contentHeading",
  "categoryMatch",
];

/** Bu eşiğin üstü güçlü yön, altı gelişim alanı sayılıyor (pozitif polarite). */
const STRENGTH_FLOOR = 85;
const IMPROVEMENT_CEILING = 85;

const OUTCOME_HEADLINES: Record<DecisionOutcome, string> = {
  approve: "Başvurunuz bir sonraki aşamaya ilerledi.",
  revise: "Başvurunuz revizyon sonrası yeniden değerlendirilecek.",
  reject: "Başvurunuz bu aşamada ilerleyemedi.",
};

const OUTCOME_NEXT_STEPS: Record<DecisionOutcome, string> = {
  approve:
    "Şu anda sizden bir işlem beklenmiyor. Takvim netleştiğinde bu panel üzerinden bilgilendirileceksiniz.",
  revise:
    "Aşağıdaki geliştirme alanlarını ele alıp raporunuzu güncelleyin ve yeniden gönderin.",
  reject:
    "Değerlendirme notlarını inceleyip bir sonraki dönem için raporunuzu güçlendirebilirsiniz.",
};

function toFeedbackPoint(key: AiCheckKey, analysis: AiAnalysis): FeedbackPoint {
  const definition = CHECK_DEFINITIONS[key];
  const result = analysis.results[key];
  return {
    title: definition.label,
    // Özet + bulgular birleştiriliyor: özet tek cümlelik başlık, bulgular
    // ise somut gerekçe. Yarışmacıya "neden" göstermeden puan vermek
    // gelişim odaklı geri bildirim sayılmaz.
    detail: [result.summary, ...result.findings].filter(Boolean).join(" "),
  };
}

/**
 * Rapor + analiz + hakem kararından yarışmacı özeti üretir.
 *
 * Karar henüz verilmediyse null döner — yarışmacı yalnızca NİHAİ sonucu
 * görmeli; hakem kararını vermeden AI önerisini yarışmacıya göstermek,
 * "AI karar verici değildir" ilkesini ihlal ederdi.
 */
export function buildCompetitorSummary(input: {
  report: EvaluationReport;
  analysis: AiAnalysis | null;
  decision: RefereeDecision | null;
}): CompetitorEvaluationSummary | null {
  const { report, analysis, decision } = input;
  if (!decision) return null;

  const strengths: FeedbackPoint[] = [];
  const improvements: FeedbackPoint[] = [];

  if (analysis) {
    for (const key of COMPETITOR_VISIBLE_CHECKS) {
      const score = analysis.results[key]?.score ?? 0;
      if (score >= STRENGTH_FLOOR) {
        strengths.push(toFeedbackPoint(key, analysis));
      } else if (score < IMPROVEMENT_CEILING) {
        improvements.push(toFeedbackPoint(key, analysis));
      }
    }
  }

  // Hakemin kendi gerekçesi yarışmacıya gösterilir; bu, kararın
  // dayanağıdır ve gizli bir not değildir (hakem-özel `refereeNotes`
  // alanı ayrı tutuluyor).
  if (decision.rationale.trim()) {
    improvements.push({
      title: "Hakem değerlendirmesi",
      detail: decision.rationale.trim(),
    });
  }

  const published: PublishedEvaluation = {
    reportId: report.reportId,
    projectName: report.projectName,
    category: report.category,
    submittedAt: report.submissionDate,
    reviewedAt: decision.submittedAt,
    outcome: decision.outcome,
    finalScore: decision.finalScore,

    // Hakem-özel alanlar. Bunlar `toCompetitorSummary` tarafından
    // projeksiyonun DIŞINDA bırakılıyor - burada doldurulmaları,
    // beyaz listenin gerçekten çalıştığının da bir denetimi.
    refereeName: "",
    refereeNotes: "",
    aiSuggestedScore: analysis?.suggestion.score ?? 0,
    aiSuggestedOutcome: analysis?.suggestion.outcome ?? "revise",
    similarityScore: analysis?.results.similarity?.score ?? 0,

    message: {
      headline: OUTCOME_HEADLINES[decision.outcome],
      strengths,
      improvements,
      nextStep: OUTCOME_NEXT_STEPS[decision.outcome],
    },
  };

  // TEK ÇIKIŞ YOLU: beyaz liste projeksiyonu.
  return toCompetitorSummary(published);
}
