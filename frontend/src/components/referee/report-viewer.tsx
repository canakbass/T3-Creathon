"use client";

import { useEffect, useState } from "react";
import { downloadReportFile, fetchReportFile } from "@/lib/api";
import { describeError } from "@/lib/api/errors";

/**
 * Raporun kendisini hakeme gösterir.
 *
 * NEDEN GEREKLİ: bu bileşenden önce hakem, OKUYAMADIĞI bir raporu
 * değerlendiriyordu — sistemde yalnızca AI'nin özeti vardı, belgenin
 * kendisi yoktu.
 *
 * NEDEN BLOB: `<iframe src="/api/reports/x/file">` Authorization başlığını
 * GÖNDERMEZ, dolayısıyla token'lı bir uç noktayı doğrudan iframe'e vermek
 * 401 döner. Dosyayı blob olarak indirip object URL üretiyoruz.
 */
export function ReportViewer({
  reportId,
  fileName,
}: {
  reportId: string;
  fileName: string;
}) {
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [acik, setAcik] = useState(false);
  const [indiriliyor, setIndiriliyor] = useState(false);

  useEffect(() => {
    if (!acik) return;
    let iptal = false;
    let uretilen: string | null = null;

    (async () => {
      setError(null);
      try {
        const { url: objectUrl } = await fetchReportFile(reportId);
        uretilen = objectUrl;
        if (iptal) {
          URL.revokeObjectURL(objectUrl);
          return;
        }
        setUrl(objectUrl);
      } catch (cause) {
        if (!iptal) setError(describeError(cause));
      }
    })();

    return () => {
      iptal = true;
      // Object URL'ler tarayıcı belleğinde kalır; bileşen kapanınca
      // serbest bırakılmazsa sızıntı olur.
      if (uretilen) URL.revokeObjectURL(uretilen);
      setUrl(null);
    };
  }, [acik, reportId]);

  async function indir() {
    setIndiriliyor(true);
    setError(null);
    try {
      await downloadReportFile(reportId, fileName);
    } catch (cause) {
      setError(describeError(cause));
    } finally {
      setIndiriliyor(false);
    }
  }

  return (
    <section
      data-testid="report-viewer"
      className="rounded-2xl border border-border bg-surface p-6 shadow-sm"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold text-foreground">Raporun Kendisi</h2>
          <p className="mt-1 text-sm text-muted">
            Değerlendirmenizi yapmadan önce belgeyi inceleyin.
          </p>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => setAcik((a) => !a)}
            data-testid="toggle-report-viewer"
            className="rounded-lg border border-border bg-surface px-3 py-1.5 text-sm font-semibold text-brand-700 transition hover:border-brand-300"
          >
            {acik ? "Görüntüleyiciyi kapat" : "Raporu görüntüle"}
          </button>
          <button
            type="button"
            onClick={() => void indir()}
            disabled={indiriliyor}
            data-testid="download-report"
            className="rounded-lg bg-brand-600 px-3 py-1.5 text-sm font-semibold text-white transition hover:bg-brand-700 disabled:opacity-60"
          >
            {indiriliyor ? "İndiriliyor…" : "İndir"}
          </button>
        </div>
      </div>

      {error ? (
        <div
          role="alert"
          data-testid="viewer-error"
          className="mt-4 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-medium text-rose-700"
        >
          {error}
        </div>
      ) : null}

      {acik ? (
        url ? (
          <iframe
            src={url}
            title={`${fileName} önizleme`}
            data-testid="report-iframe"
            className="mt-4 h-[36rem] w-full rounded-xl border border-border bg-white"
          />
        ) : !error ? (
          <div
            data-testid="viewer-loading"
            aria-hidden="true"
            className="mt-4 h-[36rem] w-full animate-pulse rounded-xl border border-border bg-slate-100"
          />
        ) : null
      ) : null}
    </section>
  );
}
