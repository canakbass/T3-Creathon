"use client";

import Link from "next/link";
import type { AiAnalysis } from "@/lib/ai-analysis";
import type { EvaluationReport } from "@/lib/mock-reports";
import type { FinalDecisionSubmission } from "@/lib/final-decision";
import { formatDate } from "@/lib/format";
import { AiAnalysisReport } from "./ai-analysis-report";
import { FinalDecisionForm } from "./final-decision-form";
import { StatusBadge } from "./status-badge";

interface RefereeReportDetailProps {
  report: EvaluationReport;
  analysis: AiAnalysis | null;
  /** Promise dönebilir; reddedilirse form "kaydedildi" göstermez. */
  onSubmitDecision?: (submission: FinalDecisionSubmission) => void | Promise<void>;
  /** Bu rapora daha önce karar verilmişse form kilitlenir. */
  decisionAlreadySubmitted?: boolean;
}

export function RefereeReportDetail({
  report,
  analysis,
  onSubmitDecision,
  decisionAlreadySubmitted,
}: RefereeReportDetailProps) {
  return (
    <div className="flex flex-col gap-6" data-testid="referee-report-detail">
      <Link
        href="/dashboard/referee"
        className="inline-flex w-fit items-center gap-1.5 text-sm font-semibold text-muted transition hover:text-brand-700"
      >
        <span aria-hidden="true">←</span> Tüm raporlara dön
      </Link>

      <header className="rounded-2xl border border-border bg-surface p-6 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-muted">
              {report.reportId}
            </p>
            <h1 className="mt-1 text-2xl font-extrabold text-foreground">
              {report.projectName}
            </h1>
          </div>
          <StatusBadge status={report.status} />
        </div>

        <dl className="mt-5 grid grid-cols-1 gap-4 border-t border-border pt-5 sm:grid-cols-3">
          <div>
            <dt className="text-xs font-semibold uppercase tracking-wide text-muted">
              Kategori
            </dt>
            <dd className="mt-1 text-sm font-semibold text-foreground">{report.category}</dd>
          </div>
          <div>
            <dt className="text-xs font-semibold uppercase tracking-wide text-muted">
              Gönderim Tarihi
            </dt>
            <dd className="mt-1 text-sm font-semibold text-foreground">
              {formatDate(report.submissionDate)}
            </dd>
          </div>
          <div>
            <dt className="text-xs font-semibold uppercase tracking-wide text-muted">
              Analiz
            </dt>
            <dd className="mt-1 text-sm font-semibold text-foreground">
              {analysis ? "Tamamlandı" : "Sırada"}
            </dd>
          </div>
        </dl>
      </header>

      {analysis ? (
        <>
          <AiAnalysisReport analysis={analysis} />
          <FinalDecisionForm
            reportId={report.reportId}
            suggestion={analysis.suggestion}
            onSubmitDecision={onSubmitDecision}
            decisionAlreadySubmitted={decisionAlreadySubmitted}
          />
        </>
      ) : (
        <section
          data-testid="analysis-pending"
          className="flex flex-col items-center gap-2 rounded-2xl border border-dashed border-border px-6 py-16 text-center"
        >
          <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-slate-100 text-muted">
            <svg viewBox="0 0 24 24" fill="none" className="h-5 w-5" aria-hidden="true">
              <circle cx="12" cy="12" r="8.5" stroke="currentColor" strokeWidth="1.5" />
              <path
                d="M12 7.5V12l3 2"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </span>
          <p className="text-sm font-semibold text-foreground">Analiz devam ediyor</p>
          <p className="max-w-sm text-xs leading-relaxed text-muted">
            Değerlendirme motoru bu başvuruyu işlemeyi henüz tamamlamadı. İşlem
            tamamlandığında güven puanları ve AI Dördüncü Göz önerisi burada görünecektir.
          </p>
        </section>
      )}
    </div>
  );
}
