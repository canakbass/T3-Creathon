"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { login as apiLogin, register as apiRegister, selectRole as apiSelectRole, type Session } from "@/lib/api";
import { describeError } from "@/lib/api/errors";
import { ROLE_DEFINITIONS, ROLES, getDashboardPath, isRole, type Role } from "@/lib/roles";
import { useAuthStore } from "@/store/auth-store";

const ROLE_ICON_PATHS: Record<Role, string> = {
  COMPETITION_MANAGER:
    "M3 7.5 12 3l9 4.5v9L12 21l-9-4.5v-9Zm9-1.7L5.5 9v6L12 18.2 18.5 15V9L12 5.8Z",
  REFEREE: "M12 2 4 5v6c0 5 3.4 8.7 8 10 4.6-1.3 8-5 8-10V5l-8-3Zm0 9.5 3 1.7-.8-3.4 2.6-2.3-3.5-.3L12 4l-1.3 3.2-3.5.3 2.6 2.3-.8 3.4L12 11.5Z",
  COMPETITOR: "M12 2a5 5 0 0 1 5 5c0 2.2-1.4 4-3.3 4.7L15 21H9l1.3-9.3C8.4 11 7 9.2 7 7a5 5 0 0 1 5-5Z",
  EVALUATION_MANAGER:
    "M4 4h16v3H4V4Zm0 6.5h10v3H4v-3ZM4 17h16v3H4v-3Zm13-6.5h3v3h-3v-3Z",
};

/** Ekranın hangi adımda olduğu. */
type Adim = "giris" | "kayit" | "rol-secimi";

