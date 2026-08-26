"use client";

import { useState } from "react";
import { createOrganization, resendVerification } from "@/lib/api";
import { describeError } from "@/lib/api/errors";

/**
 * Hiçbir kuruma bağlı olmayan hesabın gördüğü ekran.
 *
 * KULLANICININ BİLDİRDİĞİ HATA: yeni bir hesap açıp giriş yapınca
 * "Birden fazla seçeneğiniz var, kurumu ve rolü seçin" yazıyordu ama
 * SEÇİLECEK HİÇBİR ŞEY YOKTU — ölü bir yol.
 *
 * Sebebi şu: kayıt hiçbir rol ve hiçbir kurum vermiyor (vermemeli de).
 * Kuruma giriş iki yoldan geliyor — ya doğrulanmış e-posta yöneticinin
 * yüklediği bir raporun takımıyla eşleşir, ya da kişi kendi kurumunu kurar.
 * Ekran o iki yolu AÇIKÇA gösteriyor.
 *
 * ÜÇ DURUM AYRI AYRI ANLATILIYOR, çünkü "hiçbir şey göremiyorum"un üç farklı
 * sebebi var ve kullanıcının hangisinde olduğunu bilmesi gerekiyor:
 *   1. E-posta doğrulanmadı        → doğrula
 *   2. Doğrulandı, başvuru yok     → bekle (ya da kendi kurumunu kur)
 *   3. Kendi kurumu için kullanacak → kurum oluştur
 */

interface Props {
  email: string;
  emailVerified: boolean;
  /** Kurum kurulduktan sonra oturumu tazelemek için. */
  onKurumKuruldu: () => void;
  onCikis: () => void;
}

export function NoMembershipScreen({
  email,
  emailVerified,
  onKurumKuruldu,
  onCikis,
}: Props) {
  const [kurumAdi, setKurumAdi] = useState("");
  const [formAcik, setFormAcik] = useState(false);
  const [hata, setHata] = useState<string | null>(null);
  const [bilgi, setBilgi] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function tekrarGonder() {
    setBusy(true);
    setHata(null);
    try {
      const sonuc = await resendVerification(email);
      setBilgi(sonuc.message);
    } catch (cause) {
      setHata(describeError(cause));
    } finally {
      setBusy(false);
    }
  }

  async function kurumKur(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setHata(null);
    try {
      await createOrganization(kurumAdi);
      onKurumKuruldu();
    } catch (cause) {
      setHata(describeError(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-screen w-full items-center justify-center bg-background px-4 py-16">
      <div className="w-full max-w-lg">
        <h1 className="text-center text-2xl font-extrabold text-foreground">
          {emailVerified ? "Henüz bir başvurunuz yok" : "E-postanızı doğrulayın"}
        </h1>
        <p className="mt-2 text-center text-sm text-muted">{email}</p>

        {hata ? (
          <p
            role="alert"
            data-testid="no-membership-error"
            className="mt-6 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-medium text-rose-700"
          >
            {hata}
          </p>
        ) : null}
        {bilgi ? (
          <p
            role="status"
            data-testid="no-membership-info"
            className="mt-6 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm font-medium text-emerald-700"
          >
            {bilgi}
          </p>
        ) : null}

        {!emailVerified ? (
          <section
            data-testid="verify-prompt"
            className="mt-6 rounded-2xl border border-border bg-surface p-6 shadow-sm"
          >
            <p className="text-sm leading-relaxed text-foreground">
              Size bir doğrulama bağlantısı gönderdik. Sonuçlarınızı
              görebilmeniz için bu adresin sizin olduğunu doğrulamanız
              gerekiyor.
            </p>
            <p className="mt-2 text-xs leading-relaxed text-muted">
              Bir raporun sonucunu takım üyeliği belirliyor ve üyelik e-postaya
              bağlı — doğrulama olmadan, adresi ilk yazan kişi o takımın
              sonuçlarını görebilirdi.
            </p>
            <button
              type="button"
              onClick={tekrarGonder}
              disabled={busy}
              data-testid="resend-verification"
              className="mt-4 rounded-lg border border-border px-4 py-2 text-sm font-semibold text-muted transition hover:border-brand-300 hover:text-brand-700 disabled:opacity-60"
            >
              Bağlantıyı tekrar gönder
            </button>
          </section>
        ) : (
          <section
            data-testid="waiting-prompt"
            className="mt-6 rounded-2xl border border-border bg-surface p-6 shadow-sm"
          >
            <p className="text-sm leading-relaxed text-foreground">
              E-posta adresiniz doğrulandı. Şu an bu adrese bağlı bir başvuru
              bulunmuyor.
            </p>
            <p className="mt-2 text-xs leading-relaxed text-muted">
              Raporunuz bu e-posta adresiyle sisteme yüklendiğinde otomatik
              olarak hesabınıza bağlanacak ve sonucunuzu burada göreceksiniz.
              Yapmanız gereken başka bir şey yok.
            </p>
          </section>
        )}

        {/* KENDİ KURUMUNU KURMA yolu her iki durumda da görünüyor: kişi
            sonuç bekleyen bir yarışmacı değil, sistemi kendi kurumu için
            kullanmak isteyen biri olabilir. Doğrulama şartı sunucuda —
            doğrulanmamış adresle kurum açılabilseydi sahte adreslerle
            sınırsız kiracı üretilebilirdi. */}
        <section className="mt-4 rounded-2xl border border-border bg-surface p-6 shadow-sm">
          <h2 className="text-sm font-bold text-foreground">
            Sistemi kendi kurumunuz için mi kullanacaksınız?
          </h2>
          <p className="mt-1 text-xs leading-relaxed text-muted">
            Kendi kurumunuzu oluşturup rapor, ödev veya başvuru
            değerlendirmesi yapabilirsiniz. Kurumunuz size özel olur; başka
            hiçbir kurumun verisi görünmez.
          </p>

          {formAcik ? (
            <form onSubmit={kurumKur} className="mt-4 flex flex-col gap-3">
              <label className="flex flex-col gap-1 text-xs text-muted">
                Kurum adı
                <input
                  value={kurumAdi}
                  onChange={(e) => setKurumAdi(e.target.value)}
                  required
                  minLength={3}
                  placeholder="Örn. Ege Üniversitesi Mühendislik Fakültesi"
                  data-testid="org-name"
                  aria-label="Kurum adı"
                  className="rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground"
                />
              </label>
              <div className="flex gap-2">
                <button
                  type="submit"
                  disabled={busy || kurumAdi.trim().length < 3}
                  data-testid="org-create-submit"
                  className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {busy ? "Oluşturuluyor…" : "Kurumu oluştur"}
                </button>
                <button
                  type="button"
                  onClick={() => setFormAcik(false)}
                  className="rounded-lg border border-border px-4 py-2 text-sm font-semibold text-muted"
                >
                  Vazgeç
                </button>
              </div>
            </form>
          ) : (
            <button
              type="button"
              onClick={() => setFormAcik(true)}
              data-testid="org-create-open"
              className="mt-4 rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-brand-700"
            >
              Kurum oluştur
            </button>
          )}
        </section>

        <button
          type="button"
          onClick={onCikis}
          data-testid="no-membership-logout"
          className="mx-auto mt-6 block text-sm font-semibold text-muted underline-offset-4 hover:text-brand-700 hover:underline"
        >
          Farklı bir hesapla giriş yap
        </button>
      </div>
    </main>
  );
}
