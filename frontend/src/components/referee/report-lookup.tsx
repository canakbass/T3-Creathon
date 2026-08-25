"use client";

import { useState } from "react";
import { lookupReports, type ReportLookupQuery } from "@/lib/api";
import { describeError } from "@/lib/api/errors";
import type { WireReportLookup } from "@/lib/api/types";

/**
 * Başvuru arama — hakem kendisine ATANMAMIŞ raporları da bulabilsin diye.
 *
 * NEDEN AYRI BİR BİLEŞEN VE AYRI BİR UÇ NOKTA: hakemin atanmamış raporlara
 * erişmesi bilinçli bir gevşetme; aynı sistemde tam tersi bir açık
 * kapatıldı (atanmamış hakem başka bir yarışmacının tam AI analizini
 * okuyabiliyordu). Bu yüzden arama sonucu KÜNYE ile sınırlı: puan, gerekçe,
 * benzerlik bulgusu ve PDF burada YOK ve backend de vermiyor.
 *
 * Aramanın asıl cevapladığı soru: "bu başvuruya kim bakıyor?"
 */

const OLCUTLER = [
  { anahtar: "reportId", etiket: "Başvuru kimliği", ornek: "RPT-2026-4A9C21" },
  { anahtar: "teamId", etiket: "Takım kimliği", ornek: "team-glieser" },
  { anahtar: "email", etiket: "Yarışmacı e-postası", ornek: "ad@ornek.org" },
] as const;

type OlcutAnahtari = (typeof OLCUTLER)[number]["anahtar"];

const DURUM_ETIKETLERI: Record<string, { metin: string; sinif: string }> = {
  analiz_bekliyor: { metin: "Analiz bekliyor", sinif: "bg-slate-100 text-slate-700" },
  analiz_edildi: { metin: "Analiz edildi", sinif: "bg-brand-50 text-brand-700" },
  degerlendirildi: { metin: "Değerlendirildi", sinif: "bg-emerald-50 text-emerald-700" },
  hata: { metin: "Analiz başarısız", sinif: "bg-rose-50 text-rose-700" },
};

interface Props {
  /** Sonuca tıklanınca çağrılır — yalnızca `access === "assigned"` satırlarda. */
  onOpen?: (reportId: string) => void;
}

