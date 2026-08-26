import {
  getCheckTone,
  getChecks,
  getOverallConfidence,
  getToneLabel,
  type AiAnalysis,
} from "@/lib/ai-analysis";
import { formatDate } from "@/lib/format";
import { ConfidenceRing } from "./confidence-ring";
import { TonePill } from "./tone-pill";

interface AiAnalysisReportProps {
  analysis: AiAnalysis;
}

export function AiAnalysisReport({ analysis }: AiAnalysisReportProps) {
  const checks = getChecks(analysis);
  const overall = getOverallConfidence(analysis);

  return (
    <section
      aria-labelledby="ai-analysis-heading"
      data-testid="ai-analysis-report"
      className="rounded-2xl border border-border bg-surface p-6 shadow-sm"
    >
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-border pb-5">
        <div>
          <h2 id="ai-analysis-heading" className="text-lg font-bold text-foreground">
            AI Analiz Raporu
          </h2>
          <p className="mt-1 text-sm text-muted">
            {analysis.engineVersion} · {formatDate(analysis.analyzedAt)} tarihinde analiz edildi
          </p>
        </div>
        <div className="flex items-center gap-3 rounded-xl border border-border bg-background px-4 py-2">
          <span className="text-xs font-semibold uppercase tracking-wide text-muted">
            Genel güven
          </span>
          <span
            data-testid="overall-confidence"
            className="text-lg font-extrabold tabular-nums text-brand-700"
          >
            {overall}%
          </span>
        </div>
      </div>

      <ul className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2">
        {checks.map((check) => {
          const tone = getCheckTone(check.score, check.polarity);
          return (
            <li
              key={check.key}
              data-testid={`ai-check-${check.key}`}
              className="flex flex-col gap-4 rounded-xl border border-border bg-background p-4"
            >
              <div className="flex items-start gap-4">
                <ConfidenceRing label={check.label} value={check.score} tone={tone} />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="text-sm font-bold text-foreground">{check.shortLabel}</h3>
                    <TonePill tone={tone} testId={`ai-check-pill-${check.key}`}>
                      {getToneLabel(check.score, check.polarity)}
                    </TonePill>
                  </div>
                  <p className="mt-1.5 text-xs leading-relaxed text-muted">{check.summary}</p>
                </div>
              </div>

              <ul className="flex flex-col gap-1.5 border-t border-border pt-3">
                {/* Anahtar SIRA + metin: bulgular AI'dan geliyor ve ayni
                    cumle iki kez cikabilir (orn. iki bolumde ayni eksik
                    baslik). Metni tek basina anahtar yapmak, hakemin
                    bulgulardan birini HIC gormemesine yol acardi. */}
                {check.findings.map((finding, sira) => (
                  <li
                    key={`${sira}-${finding}`}
                    className="flex gap-2 text-xs leading-relaxed text-muted"
                  >
                    <span aria-hidden="true" className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-slate-300" />
                    {finding}
                  </li>
                ))}
              </ul>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
