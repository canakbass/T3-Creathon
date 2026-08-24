"use client";

import { useCallback, useEffect, useState } from "react";
import { listCompetitions, listReportRows, type ReportRow } from "@/lib/api";
import { describeError } from "@/lib/api/errors";
import type { WireCompetition } from "@/lib/api/types";
import { ReportUpload } from "@/components/manager/report-upload";
import { StatusBadge } from "@/components/referee/status-badge";
import { formatDate } from "@/lib/format";

/**
 * Yarışmacının kendi başvurusunu yaptığı ekran.
 *
 * NEDEN VAR: önceden yükleme YALNIZCA yönetici panelinde vardı — yani
 * yarışma yöneticisi her raporu elle yüklemek zorundaydı. Artık yarışmacı
 * kendi raporunu gönderiyor ve AI analizi otomatik başlıyor.
 *
 * Yükleme yalnızca BAŞVURUSU AÇIK yarışmalar için mümkün; backend de bunu
 * ayrıca doğruluyor (yarışma aşaması 'open' değilse 400 döner).
 */
export function CompetitorSubmission({
  initialCompetitions,
  initialReports,
}: {
  initialCompetitions?: WireCompetition[];
  initialReports?: ReportRow[];
}) {
  const [yarismalar, setYarismalar] = useState<WireCompetition[]>(
    initialCompetitions ?? [],
  );
  const [raporlarim, setRaporlarim] = useState<ReportRow[]>(initialReports ?? []);
  const [seciliId, setSeciliId] = useState<string>(initialCompetitions?.[0]?.id ?? "");
  const [error, setError] = useState<string | null>(null);
  const [yuklendi, setYuklendi] = useState(Boolean(initialCompetitions));

  const yukle = useCallback(async () => {
    setError(null);
    try {
      const [y, r] = await Promise.all([listCompetitions(), listReportRows()]);
      // Yalnızca başvurusu açık olanlara gönderim yapılabilir.
      const acik = y.filter((x) => x.status === "open");
      setYarismalar(acik);
      setSeciliId((mevcut) => mevcut || acik[0]?.id || "");
      setRaporlarim(r);
    } catch (cause) {
      setError(describeError(cause));
    } finally {
      setYuklendi(true);
    }
  }, []);

  useEffect(() => {
    if (initialCompetitions && initialReports) return;
    void yukle();
  }, [initialCompetitions, initialReports, yukle]);

  if (!yuklendi) {
    return (
      <div
        data-testid="submission-loading"
        aria-hidden="true"
        className="h-48 animate-pulse rounded-2xl border border-border bg-slate-100"
      />
    );
  }

  const secili = yarismalar.find((y) => y.id === seciliId) ?? null;

  return (
    <div className="flex flex-col gap-6" data-testid="competitor-submission">
      {error ? (
        <div
          role="alert"
          data-testid="submission-error"
          className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-medium text-rose-700"
        >
          {error}
        </div>
      ) : null}

      {/* --- Gönderilmiş raporlarım --- */}
      {raporlarim.length > 0 ? (
        <section className="rounded-2xl border border-border bg-surface p-6 shadow-sm">
          <h2 className="text-lg font-bold text-foreground">Başvurularım</h2>
          <ul className="mt-4 flex flex-col gap-2" data-testid="my-reports">
            {raporlarim.map((satir) => (
              <li
                key={satir.report.reportId}
                className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border px-4 py-3"
              >
                <span className="min-w-0">
                  <span className="block truncate text-sm font-semibold text-foreground">
                    {satir.report.projectName}
                  </span>
                  <span className="block text-xs text-muted">
                    {satir.report.reportId} · {formatDate(satir.report.submissionDate)}
                  </span>
                </span>
                <StatusBadge status={satir.report.status} />
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {/* --- Yeni başvuru --- */}
      {yarismalar.length === 0 ? (
        <section
          data-testid="no-open-competitions"
          className="flex flex-col items-center gap-2 rounded-2xl border border-dashed border-border px-6 py-12 text-center"
        >
          <p className="text-sm font-semibold text-foreground">
            Şu anda başvuruya açık yarışma yok
          </p>
          <p className="max-w-md text-xs leading-relaxed text-muted">
            Bir yarışmanın başvuruları açıldığında burada görünecek ve raporunuzu
            yükleyebileceksiniz.
          </p>
        </section>
      ) : (
        <>
          <section className="rounded-2xl border border-border bg-surface p-6 shadow-sm">
            <h2 className="text-lg font-bold text-foreground">Yeni Başvuru</h2>
            <p className="mt-1 text-sm text-muted">
              Başvurusu açık bir yarışma seçip raporunuzu yükleyin. Yükleme
              tamamlandığında AI ön analizi otomatik başlar.
            </p>
            <label className="mt-4 flex max-w-md flex-col gap-1.5">
              <span className="text-xs font-semibold uppercase tracking-wide text-muted">
                Yarışma
              </span>
              <select
                value={seciliId}
                onChange={(e) => setSeciliId(e.target.value)}
                data-testid="competition-select"
                className="rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
              >
                {yarismalar.map((y) => (
                  <option key={y.id} value={y.id}>
                    {y.name}
                  </option>
                ))}
              </select>
            </label>
            {secili?.required_headings.length ? (
              <div className="mt-4 rounded-xl border border-border bg-background px-4 py-3">
                <p className="text-xs font-semibold uppercase tracking-wide text-muted">
                  Bu yarışmada zorunlu başlıklar
                </p>
                <ul className="mt-2 flex flex-wrap gap-2" data-testid="required-headings">
                  {secili.required_headings.map((b) => (
                    <li
                      key={b}
                      className="rounded-full border border-border px-3 py-1 text-xs text-muted"
                    >
                      {b}
                    </li>
                  ))}
                </ul>
                <p className="mt-2 text-xs text-muted">
                  Raporunuzda bu başlıkların bulunması bekleniyor; eksik başlıklar
                  değerlendirmede puan kaybettirir.
                </p>
              </div>
            ) : null}
          </section>

          {secili ? (
            <ReportUpload
              competitionId={secili.id}
              onUploadComplete={() => void yukle()}
            />
          ) : null}
        </>
      )}
    </div>
  );
}