export function ReportLookup({ onOpen }: Props) {
  const [olcut, setOlcut] = useState<OlcutAnahtari>("reportId");
  const [deger, setDeger] = useState("");
  const [sonuclar, setSonuclar] = useState<WireReportLookup[] | null>(null);
  const [hata, setHata] = useState<string | null>(null);
  const [araniyor, setAraniyor] = useState(false);

  async function ara(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const q = deger.trim();
    if (!q) return;
    setAraniyor(true);
    setHata(null);
    try {
      // Tam olarak BİR ölçüt gönderiliyor: backend 0 ya da 2+ ölçütü 422 ile
      // reddediyor (boş sorgu = envanter tarama).
      const sorgu = { [olcut]: q } as unknown as ReportLookupQuery;
      setSonuclar(await lookupReports(sorgu));
    } catch (cause) {
      setHata(describeError(cause));
      setSonuclar(null);
    } finally {
      setAraniyor(false);
    }
  }

  const secili = OLCUTLER.find((o) => o.anahtar === olcut)!;

  return (
    <section
      data-testid="report-lookup"
      className="rounded-2xl border border-border bg-surface p-5 shadow-sm"
    >
      <h3 className="text-sm font-bold text-foreground">Başvuru ara</h3>
      <p className="mt-1 text-xs text-muted">
        Size atanmamış bir başvuruyu kimliğiyle bulabilirsiniz. Arama sonucu
        yalnızca künye gösterir — puan, gerekçe ve rapor dosyası yalnızca size
        atanmış başvurularda açılır.
      </p>

      <form onSubmit={ara} className="mt-3 flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1 text-xs text-muted">
          Ölçüt
          <select
            value={olcut}
            onChange={(e) => {
              setOlcut(e.target.value as OlcutAnahtari);
              setSonuclar(null);
            }}
            data-testid="lookup-field"
            aria-label="Arama ölçütü"
            className="rounded-lg border border-border bg-background px-2 py-1.5 text-sm text-foreground"
          >
            {OLCUTLER.map((o) => (
              <option key={o.anahtar} value={o.anahtar}>
                {o.etiket}
              </option>
            ))}
          </select>
        </label>

        <label className="flex flex-1 flex-col gap-1 text-xs text-muted">
          {secili.etiket}
          <input
            value={deger}
            onChange={(e) => setDeger(e.target.value)}
            placeholder={secili.ornek}
            data-testid="lookup-input"
            aria-label={secili.etiket}
            className="min-w-48 rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground"
          />
        </label>

        <button
          type="submit"
          disabled={araniyor || !deger.trim()}
          data-testid="lookup-submit"
          className="rounded-lg bg-brand-600 px-4 py-1.5 text-sm font-semibold text-white transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {araniyor ? "Aranıyor…" : "Ara"}
        </button>
      </form>

      <p className="mt-2 text-xs text-muted">
        Tam eşleşme aranır; parça arama yapılmaz.
      </p>

      {hata ? (
        <div
          role="alert"
          data-testid="lookup-error"
          className="mt-3 rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-xs font-medium text-rose-700"
        >
          {hata}
        </div>
      ) : null}

      {sonuclar !== null && sonuclar.length === 0 ? (
        <p
          data-testid="lookup-empty"
          className="mt-3 rounded-xl border border-dashed border-border px-3 py-4 text-center text-xs text-muted"
        >
          Bu kimlikle eşleşen başvuru bulunamadı.
        </p>
      ) : null}

      {sonuclar && sonuclar.length > 0 ? (
        <ul className="mt-3 flex flex-col gap-2" data-testid="lookup-results">
          {sonuclar.map((r) => {
            const durum = DURUM_ETIKETLERI[r.evaluation_state] ?? {
              metin: r.evaluation_state,
              sinif: "bg-slate-100 text-slate-700",
            };
            const acilabilir = r.access === "assigned";
            return (
              <li
                key={r.report_id}
                data-testid={`lookup-row-${r.report_id}`}
                className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-border px-3 py-2"
              >
                <span className="min-w-0">
                  <span className="block truncate text-sm font-semibold text-foreground">
                    {r.project_name}
                  </span>
                  <span className="block text-xs text-muted">
                    {r.report_id}
                    {r.team_name ? ` · ${r.team_name}` : ""}
                    {r.competition_name ? ` · ${r.competition_name}` : ""}
                  </span>
                  <span className="block text-xs text-muted">
                    Sorumlu hakem:{" "}
                    {r.assigned_referee_email ? (
                      <span className="font-semibold text-brand-700">
                        {r.assigned_referee_email}
                      </span>
                    ) : (
                      <span className="text-amber-700">atanmamış</span>
                    )}
                  </span>
                </span>
                <span className="flex items-center gap-2">
                  <span
                    className={`rounded-full px-2 py-0.5 text-xs font-semibold ${durum.sinif}`}
                  >
                    {durum.metin}
                  </span>
                  {acilabilir ? (
                    <button
                      type="button"
                      onClick={() => onOpen?.(r.report_id)}
                      data-testid={`lookup-open-${r.report_id}`}
                      className="rounded-lg border border-brand-300 px-3 py-1 text-xs font-semibold text-brand-700 transition hover:bg-brand-50"
                    >
                      Aç
                    </button>
                  ) : (
                    /* Size atanmamış: künye dışında bir şey gösterilmiyor.
                       Düğmeyi gizlemek yerine NEDENİNİ yazıyoruz - hakem
                       "neden açamıyorum" diye aramasın. */
                    <span
                      data-testid={`lookup-locked-${r.report_id}`}
                      className="text-xs text-muted"
                    >
                      Size atanmamış
                    </span>
                  )}
                </span>
              </li>
            );
          })}
        </ul>
      ) : null}
    </section>
  );
}