export function RoleSelectionScreen() {
  const router = useRouter();
  const signIn = useAuthStore((state) => state.signIn);

  const [adim, setAdim] = useState<Adim>("giris");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [kayitRolleri, setKayitRolleri] = useState<Role[]>(["COMPETITOR"]);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // Rol seçimi adımında elde tutulan oturum (token alındı, rol seçilmedi).
  const [bekleyen, setBekleyen] = useState<Session | null>(null);

  function oturumuKur(session: Session) {
    signIn({
      token: session.token,
      role: session.activeRole ?? "",
      roles: session.roles,
      email: session.email,
      userId: session.userId,
      fullName: session.fullName,
    });
  }

  /** Oturum tamamsa panele gider; rol seçilmemişse seçim adımına geçer. */
  function oturumuIsle(session: Session) {
    if (session.activeRole && isRole(session.activeRole)) {
      oturumuKur(session);
      router.push(getDashboardPath(session.activeRole));
      return;
    }
    // Birden fazla rol var, kullanıcı hangisiyle devam edeceğini seçmeli.
    setBekleyen(session);
    setAdim("rol-secimi");
  }

  async function handleLogin(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      oturumuIsle(await apiLogin(email, password));
    } catch (cause) {
      setError(describeError(cause));
    } finally {
      setBusy(false);
    }
  }

  async function handleRegister(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (kayitRolleri.length === 0) {
      setError("En az bir rol seçin.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await apiRegister({ email, password, fullName, roles: kayitRolleri });
      // Kayıttan sonra doğrudan giriş yapıyoruz - kullanıcıyı ikinci kez
      // form doldurmaya zorlamanın bir faydası yok.
      oturumuIsle(await apiLogin(email, password));
    } catch (cause) {
      setError(describeError(cause));
    } finally {
      setBusy(false);
    }
  }

  async function handleSelectRole(role: Role) {
    if (!bekleyen) return;
    setBusy(true);
    setError(null);
    try {
      // Sunucu, seçilen role göre YENİ bir token imzalıyor. Arayüz kendi
      // başına rol değiştiremez.
      const session = await apiSelectRole(role, bekleyen.token);
      oturumuKur(session);
      router.push(getDashboardPath(role));
    } catch (cause) {
      setError(describeError(cause));
    } finally {
      setBusy(false);
    }
  }

  function rolDegistir(role: Role) {
    setKayitRolleri((mevcut) =>
      mevcut.includes(role) ? mevcut.filter((r) => r !== role) : [...mevcut, role],
    );
  }

  function modDegistir(yeni: Adim) {
    setAdim(yeni);
    setError(null);
    setInfo(null);
  }

  return (
    <main className="flex min-h-screen w-full flex-col items-center justify-center bg-background px-4 py-16">
      <div className="w-full max-w-xl">
        <div className="mb-8 text-center">
          <span className="inline-flex items-center rounded-full border border-border bg-surface px-3 py-1 text-xs font-semibold uppercase tracking-wide text-brand-700">
            AI Destekli Değerlendirme Sistemi
          </span>
          <h1 className="mt-4 text-3xl font-extrabold tracking-tight text-foreground sm:text-4xl">
            {adim === "kayit"
              ? "Hesap oluşturun"
              : adim === "rol-secimi"
                ? "Hangi rolle devam edeceksiniz?"
                : "Giriş yapın"}
          </h1>
          <p className="mt-3 text-sm text-muted sm:text-base">
            {adim === "rol-secimi"
              ? "Hesabınızın birden fazla rolü var. Bu oturumda kullanacağınız rolü seçin."
              : "TEKNOFEST rapor değerlendirme paneline erişmek için."}
          </p>
        </div>

        {error ? (
          <div
            role="alert"
            data-testid="login-error"
            className="mb-6 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-medium text-rose-700"
          >
            {error}
          </div>
        ) : null}
        {info ? (
          <div
            role="status"
            className="mb-6 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm font-medium text-emerald-700"
          >
            {info}
          </div>
        ) : null}

        {adim === "rol-secimi" ? (
          <>
            <div
              role="radiogroup"
              aria-label="Rolünüzü seçin"
              className="grid grid-cols-1 gap-4 sm:grid-cols-2"
            >
              {(bekleyen?.roles ?? []).filter(isRole).map((role) => {
                const definition = ROLE_DEFINITIONS[role];
                return (
                  <button
                    key={role}
                    type="button"
                    role="radio"
                    aria-checked="false"
                    disabled={busy}
                    data-testid={`role-card-${role}`}
                    onClick={() => handleSelectRole(role)}
                    className="group flex flex-col items-start gap-3 rounded-2xl border border-border bg-surface p-6 text-left shadow-sm transition hover:-translate-y-0.5 hover:border-brand-300 hover:shadow-md focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-brand-50 text-brand-600 transition group-hover:bg-brand-100">
                      <svg viewBox="0 0 24 24" fill="currentColor" className="h-6 w-6" aria-hidden="true">
                        <path d={ROLE_ICON_PATHS[role]} />
                      </svg>
                    </span>
                    <span className="text-base font-bold text-foreground">{definition.label}</span>
                    <span className="text-sm leading-relaxed text-muted">
                      {definition.description}
                    </span>
                  </button>
                );
              })}
            </div>
            <div className="mt-6 text-center">
              <button
                type="button"
                onClick={() => {
                  setBekleyen(null);
                  modDegistir("giris");
                }}
                className="text-sm font-semibold text-muted underline-offset-4 transition hover:text-brand-700 hover:underline"
              >
                Farklı bir hesapla giriş yap
              </button>
            </div>
          </>
        ) : (
          <form
            onSubmit={adim === "kayit" ? handleRegister : handleLogin}
            data-testid={adim === "kayit" ? "register-form" : "login-form"}
            className="flex flex-col gap-4 rounded-2xl border border-border bg-surface p-6 shadow-sm"
          >
            {adim === "kayit" ? (
              <label className="flex flex-col gap-1.5">
                <span className="text-xs font-semibold uppercase tracking-wide text-muted">
                  Ad Soyad
                </span>
                <input
                  type="text"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  className="rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
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
                className="rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
              />
            </label>

            <label className="flex flex-col gap-1.5">
              <span className="text-xs font-semibold uppercase tracking-wide text-muted">
                Şifre
              </span>
              <input
                type="password"
                required
                autoComplete={adim === "kayit" ? "new-password" : "current-password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
              />
            </label>

            {adim === "kayit" ? (
              <fieldset className="flex flex-col gap-2">
                <legend className="text-xs font-semibold uppercase tracking-wide text-muted">
                  Rolleriniz (birden fazla seçebilirsiniz)
                </legend>
                <div className="mt-1 grid grid-cols-1 gap-2 sm:grid-cols-2">
                  {ROLES.map((role) => (
                    <label
                      key={role}
                      className="flex cursor-pointer items-center gap-2 rounded-lg border border-border px-3 py-2 text-sm text-foreground transition hover:border-brand-300"
                    >
                      <input
                        type="checkbox"
                        checked={kayitRolleri.includes(role)}
                        onChange={() => rolDegistir(role)}
                        data-testid={`register-role-${role}`}
                        className="h-4 w-4"
                      />
                      {ROLE_DEFINITIONS[role].label}
                    </label>
                  ))}
                </div>
              </fieldset>
            ) : null}

            <button
              type="submit"
              disabled={busy}
              className="mt-2 rounded-lg bg-brand-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {busy ? "Lütfen bekleyin…" : adim === "kayit" ? "Kaydol" : "Giriş yap"}
            </button>

            <p className="text-center text-sm text-muted">
              {adim === "kayit" ? "Zaten hesabınız var mı? " : "Hesabınız yok mu? "}
              <button
                type="button"
                onClick={() => modDegistir(adim === "kayit" ? "giris" : "kayit")}
                className="font-semibold text-brand-700 underline-offset-4 hover:underline"
              >
                {adim === "kayit" ? "Giriş yapın" : "Kaydolun"}
              </button>
            </p>
          </form>
        )}

        {adim === "giris" ? (
          <details className="mx-auto mt-6 max-w-md rounded-xl border border-border bg-surface/60 px-4 py-3 text-sm">
            <summary className="cursor-pointer font-semibold text-muted">
              Demo hesapları
            </summary>
            <div className="mt-3 flex flex-col gap-2 text-xs text-muted">
              <p>
                <span className="font-semibold text-foreground">Tüm roller (test):</span>{" "}
                asdfghjkl@gmail.com / asdfghjkl
              </p>
              <p>manager@teknofest.org · referee@teknofest.org · competitor@teknofest.org · evaluator@teknofest.org</p>
              <p>Hepsinin şifresi: password123</p>
              <button
                type="button"
                onClick={() => {
                  setEmail("asdfghjkl@gmail.com");
                  setPassword("asdfghjkl");
                  setInfo("Test hesabı bilgileri dolduruldu — Giriş yap'a basın.");
                }}
                className="mt-1 w-fit rounded-lg border border-border px-3 py-1.5 font-semibold text-brand-700 transition hover:border-brand-300"
              >
                Test hesabını doldur
              </button>
            </div>
          </details>
        ) : null}
      </div>
    </main>
  );
}
