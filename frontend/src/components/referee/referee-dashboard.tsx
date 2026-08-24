"use client";

import { useCallback, useEffect, useState } from "react";
import { listReports } from "@/lib/api";
import { describeError } from "@/lib/api/errors";
import type { EvaluationReport } from "@/lib/mock-reports";
import { ReportList } from "./report-list";
import { ReportListSkeleton } from "./report-list-skeleton";
import { ReportDetail } from "./report-detail";

interface RefereeDashboardProps {
  /** Provide directly (e.g. in tests) to skip the network fetch entirely. */
  initialReports?: EvaluationReport[];
  /** @deprecated Sahte gecikme kaldirildi; artik gercek API cagriliyor. */
  loadingDelayMs?: number;
}

export function RefereeDashboard({ initialReports }: RefereeDashboardProps) {
  const [reports, setReports] = useState<EvaluationReport[] | null>(
    initialReports ?? null,
  );
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setReports(await listReports());
    } catch (cause) {
      setError(describeError(cause));
      // Liste null kalirsa iskelet sonsuza kadar doner; bos diziye
      // cekiyoruz ki hata mesaji gorunur olsun.
      setReports([]);
    }
  }, []);

  useEffect(() => {
    if (initialReports) return;
    void load();
  }, [initialReports, load]);

  const selectedReport =
    reports?.find((report) => report.reportId === selectedId) ?? null;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold text-foreground">Değerlendirme Raporları</h2>
          <p className="mt-1 text-sm text-muted">
            Gönderilen projeleri inceleyin ve AI destekli değerlendirme durumunu takip edin.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void load()}
          data-testid="refresh-reports"
          className="rounded-lg border border-border bg-surface px-3 py-1.5 text-sm font-semibold text-muted transition hover:border-brand-300 hover:text-brand-700"
        >
          Yenile
        </button>
      </div>

      {error ? (
        <div
          role="alert"
          data-testid="reports-error"
          className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-medium text-rose-700"
        >
          {error}
        </div>
      ) : null}

      <div className="flex flex-col gap-6 lg:flex-row lg:items-start">
        <aside className="w-full overflow-hidden rounded-2xl border border-border bg-surface shadow-sm lg:w-96 lg:shrink-0">
          <div className="border-b border-border px-4 py-3">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted">
              {reports ? `${reports.length} rapor` : "Raporlar yükleniyor"}
            </p>
          </div>
          {reports === null ? (
            <ReportListSkeleton />
          ) : (
            <ReportList reports={reports} selectedId={selectedId} onSelect={setSelectedId} />
          )}
        </aside>

        <div className="min-w-0 flex-1">
          {reports === null ? (
            <div
              data-testid="report-detail-skeleton"
              aria-hidden="true"
              className="h-64 animate-pulse rounded-2xl border border-border bg-slate-100"
            />
          ) : (
            <ReportDetail report={selectedReport} />
          )}
        </div>
      </div>
    </div>
  );
}
