"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  addRefereeToCompetition,
  autoAssign,
  listReferees,
  listReportRows,
  reassignReport,
  type ReportRow,
} from "@/lib/api";
import { describeError } from "@/lib/api/errors";
import type { WireReferee } from "@/lib/api/types";

/**
 * Yarışmanın hakem kadrosu ve rapor-hakem ataması.
 *
 * NEDEN VAR: önceden atama diye bir şey yoktu — her hakem her raporu
 * görüyordu. Yönetici artık:
 *   1. Yarışmaya hakem ekler
 *   2. Raporları dengeli biçimde otomatik dağıtır
 *   3. Gerekirse tek bir raporun sorumlu hakemini değiştirir
 *      (çıkar çatışması, uzmanlık alanı vb.)
 */
interface Props {
  competitionId: string;
  onChanged?: () => void;
  /** Testlerde ağ çağrısını atlamak için. */
  initialReferees?: WireReferee[];
  initialReports?: ReportRow[];
}

export function RefereeAssignmentPanel({
  competitionId,
  onChanged,
  initialReferees,
  initialReports,
}: Props) {
  const [tumHakemler, setTumHakemler] = useState<WireReferee[]>(initialReferees ?? []);
  const [yarismaHakemleri, setYarismaHakemleri] = useState<WireReferee[]>(
    initialReferees ?? [],
  );
  const [raporlar, setRaporlar] = useState<ReportRow[]>(initialReports ?? []);
  const [arama, setArama] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [eklenecek, setEklenecek] = useState("");

  /**
   * `gecerliIstek` yarış koşulunu engelliyor.
   *
   * NEDEN: yönetici yarışmalar arasında hızlıca geçerse iki `yukle` çağrısı
   * aynı anda uçuşta olur ve HANGİSİNİN ÖNCE DÖNECEĞİ garanti değil. Eski
   * yarışmanın yanıtı sonra dönerse, ekranda B yarışması yazarken A
   * yarışmasının hakemleri ve raporları gösterilir — yönetici de yanlış
   * yarışmada atama yapar. Her yükleme kendi kimliğini alıyor ve yalnızca
   * EN SON başlatılan yükleme state yazabiliyor.
   */
  const istekSayaci = useRef(0);

  const yukle = useCallback(async () => {
    const benimIstegim = ++istekSayaci.current;
    setError(null);
    try {
      // Atama ve karar bilgisi listede geliyor - rapor başına ayrı istek
      // (N+1) gerekmiyor. Bunun için backend'in ReportResponse'una
      // assigned_referee_id/email alanları eklendi.
      const [hepsi, yarismada, rprlar] = await Promise.all([
        listReferees(),
        listReferees(competitionId),
        listReportRows(),
      ]);
      if (benimIstegim !== istekSayaci.current) return;
      setTumHakemler(hepsi);
      setYarismaHakemleri(yarismada);
      setRaporlar(rprlar);
    } catch (cause) {
      if (benimIstegim !== istekSayaci.current) return;
      setError(describeError(cause));
    }
  }, [competitionId]);

  useEffect(() => {
    if (initialReferees && initialReports) return;
    void yukle();
  }, [initialReferees, initialReports, yukle]);

  const eklenebilir = useMemo(
    () =>
      tumHakemler.filter((h) => !yarismaHakemleri.some((y) => y.id === h.id)),
    [tumHakemler, yarismaHakemleri],
  );

  /**
   * YALNIZCA bu yarışmanın raporları.
   *
   * Önceden `|| r.competitionId === null` ile yarışmaya bağlı olmayan
   * raporlar da listeleniyordu. Bu, o raporların HER yarışmanın panelinde
   * görünmesi demekti: A yarışmasından atama yapılınca aynı rapor B'de de
   * "atanmış" görünüyor, ama yarışma başına yük hesabına hiç girmedikleri
   * için otomatik dağıtımın dengesi de yanlış çıkıyordu.
   *
   * Filtre YÜKLEMEDE değil BURADA: `initialReports` ile kurulan bir örnek
   * (testler, sunucu tarafı ön yükleme) yükleme yolundan hiç geçmiyor ve
   * filtresiz liste gösterirdi.
   */
  const buYarismaninRaporlari = useMemo(
    () => raporlar.filter((r) => r.competitionId === competitionId),
    [raporlar, competitionId],
  );

  // Yok saymıyoruz: var olduklarını söylüyoruz, sadece burada göstermiyoruz.
  const bagsizSayisi = useMemo(
    () => raporlar.filter((r) => r.competitionId === null).length,
    [raporlar],
  );

  const filtreliRaporlar = useMemo(() => {
    const q = arama.trim().toLocaleLowerCase("tr");
    if (!q) return buYarismaninRaporlari;
    return buYarismaninRaporlari.filter(
      (r) =>
        r.report.projectName.toLocaleLowerCase("tr").includes(q) ||
        r.report.reportId.toLocaleLowerCase("tr").includes(q),
    );
  }, [arama, buYarismaninRaporlari]);

  async function hakemEkle() {
    if (!eklenecek) return;
    setBusy(true);
    setError(null);
    try {
      await addRefereeToCompetition(competitionId, eklenecek);
      setEklenecek("");
      await yukle();
      onChanged?.();
    } catch (cause) {
      setError(describeError(cause));
    } finally {
      setBusy(false);
    }
  }

  async function otomatikDagit() {
    setBusy(true);
    setError(null);
    setInfo(null);
    try {
      const sonuc = await autoAssign(competitionId);
      const dagitim =
        sonuc.assigned === 0
          ? "Atanmamış rapor kalmadı."
          : `${sonuc.assigned} rapor dağıtıldı. ` +
            sonuc.load.map((l) => `${l.email}: ${l.assigned_count}`).join(" · ");
      // Dağıtılamayan raporlar SESSİZCE atlanmamalı: aksi halde yönetici
      // "dağıtım tamam" sanıp hiç değerlendirilmeyen bir rapor bırakır.
      // (Backend bunları `skipped` ile bildiriyor; en sık sebep raporun
      // sahibinin tek uygun hakem olması — çıkar çatışması.)
      const atlanan = sonuc.skipped ?? [];
      if (atlanan.length > 0) {
        setError(
          `${atlanan.length} rapor dağıtılamadı: ` +
            atlanan.map((a) => `${a.report_id} (${a.reason})`).join(" · "),
        );
      }
      setInfo(dagitim);
      await yukle();
      onChanged?.();
    } catch (cause) {
      setError(describeError(cause));
    } finally {
      setBusy(false);
    }
  }

  async function hakemDegistir(reportId: string, refereeId: string) {
    if (!refereeId) return;
    setBusy(true);
    setError(null);
    try {
      await reassignReport(reportId, refereeId);
      setInfo("Sorumlu hakem güncellendi.");
      await yukle();
      onChanged?.();
    } catch (cause) {
      setError(describeError(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section
      data-testid="referee-assignment"
      className="rounded-2xl border border-border bg-surface p-6 shadow-sm"
    >
      <div className="mb-5">
        <h2 className="text-lg font-bold text-foreground">Hakem Kadrosu ve Atama</h2>
        <p className="mt-1 text-sm text-muted">
          Yarışmaya hakem ekleyin, raporları dengeli dağıtın; gerekirse tek tek
          sorumlu hakemi değiştirin.
        </p>
      </div>

      {error ? (
        <div
          role="alert"
          data-testid="assignment-error"
          className="mb-4 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-medium text-rose-700"
        >
          {error}
        </div>
      ) : null}
      {info ? (
        <div
          role="status"
          data-testid="assignment-info"
          className="mb-4 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm font-medium text-emerald-700"
        >
          {info}
        </div>
      ) : null}

      {/* --- Kadro --- */}
      <div className="flex flex-col gap-3">
        <h3 className="text-sm font-semibold text-foreground">
          Görevli hakemler ({yarismaHakemleri.length})
        </h3>
        {yarismaHakemleri.length === 0 ? (
          <p className="rounded-xl border border-dashed border-border px-4 py-4 text-sm text-muted">
            Bu yarışmada henüz hakem yok. Dağıtım yapabilmek için önce hakem ekleyin.
          </p>
        ) : (
          <ul className="flex flex-wrap gap-2" data-testid="competition-referees">
            {yarismaHakemleri.map((h) => (
              <li
                key={h.id}
                className="rounded-full border border-border px-3 py-1 text-xs text-foreground"
              >
                {h.full_name || h.email}
                <span className="ml-2 font-semibold text-brand-700">
                  {h.assigned_count} rapor
                </span>
              </li>
            ))}
          </ul>
        )}

        <div className="flex flex-col gap-2 sm:flex-row">
          <select
            value={eklenecek}
            onChange={(e) => setEklenecek(e.target.value)}
            data-testid="referee-to-add"
            className="flex-1 rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground"
          >
            <option value="">Eklenecek hakemi seçin…</option>
            {eklenebilir.map((h) => (
              <option key={h.id} value={h.id}>
                {h.full_name || h.email}
              </option>
            ))}
          </select>
          <button
            type="button"
            onClick={() => void hakemEkle()}
            disabled={busy || !eklenecek}
            data-testid="add-referee"
            className="rounded-lg border border-border px-4 py-2 text-sm font-semibold text-brand-700 transition hover:border-brand-300 disabled:opacity-60"
          >
            Hakem ekle
          </button>
          <button
            type="button"
            onClick={() => void otomatikDagit()}
            disabled={busy || yarismaHakemleri.length === 0}
            data-testid="auto-assign"
            className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-brand-700 disabled:opacity-60"
          >
            Dengeli dağıt
          </button>
        </div>
      </div>

      {/* --- Rapor listesi + arama + elle atama --- */}
      <div className="mt-6 border-t border-border pt-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h3 className="text-sm font-semibold text-foreground">
            Raporlar ({filtreliRaporlar.length})
          </h3>
          <input
            type="search"
            value={arama}
            onChange={(e) => setArama(e.target.value)}
            placeholder="Rapor adı veya kimliği ara…"
            data-testid="report-search"
            aria-label="Rapor ara"
            className="w-64 rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground"
          />
        </div>

        {bagsizSayisi > 0 ? (
          <p
            data-testid="unattached-reports-notice"
            className="mt-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-2 text-xs text-amber-800"
          >
            {bagsizSayisi} rapor hiçbir yarışmaya bağlı değil ve burada
            gösterilmiyor. Bunlar yarışma akışı devreye girmeden önce
            yüklenmiş eski kayıtlar; bir yarışmaya bağlı olmadıkları için
            dağıtıma dahil edilemezler.
          </p>
        ) : null}

        {filtreliRaporlar.length === 0 ? (
          <p
            data-testid="no-reports"
            className="mt-4 rounded-xl border border-dashed border-border px-4 py-6 text-center text-sm text-muted"
          >
            {arama ? "Aramaya uyan rapor yok." : "Bu yarışmaya henüz rapor yüklenmemiş."}
          </p>
        ) : (
          <ul className="mt-4 flex flex-col gap-2" data-testid="assignment-report-list">
            {filtreliRaporlar.map((satir) => {
              const r = satir.report;
              return (
                <li
                  key={r.reportId}
                  data-testid={`assignment-row-${r.reportId}`}
                  className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border px-4 py-3"
                >
                  <span className="min-w-0">
                    <span className="block truncate text-sm font-semibold text-foreground">
                      {r.projectName}
                    </span>
                    <span className="block text-xs text-muted">
                      {r.reportId} ·{" "}
                      {satir.assignedRefereeEmail ? (
                        <span className="font-semibold text-brand-700">
                          {satir.assignedRefereeEmail}
                        </span>
                      ) : (
                        <span className="text-amber-700">atanmamış</span>
                      )}
                    </span>
                  </span>
                  <label className="flex items-center gap-2 text-xs text-muted">
                    Sorumlu hakem
                    <select
                      defaultValue=""
                      onChange={(e) => void hakemDegistir(r.reportId, e.target.value)}
                      disabled={busy || satir.hasDecision}
                      data-testid={`reassign-${r.reportId}`}
                      aria-label={`${r.projectName} için sorumlu hakem`}
                      className="rounded-lg border border-border bg-background px-2 py-1 text-sm text-foreground disabled:opacity-60"
                    >
                      <option value="">
                        {satir.hasDecision ? "Karar verildi — değiştirilemez" : "Değiştir…"}
                      </option>
                      {yarismaHakemleri.map((h) => (
                        <option key={h.id} value={h.id}>
                          {h.full_name || h.email}
                        </option>
                      ))}
                    </select>
                  </label>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </section>
  );
}
