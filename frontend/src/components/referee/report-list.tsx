"use client";

import type { KeyboardEvent } from "react";
import type { EvaluationReport } from "@/lib/mock-reports";
import { formatDate } from "@/lib/format";
import { StatusBadge } from "./status-badge";

interface ReportListProps {
  reports: EvaluationReport[];
  selectedId: string | null;
  onSelect: (reportId: string) => void;
  /**
   * Liste boşken gösterilecek başlık ve açıklama.
   *
   * NEDEN PROP: varsayılan metin ("Henüz rapor yok") hakem panosunda artık
   * yanıltıcı. Hakem yalnızca KENDİSİNE ATANMIŞ raporları görüyor; sistemde
   * onlarca rapor olabilir ama hiçbiri ona atanmamışsa liste boş gelir.
   * "Henüz rapor yok" cümlesi bu durumda hakemi "kimse başvurmamış" ya da
   * "sistem bozuk" sonucuna götürür — oysa yapması gereken şey yöneticiden
   * atama istemek.
   */
  emptyTitle?: string;
  emptyHint?: string;
}

export function ReportList({
  reports,
  selectedId,
  onSelect,
  emptyTitle = "Henüz rapor yok",
  emptyHint = "Gönderilen değerlendirme raporları burada görünecek.",
}: ReportListProps) {
  if (reports.length === 0) {
    return (
      <div
        data-testid="report-list-empty"
        className="flex flex-col items-center gap-2 px-6 py-16 text-center"
      >
        <span className="flex h-10 w-10 items-center justify-center rounded-full bg-slate-100 text-muted">
          <svg viewBox="0 0 24 24" fill="none" className="h-5 w-5" aria-hidden="true">
            <path
              d="M7 3h7l5 5v13a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Z"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinejoin="round"
            />
            <path d="M14 3v5h5" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
          </svg>
        </span>
        <p className="text-sm font-semibold text-foreground">{emptyTitle}</p>
        <p className="text-xs text-muted">{emptyHint}</p>
      </div>
    );
  }

  function handleKeyDown(event: KeyboardEvent<HTMLLIElement>, reportId: string) {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onSelect(reportId);
    }
  }

  return (
    <ul role="listbox" aria-label="Değerlendirme Raporları" className="divide-y divide-border">
      {reports.map((report) => {
        const isSelected = report.reportId === selectedId;
        return (
          <li
            key={report.reportId}
            role="option"
            aria-selected={isSelected}
            tabIndex={0}
            data-testid={`report-row-${report.reportId}`}
            onClick={() => onSelect(report.reportId)}
            onKeyDown={(event) => handleKeyDown(event, report.reportId)}
            className={`flex cursor-pointer flex-col gap-1.5 border-l-2 px-4 py-4 transition hover:bg-slate-50 focus:outline-none focus-visible:bg-slate-50 ${
              isSelected ? "border-brand-600 bg-brand-50/60" : "border-transparent"
            }`}
          >
            <div className="flex items-start justify-between gap-2">
              <span
                className={`text-sm font-semibold ${isSelected ? "text-brand-700" : "text-foreground"}`}
              >
                {report.projectName}
              </span>
              <StatusBadge status={report.status} />
            </div>
            <span className="text-xs text-muted">{report.category}</span>
            <span className="text-xs text-muted">
              {report.reportId} · {formatDate(report.submissionDate)}
            </span>
          </li>
        );
      })}
    </ul>
  );
}
