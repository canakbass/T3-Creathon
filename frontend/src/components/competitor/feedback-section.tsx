import type { FeedbackPoint } from "@/lib/competitor-feedback";

export type FeedbackVariant = "strength" | "improvement";

const VARIANT_STYLES: Record<
  FeedbackVariant,
  { section: string; heading: string; marker: string; count: string }
> = {
  strength: {
    section: "border-emerald-100 bg-emerald-50/60",
    heading: "text-emerald-900",
    marker: "bg-emerald-100 text-emerald-700",
    count: "bg-emerald-100 text-emerald-800",
  },
  improvement: {
    section: "border-amber-100 bg-amber-50/60",
    heading: "text-amber-900",
    marker: "bg-amber-100 text-amber-700",
    count: "bg-amber-100 text-amber-800",
  },
};

const VARIANT_ICON: Record<FeedbackVariant, React.ReactNode> = {
  strength: (
    <path
      d="m5 12.5 4.5 4.5L19 7.5"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  ),
  improvement: (
    <path
      d="M12 8.5v4m0 3.5h.01M12 3.5 21 20H3l9-16.5Z"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  ),
};

interface FeedbackSectionProps {
  variant: FeedbackVariant;
  title: string;
  intro: string;
  points: FeedbackPoint[];
  testId: string;
}

export function FeedbackSection({
  variant,
  title,
  intro,
  points,
  testId,
}: FeedbackSectionProps) {
  const styles = VARIANT_STYLES[variant];
  const headingId = `${testId}-heading`;

  return (
    <section
      aria-labelledby={headingId}
      data-testid={testId}
      className={`rounded-2xl border p-6 ${styles.section}`}
    >
      <div className="flex items-center gap-3">
        <span
          aria-hidden="true"
          className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${styles.marker}`}
        >
          <svg viewBox="0 0 24 24" fill="none" className="h-4.5 w-4.5">
            {VARIANT_ICON[variant]}
          </svg>
        </span>
        <h2 id={headingId} className={`text-base font-bold ${styles.heading}`}>
          {title}
        </h2>
        <span
          className={`ml-auto rounded-full px-2.5 py-0.5 text-xs font-bold tabular-nums ${styles.count}`}
        >
          {points.length}
        </span>
      </div>

      <p className={`mt-2 text-sm leading-relaxed ${styles.heading} opacity-80`}>{intro}</p>

      <ul className="mt-5 flex flex-col gap-4">
        {/* Anahtar SIRA + baslik: maddeler AI ciktisindan turetiliyor ve
            ayni baslik iki kez gelebilir. Basligi tek basina anahtar yapmak
            yarismacinin geri bildirim maddelerinden birini kaybetmesi
            demekti. */}
        {points.map((point, sira) => (
          <li
            key={`${sira}-${point.title}`}
            className="rounded-xl border border-white/70 bg-white/80 px-4 py-3.5"
          >
            <h3 className="text-sm font-bold text-foreground">{point.title}</h3>
            <p className="mt-1.5 text-sm leading-relaxed text-slate-600">{point.detail}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}
