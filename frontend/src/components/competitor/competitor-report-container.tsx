"use client";

import { useEffect, useState } from "react";
import { getReport, listReports, loadCategoryNames } from "@/lib/api";
import { describeError } from "@/lib/api/errors";
import { buildCompetitorSummary } from "@/lib/competitor-view";
import type { CompetitorEvaluationSummary } from "@/lib/competitor-feedback";
import { CompetitorDashboard } from "./competitor-dashboard";

/**
 * Yarışmacının kendi başvurusunun sonucunu canlı API'den yükler.
 *
 * Backend zaten rol bazlı filtreleme yapıyor: `GET /api/reports`,
 * COMPETITOR rolü için yalnızca kullanıcının kendi raporlarını döndürüyor
 * (backend/app/routes/reports.py). Yani yanlış bir raporu görme riski
 * sunucu tarafında da kapalı.
 */
export function CompetitorReportContainer() {
  const [summary, setSummary] = useState<CompetitorEvaluationSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    (async () => {
      try {
        const [reports, names] = await Promise.all([listReports(), loadCategoryNames()]);
        if (cancelled) return;

        if (reports.length === 0) {
          setSummary(null);
          return;
        }

        // En son gönderilen rapordan geriye doğru, hakem kararı verilmiş
        // ilkini gösteriyoruz. Karar verilmemiş raporlar yarışmacıya
        // gösterilmiyor - AI önerisi hakem onaylamadan sonuç değildir.
        const sorted = [...reports].sort((a, b) =>
          b.submissionDate.localeCompare(a.submissionDate),
        );

        for (const candidate of sorted) {
          const detail = await getReport(candidate.reportId, names);
          if (cancelled) return;
          const built = buildCompetitorSummary({
            report: detail.report,
            analysis: detail.analysis,
            decision: detail.decision,
          });
          if (built) {
            setSummary(built);
            return;
          }
        }
        setSummary(null);
      } catch (cause) {
        if (!cancelled) setError(describeError(cause));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  if (loading) {
    return (
      <div
        data-testid="competitor-loading"
        aria-hidden="true"
        className="h-64 animate-pulse rounded-2xl border border-border bg-slate-100"
      />
    );
  }

  if (error) {
    return (
      <div
        role="alert"
        data-testid="competitor-error"
        className="rounded-2xl border border-rose-200 bg-rose-50 px-6 py-8 text-center text-sm font-medium text-rose-700"
      >
        {error}
      </div>
    );
  }

  if (!summary) {
    return (
      <div
        data-testid="competitor-empty"
        className="flex flex-col items-center gap-2 rounded-2xl border border-dashed border-border px-6 py-16 text-center"
      >
        <p className="text-sm font-semibold text-foreground">Henüz açıklanmış bir sonuç yok</p>
        <p className="max-w-md text-xs leading-relaxed text-muted">
          Raporunuz değerlendirme sırasında. Hakem nihai kararını verdiğinde sonucunuz,
          güçlü yönleriniz ve gelişim önerileriniz burada görünecek.
        </p>
      </div>
    );
  }

  return <CompetitorDashboard summary={summary} />;
}
