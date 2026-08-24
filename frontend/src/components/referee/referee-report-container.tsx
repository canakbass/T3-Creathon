"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  fetchRationaleDraft,
  getReport,
  pollUntilAnalyzed,
  submitDecision,
  type ReportWithAnalysis,
} from "@/lib/api";
import { describeError } from "@/lib/api/errors";
import type { FinalDecisionSubmission } from "@/lib/final-decision";
import { RefereeReportDetail } from "./referee-report-detail";

/**
 * Tek bir raporun canlı verisini yükleyip {@link RefereeReportDetail}'e
 * besleyen kap bileşeni.
 *
 * NEDEN AYRI BİR BİLEŞEN: `RefereeReportDetail` saf sunum bileşeni ve
 * mevcut testleri ona doğrudan prop veriyor. Veri çekmeyi oraya koymak o
 * testleri bozardı; kap ayrı tutulunca sunum katmanı test edilebilir
 * kalıyor.
 *
 * Sayfanın kendisi de artık bunu kullanıyor: eskiden sunucu bileşeniydi ve
 * `generateStaticParams` ile MOCK_REPORTS kimliklerinden statik üretiliyordu
 * — yani gerçek bir rapor kimliğiyle açıldığında 404 veriyordu. Ayrıca JWT
 * localStorage'da durduğu için bir sunucu bileşeni ona zaten erişemezdi.
 */
export function RefereeReportContainer({ reportId }: { reportId: string }) {
  const [data, setData] = useState<ReportWithAnalysis | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [decisionError, setDecisionError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    abortRef.current = controller;

    (async () => {
      try {
        const first = await getReport(reportId);
        setData(first);

        // Analiz arka planda calisiyor. "pending" ise bitene kadar yokla ki
        // hakem sayfayi elle yenilemek zorunda kalmasin.
        if (first.rawStatus === "pending") {
          const finished = await pollUntilAnalyzed(reportId, {
            signal: controller.signal,
            onTick: setData,
          });
          setData(finished);
        }
      } catch (cause) {
        if (cause instanceof DOMException && cause.name === "AbortError") return;
        setError(describeError(cause));
      }
    })();

    return () => controller.abort();
  }, [reportId]);

  /**
   * Hakemin nihai kararını backend'e yazar.
   *
   * `RefereeReportDetail` -> `FinalDecisionForm` bu geri çağrımı `await`
   * ediyor; Promise reddedilirse form "kaydedildi" ekranını GÖSTERMİYOR.
   * Eskiden geri çağrım senkron ve sonuçsuzdu, yani kayıt başarısız olsa
   * bile arayüz başarı gösteriyordu.
   */
  const handleSubmitDecision = useCallback(
    async (submission: FinalDecisionSubmission) => {
      setDecisionError(null);
      try {
        await submitDecision({
          reportId: submission.reportId,
          outcome: submission.outcome,
          finalScore: submission.finalScore,
          // Arayuzde `refereeNotes`, backend'de `rationale`.
          rationale: submission.refereeNotes,
          rationaleAiDrafted: submission.rationaleAiDrafted,
          rationaleEditedByReferee: submission.rationaleEditedByReferee,
        });
        // Karar sonrasi rapor durumu degisiyor (approved/rejected/revise) -
        // rozetin guncellenmesi icin tazeliyoruz.
        setData(await getReport(reportId));
      } catch (cause) {
        const message = describeError(cause);
        setDecisionError(message);
        throw cause;
      }
    },
    [reportId],
  );

  if (error) {
    return (
      <div
        role="alert"
        data-testid="report-load-error"
        className="rounded-2xl border border-rose-200 bg-rose-50 px-6 py-8 text-center text-sm font-medium text-rose-700"
      >
        {error}
      </div>
    );
  }

  if (!data) {
    return (
      <div
        data-testid="report-loading"
        aria-hidden="true"
        className="h-64 animate-pulse rounded-2xl border border-border bg-slate-100"
      />
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {decisionError ? (
        <div
          role="alert"
          data-testid="decision-error"
          className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-medium text-rose-700"
        >
          {decisionError}
        </div>
      ) : null}

      <RefereeReportDetail
        report={data.report}
        analysis={data.analysis}
        onSubmitDecision={data.hasDecision ? undefined : handleSubmitDecision}
        decisionAlreadySubmitted={data.hasDecision}
        // Canli akista raporun kendisi gosteriliyor. Sunum bileseninin
        // kendi testleri ag cagrisi yapmadigi icin varsayilan kapali.
        showViewer
        onRequestDraft={async () => (await fetchRationaleDraft(reportId)).draft}
      />
    </div>
  );
}
