"use client";

import { useState } from "react";
import { createUser } from "@/lib/api";
import { describeError } from "@/lib/api/errors";

/**
 * Yöneticinin TOPLU hesap açtığı ekran.
 *
 * NEDEN KENDİ KENDİNE KAYIT YOK: raporun sonucunu TAKIM ÜYELİĞİ belirliyor
 * ve üyelik e-postaya bağlı. Kayıt açık olsaydı, bir takım üyesinin
 * e-postasını ilk kaydettiren kişi o takımın sonuçlarını görürdü.
 *
 * NEDEN E-POSTA DOĞRULAMASI BUNU ÇÖZMEZ: doğrulama "bu kişi bu posta
 * kutusuna erişebiliyor" der. Bizim sorumuz o değil — "bu e-posta bu takıma
 * mı ait?". Yönetici yanlış adresi girerse doğrulama YANLIŞ kişiyi onaylar.
 * O sorunun cevabını yalnızca yönetici bilir; hesabı onun açması kimliğe
 * kefil olması demektir. (Şifre e-postayla İLETİLEBİLİR - bu ekranın
 * yerine değil, üstüne biner.)
 *
 * TOPLU: yönetici tek tek uğraşmasın diye satır satır e-posta alıyor.
 * Gerçek kullanımda liste zaten bir yerden (KYS / Excel) kopyalanıyor.
 */

const ROLLER = [
  { deger: "COMPETITOR", etiket: "Yarışmacı" },
  { deger: "REFEREE", etiket: "Hakem" },
  { deger: "COMPETITION_MANAGER", etiket: "Yarışma Yöneticisi" },
  { deger: "EVALUATION_MANAGER", etiket: "Değerlendirme Yöneticisi" },
] as const;

interface Sonuc {
  eposta: string;
  sifre?: string;
  hata?: string;
}

export function AccountCreator({ teamId }: { teamId?: string | null }) {
  const [epostalar, setEpostalar] = useState("");
  const [rol, setRol] = useState<string>("COMPETITOR");
  const [takim, setTakim] = useState(teamId ?? "");
  const [sonuclar, setSonuclar] = useState<Sonuc[] | null>(null);
  const [calisiyor, setCalisiyor] = useState(false);

  const satirlar = epostalar
    .split(/[\n,;]/)
    .map((x) => x.trim())
    .filter(Boolean);

  async function ac(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (satirlar.length === 0) return;
    setCalisiyor(true);
    setSonuclar(null);
    const toplanan: Sonuc[] = [];
    // Sirayla: bir adres hata verirse DIGERLERI DEVAM ETSIN. Tumunu birden
    // iptal etmek, yoneticiyi listeyi elle ayiklamaya zorlardi.
    for (const eposta of satirlar) {
      try {
        const d = await createUser({
          email: eposta,
          roles: [rol],
          teamId: takim.trim() || null,
        });
        toplanan.push({ eposta: d.email, sifre: d.temporary_password });
      } catch (cause) {
        toplanan.push({ eposta, hata: describeError(cause) });
      }
    }
    setSonuclar(toplanan);
    setCalisiyor(false);
    setEpostalar("");
  }

  const basarili = sonuclar?.filter((s) => s.sifre) ?? [];

  return (
    <section
      data-testid="account-creator"
      className="rounded-2xl border border-border bg-surface p-6 shadow-sm"
    >
      <h2 className="text-lg font-bold text-foreground">Hesap Aç</h2>
      <p className="mt-1 text-sm text-muted">
        Kullanıcılar kendi kendine kayıt olamaz. Hesapları siz açarsınız,
        şifreyi sistem üretir ve kullanıcıya siz iletirsiniz.
      </p>

      <form onSubmit={ac} className="mt-4 flex flex-col gap-3">
        <label className="flex flex-col gap-1 text-xs text-muted">
          E-posta adresleri (her satıra bir tane)
          <textarea
            value={epostalar}
            onChange={(e) => setEpostalar(e.target.value)}
            rows={4}
            placeholder={"kaptan@takim.org\nuye@takim.org"}
            data-testid="account-emails"
            aria-label="E-posta adresleri"
            className="rounded-lg border border-border bg-background px-3 py-2 font-mono text-sm text-foreground"
          />
        </label>

        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-xs text-muted">
            Rol
            <select
              value={rol}
              onChange={(e) => setRol(e.target.value)}
              data-testid="account-role"
              aria-label="Rol"
              className="rounded-lg border border-border bg-background px-2 py-1.5 text-sm text-foreground"
            >
              {ROLLER.map((r) => (
                <option key={r.deger} value={r.deger}>
                  {r.etiket}
                </option>
              ))}
            </select>
          </label>

          <label className="flex flex-col gap-1 text-xs text-muted">
            Takım kimliği (isteğe bağlı)
            <input
              value={takim}
              onChange={(e) => setTakim(e.target.value)}
              placeholder="team-glieser"
              data-testid="account-team"
              aria-label="Takım kimliği"
              className="rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground"
            />
          </label>

          <button
            type="submit"
            disabled={calisiyor || satirlar.length === 0}
            data-testid="account-submit"
            className="rounded-lg bg-brand-600 px-4 py-1.5 text-sm font-semibold text-white transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {calisiyor ? "Açılıyor…" : `${satirlar.length || ""} hesap aç`.trim()}
          </button>
        </div>
      </form>

      {sonuclar ? (
        <div className="mt-5" data-testid="account-results">
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <p className="text-sm font-semibold text-foreground">
              {basarili.length} hesap açıldı
              {sonuclar.length - basarili.length > 0
                ? ` · ${sonuclar.length - basarili.length} hata`
                : ""}
            </p>
            {basarili.length > 0 ? (
              <button
                type="button"
                data-testid="account-copy"
                onClick={() =>
                  void navigator.clipboard?.writeText(
                    basarili.map((s) => `${s.eposta}\t${s.sifre}`).join("\n"),
                  )
                }
                className="rounded-lg border border-border px-3 py-1 text-xs font-semibold text-muted hover:border-brand-300 hover:text-brand-700"
              >
                Hepsini kopyala
              </button>
            ) : null}
          </div>

          {/* Şifreler YALNIZCA BURADA görünüyor - veri tabanında sadece
              bcrypt özeti var, bir daha okunamaz. Bu uyarı olmadan yönetici
              sayfayı kapatıp şifreleri kaybedebilir. */}
          {basarili.length > 0 ? (
            <p
              data-testid="account-password-notice"
              className="mb-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900"
            >
              Şifreler yalnızca burada görünüyor; sayfayı kapattığınızda bir daha
              okunamaz. Kullanıcılara güvenli bir kanaldan iletin.
            </p>
          ) : null}

          <ul className="flex flex-col gap-1">
            {sonuclar.map((s) => (
              <li
                key={s.eposta}
                data-testid={`account-row-${s.eposta}`}
                className={`flex flex-wrap items-center justify-between gap-2 rounded-lg border px-3 py-2 text-xs ${
                  s.hata ? "border-rose-200 bg-rose-50" : "border-border"
                }`}
              >
                <span className="font-semibold text-foreground">{s.eposta}</span>
                {s.hata ? (
                  <span className="text-rose-700">{s.hata}</span>
                ) : (
                  <code className="rounded bg-slate-100 px-2 py-0.5 font-mono text-foreground">
                    {s.sifre}
                  </code>
                )}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}
