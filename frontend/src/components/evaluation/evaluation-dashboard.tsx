"use client";

import { useCallback, useEffect, useState } from "react";
import { getDashboardStats } from "@/lib/api";
import { describeError } from "@/lib/api/errors";
import type { WireDashboardStats } from "@/lib/api/types";

/**
 * Değerlendirme Yöneticisi panosu (MVP rolü 4: "Analiz durumlarını,
 * tamamlanma oranlarını ve değerlendirme akışını izler").
 *
 * Bu sayfa daha önce tek bir statik `<p>` etiketinden ibaretti — hiçbir
 * veri göstermiyordu. Backend'de `GET /api/dashboard/stats` zaten vardı
 * ve hiç çağrılmıyordu.
 */
interface EvaluationDashboardProps {
  /** Testlerde API çağrısını atlamak için. */
  initialStats?: WireDashboardStats;
}

interface Tile {
  key: keyof WireDashboardStats;
  label: string;
  hint: string;
}

const TILES: Tile[] = [
  { key: "total_reports", label: "Toplam Rapor", hint: "Sisteme yüklenen tüm başvurular" },
  { key: "pending_reports", label: "Analiz Bekliyor", hint: "AI analizi henüz tamamlanmadı" },
  { key: "analyzed_reports", label: "Hakem Bekliyor", hint: "Analiz bitti, nihai karar verilmedi" },
  { key: "approved_reports", label: "Onaylandı", hint: "Hakem onayıyla ilerledi" },
  { key: "revise_reports", label: "Revizyon İstendi", hint: "Düzeltme sonrası yeniden değerlendirilecek" },
  { key: "rejected_reports", label: "Reddedildi", hint: "Yarışma kriterlerini karşılamadı" },
];

export function EvaluationDashboard({ initialStats }: EvaluationDashboardProps) {
  const [stats, setStats] = useState<WireDashboardStats | null>(initialStats ?? null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setStats(await getDashboardStats());
    } catch (cause) {
      setError(describeError(cause));
    }
  }, []);

  useEffect(() => {
    if (initialStats) return;
    void load();
  }, [initialStats, load]);

  return (
    <div className="flex flex-col gap-6" data-testid="evaluation-dashboard">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold text-foreground">Değerlendirme Süreci</h2>
          <p className="mt-1 text-sm text-muted">
            Analiz durumlarını ve tamamlanma oranını izleyin.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void load()}
          data-testid="refresh-stats"
          className="rounded-lg border border-border bg-surface px-3 py-1.5 text-sm font-semibold text-muted transition hover:border-brand-300 hover:text-brand-700"
        >
          Yenile
        </button>
      </div>

      {error ? (
        <div
          role="alert"
          data-testid="stats-error"
          className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-medium text-rose-700"
        >
          {error}
        </div>
      ) : null}

      {stats === null && !error ? (
        <div
          data-testid="stats-loading"
          aria-hidden="true"
          className="h-40 animate-pulse rounded-2xl border border-border bg-slate-100"
        />
      ) : null}

      {stats ? (
        <>
          <section
            aria-label="Tamamlanma oranı"
            data-testid="completion-rate"
            className="rounded-2xl border border-border bg-surface p-6 shadow-sm"
          >
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-muted">
                  Tamamlanma Oranı
                </p>
                <p className="mt-1 text-3xl font-extrabold text-foreground">
                  %{stats.completion_rate}
                </p>
                <p className="mt-1 text-xs text-muted">
                  Nihai karara bağlanmış raporların toplam içindeki payı
                </p>
              </div>
            </div>
            <div
              role="progressbar"
              aria-valuenow={Math.round(stats.completion_rate)}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-label="Tamamlanma oranı"
              className="mt-4 h-2 w-full overflow-hidden rounded-full bg-slate-100"
            >
              <div
                className="h-full rounded-full bg-brand-600 transition-[width] duration-500"
                style={{ width: `${Math.min(100, Math.max(0, stats.completion_rate))}%` }}
              />
            </div>
          </section>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {TILES.map((tile) => (
              <div
                key={tile.key}
                data-testid={`stat-${tile.key}`}
                className="rounded-2xl border border-border bg-surface p-5 shadow-sm"
              >
                <p className="text-xs font-semibold uppercase tracking-wide text-muted">
                  {tile.label}
                </p>
                <p className="mt-1 text-2xl font-extrabold text-foreground">
                  {stats[tile.key]}
                </p>
                <p className="mt-1 text-xs leading-relaxed text-muted">{tile.hint}</p>
              </div>
            ))}
          </div>
        </>
      ) : null}
    </div>
  );
}
