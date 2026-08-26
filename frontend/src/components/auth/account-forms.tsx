"use client";

import { useState } from "react";
import { register, requestPasswordReset } from "@/lib/api";
import { describeError } from "@/lib/api/errors";

/**
 * Kayıt olma ve şifremi unuttum formları.
 *
 * Kullanıcının isteği: "kullanıcı kendi kendine de hesap oluşturabilsin,
 * şifremi unuttum gibi işlemler yapabilsin."
 *
 * KAYIT TEK BAŞINA HİÇBİR ŞEY AÇMIYOR. Hesap açılıyor ama hiçbir rol,
 * hiçbir kurum verilmiyor. Sonuçları görebilmek için e-postayı doğrulamak
 * gerekiyor ve doğrulama, yöneticinin o adresle yüklediği raporun takımına
 * bağlanmayı sağlıyor. Yani "kayıt oldum" ile "sonucu görüyorum" arasındaki
 * fark, posta kutusuna erişebildiğini kanıtlamak.
 *
 * NEDEN BÖYLE: kayıt bir süre tamamen kapalıydı çünkü bir takım üyesinin
 * e-postasını İLK KAYDETTİREN kişi o takımın sonuçlarını görürdü. Doğrulama
 * bu açığı kapatan tek şey.
 */

const EN_KISA_SIFRE = 8;

interface Props {
  /** Form gönderildikten sonra giriş ekranına dönmek için. */
  onGeriDon: () => void;
  mod: "kayit" | "sifremi-unuttum";
}

export function AccountForm({ onGeriDon, mod }: Props) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [hata, setHata] = useState<string | null>(null);
  const [bilgi, setBilgi] = useState<string | null>(null);
  const [devToken, setDevToken] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const kayit = mod === "kayit";

  async function gonder(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setHata(null);
    setBilgi(null);
    setDevToken(null);

    if (kayit && password.length < EN_KISA_SIFRE) {
      setHata(`Şifre en az ${EN_KISA_SIFRE} karakter olmalı.`);
      return;
    }

    setBusy(true);
    try {
      if (kayit) {
        const sonuc = await register({ email, password, fullName });
        setBilgi(sonuc.message);
        // Geliştirmede sunucu doğrulama bağlantısını yanıtta veriyor; üretimde
        // bu alan boş (jetonu yanıtta döndürmek, "bu kutunun sahibi misin"
        // sorusunu kendi kendine cevaplatmak olurdu).
        setDevToken(sonuc.dev_token);
      } else {
        const sonuc = await requestPasswordReset(email);
        setBilgi(sonuc.message);
      }
    } catch (cause) {
      setHata(describeError(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      onSubmit={gonder}
      data-testid={kayit ? "register-form" : "reset-form"}
      className="flex flex-col gap-4 rounded-2xl border border-border bg-surface p-6 shadow-sm"
    >
      {bilgi ? (
        <div
          role="status"
          data-testid="account-form-info"
          className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm font-medium text-emerald-700"
        >
          {bilgi}
          {devToken ? (
            <p className="mt-2 break-all font-mono text-xs text-emerald-900">
              Geliştirme bağlantısı:{" "}
              <a
                href={`/dogrula?token=${devToken}`}
                data-testid="dev-verify-link"
                className="underline"
              >
                /dogrula?token={devToken}
              </a>
            </p>
          ) : null}
        </div>
      ) : null}

      {hata ? (
        <div
          role="alert"
          data-testid="account-form-error"
          className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-medium text-rose-700"
        >
          {hata}
        </div>
      ) : null}

      {kayit ? (
        <label className="flex flex-col gap-1.5">
          <span className="text-xs font-semibold uppercase tracking-wide text-muted">
            Ad Soyad (isteğe bağlı)
          </span>
          <input
            type="text"
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            className="rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground"
          />
        </label>
      ) : null}

      <label className="flex flex-col gap-1.5">
        <span className="text-xs font-semibold uppercase tracking-wide text-muted">
          E-posta
        </span>
        <input
          type="email"
          required
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground"
        />
      </label>

      {kayit ? (
        <label className="flex flex-col gap-1.5">
          <span className="text-xs font-semibold uppercase tracking-wide text-muted">
            Şifre
          </span>
          <input
            type="password"
            required
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground"
          />
          <span className="text-xs text-muted">En az {EN_KISA_SIFRE} karakter.</span>
        </label>
      ) : null}

      <button
        type="submit"
        disabled={busy}
        data-testid={kayit ? "register-submit" : "reset-submit"}
        className="mt-2 rounded-lg bg-brand-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {busy ? "Lütfen bekleyin…" : kayit ? "Hesap oluştur" : "Sıfırlama bağlantısı gönder"}
      </button>

      {kayit ? (
        <p className="text-center text-xs leading-relaxed text-muted">
          Hesap oluşturmak tek başına bir yarışmaya erişim vermez. Sonucunuzu
          görebilmeniz için raporunuzun bu e-posta adresiyle yüklenmiş olması
          ve adresi doğrulamanız gerekiyor.
        </p>
      ) : null}

      <button
        type="button"
        onClick={onGeriDon}
        className="text-center text-sm font-semibold text-muted underline-offset-4 transition hover:text-brand-700 hover:underline"
      >
        Giriş ekranına dön
      </button>
    </form>
  );
}
