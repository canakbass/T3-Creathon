import type { ReportStatus } from "@/lib/mock-reports";

// Backend'in döndürdüğü altı durumun tamamı karşılanıyor. `Record` tam
// olduğu için yeni bir durum eklenirse TypeScript burayı hata verir —
// etiketsiz bir rozetin sessizce "undefined" göstermesi engellenmiş olur.
const STATUS_STYLES: Record<ReportStatus, string> = {
  pending: "bg-amber-50 text-amber-700 ring-1 ring-inset ring-amber-200",
  analyzed: "bg-emerald-50 text-emerald-700 ring-1 ring-inset ring-emerald-200",
  approved: "bg-brand-50 text-brand-700 ring-1 ring-inset ring-brand-200",
  rejected: "bg-rose-50 text-rose-700 ring-1 ring-inset ring-rose-200",
  revise: "bg-orange-50 text-orange-700 ring-1 ring-inset ring-orange-200",
  error: "bg-slate-100 text-slate-600 ring-1 ring-inset ring-slate-300",
};

const STATUS_LABELS: Record<ReportStatus, string> = {
  pending: "Beklemede",
  analyzed: "Analiz Edildi",
  approved: "Onaylandı",
  rejected: "Reddedildi",
  revise: "Revizyon İstendi",
  error: "Analiz Hatası",
};

export function StatusBadge({ status }: { status: ReportStatus }) {
  return (
    <span
      className={`inline-flex shrink-0 items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${STATUS_STYLES[status]}`}
    >
      {STATUS_LABELS[status]}
    </span>
  );
}
