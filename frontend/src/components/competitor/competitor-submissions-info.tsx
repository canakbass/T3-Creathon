"use client";

import { useCallback, useEffect, useState } from "react";
import { listReportRows, type ReportRow } from "@/lib/api";
import { describeError } from "@/lib/api/errors";
import { StatusBadge } from "@/components/referee/status-badge";
import { formatDate } from "@/lib/format";

/**
 * Yarışmacının başvurularını LİSTELEDİĞİ ekran — yüklemediği ekran.
 *
 * NEDEN YÜKLEME YOK: şartname AKIŞ 03 (Yarışmacı) şöyle: "Değerlendirme
 * tamamlanır → sonucunu görüntüler → güçlü ve gelişime açık yönlerini
 * inceler → önerileri görür." Yükleme adımı YOK. Yükleme AKIŞ 01'de,
 * Yarışma Yöneticisi'nde: "raporları sisteme aktarır".
 *
 * Gerçek hayatta da böyle: raporlar TEKNOFEST'in kendi sistemine
 * (KYS / t3kys.com) teslim ediliyor, buraya değil. Bu sistem o raporları
 * değerlendiren yardımcı katman, toplama noktası değil.
 *
 * Bu bileşen önceden `CompetitorSubmission` idi ve gerçekten yükleme
 * yapıyordu. Yükleme kaldırıldı ama panel silinmedi: yarışmacı "raporum
 * nerede, neden yükleyemiyorum" diye aramasın — nereden geldiği burada
 * yazıyor.
 */
export function CompetitorSubmissionsInfo({
  initialReports,
}: {
  initialReports?: ReportRow[];
}) {
  const [raporlarim, setRaporlarim] = useState<ReportRow[]>(initialReports ?? []);
  const [error, setError] = useState<string | null>(null);
  const [yuklendi, setYuklendi] = useState(Boolean(initialReports));

  const yukle = useCallback(async () => {
    setError(null);
    try {
      setRaporlarim(await listReportRows());
    } catch (cause) {
      setError(describeError(cause));
    } finally {
      setYuklendi(true);
    }
  }, []);

  useEffect(() => {
    if (initialReports) return;
    void yukle();
  }, [initialReports, yukle]);

  return (
    <section
      data-testid="competitor-submissions"
      className="rounded-2xl border border-border bg-surface p-6 shadow-sm"
    >
      <h2 className="text-lg font-bold text-foreground">Başvurularım</h2>
      <p className="mt-1 text-sm text-muted">
        Takımınız adına sisteme aktarılan raporlar burada listelenir.
      </p>

      <div
        data-testid="competitor-upload-notice"
        className="mt-4 rounded-xl border border-brand-200 bg-brand-50/60 px-4 py-3 text-xs leading-relaxed text-brand-800"
      >
        <p className="font-semibold">Rapor yükleme bu ekranda yapılmaz.</p>
        <p className="mt-1">
          Raporlar yarışmanın kendi başvuru sistemine teslim edilir; yarışma
          yöneticisi değerlendirme için buraya aktarır. Bu sistem raporları
          <strong> değerlendiren</strong> katman, teslim alan katman değil.
        </p>
        <p className="mt-1">
          Takımınızın raporu aktarıldığında burada görünür ve değerlendirme
          tamamlandığında sonucunuzu, güçlü yönlerinizi ve gelişim önerilerinizi
          görebilirsiniz.
        </p>
      </div>

      {error ? (
        <div
          role="alert"
          data-testid="competitor-submissions-error"
          className="mt-4 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-medium text-rose-700"
        >
          {error}
        </div>
      ) : null}

      {!yuklendi ? (
        <div
          data-testid="competitor-submissions-loading"
          aria-hidden="true"
          className="mt-4 h-20 animate-pulse rounded-xl border border-border bg-slate-100"
        />
      ) : raporlarim.length === 0 ? (
        <p
          data-testid="competitor-no-submissions"
          className="mt-4 rounded-xl border border-dashed border-border px-4 py-6 text-center text-sm text-muted"
        >
          Takımınız adına henüz rapor aktarılmamış.
        </p>
      ) : (
        <ul className="mt-4 flex flex-col gap-2" data-testid="competitor-submission-list">
          {raporlarim.map((satir) => (
            <li
              key={satir.report.reportId}
              data-testid={`competitor-submission-${satir.report.reportId}`}
              className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-border px-4 py-3"
            >
              <span className="min-w-0">
                <span className="block truncate text-sm font-semibold text-foreground">
                  {satir.report.projectName}
                </span>
                <span className="block text-xs text-muted">
                  {satir.report.reportId}
                  {satir.teamName ? ` · ${satir.teamName}` : ""} ·{" "}
                  {formatDate(satir.report.submissionDate)}
                </span>
              </span>
              <StatusBadge status={satir.report.status} />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
