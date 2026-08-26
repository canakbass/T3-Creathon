"use client";

import { useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { confirmPasswordReset } from "@/lib/api";
import { describeError } from "@/lib/api/errors";

const EN_KISA_SIFRE = 8;

/**
 * Şifre sıfırlama ekranı — `/sifre-sifirla?token=...`
 *
 * Sıfırlama başarılı olunca ELDEKİ TÜM OTURUMLAR düşüyor (sunucu tarafında
 * `token_epoch` artıyor). Bu şart: çalınmış bir token, kurban şifresini
 * sıfırladıktan sonra da bir saat daha çalışsaydı sıfırlamanın tek amacı
 * ("hesabı geri al") ortadan kalkardı.
 */
export function ResetPasswordScreen() {
  const router = useRouter();
  const params = useSearchParams();
  const token = params.get("token") ?? "";

  const [sifre, setSifre] = useState("");
  const [tekrar, setTekrar] = useState("");
  const [hata, setHata] = useState<string | null>(null);
  const [bitti, setBitti] = useState(false);
  const [busy, setBusy] = useState(false);

  async function gonder(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setHata(null);

    if (!token) {
      setHata("Sıfırlama bağlantısı eksik. E-postadaki bağlantıyı tam olarak açın.");
      return;
    }
    if (sifre.length < EN_KISA_SIFRE) {
      setHata(`Şifre en az ${EN_KISA_SIFRE} karakter olmalı.`);
      return;
    }
    // İki alan SUNUCUYA GİTMEDEN karşılaştırılıyor: yazım hatasıyla
    // bilinmeyen bir şifre belirlemek, tek kullanımlık jetonu harcayıp
    // kullanıcıyı hesabından tamamen kilitlerdi.
    if (sifre !== tekrar) {
      setHata("Şifreler birbirini tutmuyor.");
      return;
    }

    setBusy(true);
    try {
      await confirmPasswordReset(token, sifre);
      setBitti(true);
    } catch (cause) {
      setHata(describeError(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-screen w-full items-center justify-center bg-background px-4 py-16">
      <div className="w-full max-w-md rounded-2xl border border-border bg-surface p-8 shadow-sm">
        <h1 className="text-center text-2xl font-extrabold text-foreground">
          Yeni şifre belirleyin
        </h1>

        {bitti ? (
          <div data-testid="reset-success" className="mt-6 flex flex-col gap-4">
            <p className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm font-medium text-emerald-700">
              Şifreniz değiştirildi. Diğer cihazlardaki oturumlarınız da
              kapatıldı; yeni şifrenizle giriş yapın.
            </p>
            <button
              type="button"
              onClick={() => router.push("/")}
              data-testid="reset-go-login"
              className="rounded-lg bg-brand-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-brand-700"
            >
              Giriş ekranına git
            </button>
          </div>
        ) : (
          <form onSubmit={gonder} data-testid="reset-password-form" className="mt-6 flex flex-col gap-4">
            {hata ? (
              <div
                role="alert"
                data-testid="reset-error"
                className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-medium text-rose-700"
              >
                {hata}
              </div>
            ) : null}

            <label className="flex flex-col gap-1.5">
              <span className="text-xs font-semibold uppercase tracking-wide text-muted">
                Yeni şifre
              </span>
              <input
                type="password"
                required
                autoComplete="new-password"
                value={sifre}
                onChange={(e) => setSifre(e.target.value)}
                data-testid="reset-password"
                className="rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground"
              />
              <span className="text-xs text-muted">En az {EN_KISA_SIFRE} karakter.</span>
            </label>

            <label className="flex flex-col gap-1.5">
              <span className="text-xs font-semibold uppercase tracking-wide text-muted">
                Yeni şifre (tekrar)
              </span>
              <input
                type="password"
                required
                autoComplete="new-password"
                value={tekrar}
                onChange={(e) => setTekrar(e.target.value)}
                data-testid="reset-password-repeat"
                className="rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground"
              />
            </label>

            <button
              type="submit"
              disabled={busy}
              data-testid="reset-confirm"
              className="mt-2 rounded-lg bg-brand-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {busy ? "Lütfen bekleyin…" : "Şifreyi değiştir"}
            </button>
          </form>
        )}
      </div>
    </main>
  );
}
