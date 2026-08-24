"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { login as apiLogin, ApiError, NetworkError } from "@/lib/api";
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

/**
 * backend/main.py `seed_db()` ilk açılışta bu hesapları oluşturuyor.
 *
 * Rol kartına tıklamak, ilgili demo hesabıyla GERÇEK bir giriş yapar —
 * sahte bir rol seçimi değil. Demo'da tek tıkla ilerlemeyi korurken
 * arkada gerçek JWT alınıyor. Kendi hesabı olan kullanıcı aşağıdaki
 * formu kullanabilir.
 */
const DEMO_ACCOUNTS: Record<Role, { email: string; password: string }> = {
  COMPETITION_MANAGER: { email: "manager@teknofest.org", password: "password123" },
  REFEREE: { email: "referee@teknofest.org", password: "password123" },
  COMPETITOR: { email: "competitor@teknofest.org", password: "password123" },
  EVALUATION_MANAGER: { email: "evaluator@teknofest.org", password: "password123" },
};

export function RoleSelectionScreen() {
  const router = useRouter();
  const signIn = useAuthStore((state) => state.signIn);

  const [pendingRole, setPendingRole] = useState<Role | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [manualOpen, setManualOpen] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  async function authenticate(credentials: { email: string; password: string }) {
    setError(null);
    try {
      const user = await apiLogin(credentials.email, credentials.password);
      signIn({
        token: user.token,
        role: user.role,
        email: user.email,
        userId: user.id,
      });

      // Tıklanan karta değil, SUNUCUNUN döndürdüğü role göre yönlendiriyoruz.
      // Hesabın rolü demo eşleşmesinden farklıysa doğru panele gitmeli.
      if (!isRole(user.role)) {
        setError(`Sunucu tanınmayan bir rol döndürdü: "${user.role}".`);
        return;
      }
      router.push(getDashboardPath(user.role));
    } catch (cause) {
      if (cause instanceof NetworkError) {
        setError(cause.message);
      } else if (cause instanceof ApiError) {
        setError(
          cause.isUnauthorized ? "E-posta veya şifre hatalı." : cause.detail,
        );
      } else {
        setError("Beklenmeyen bir hata oluştu.");
      }
    }
  }

  async function handleSelectRole(role: Role) {
    setPendingRole(role);
    try {
      await authenticate(DEMO_ACCOUNTS[role]);
    } finally {
      setPendingRole(null);
    }
  }

  async function handleManualSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPendingRole("REFEREE"); // yalnızca "işlem sürüyor" durumunu tetiklemek için
    try {
      await authenticate({ email, password });
    } finally {
      setPendingRole(null);
    }
  }

  const busy = pendingRole !== null;

  return (
    <main className="flex min-h-screen w-full flex-col items-center justify-center bg-background px-4 py-16">
      <div className="w-full max-w-3xl">
        <div className="mb-10 text-center">
          <span className="inline-flex items-center rounded-full border border-border bg-surface px-3 py-1 text-xs font-semibold uppercase tracking-wide text-brand-700">
            AI Destekli Değerlendirme Sistemi
          </span>
          <h1 className="mt-4 text-3xl font-extrabold tracking-tight text-foreground sm:text-4xl">
            Devam etmek için giriş yapın
          </h1>
          <p className="mt-3 text-sm text-muted sm:text-base">
            Demo hesabıyla hızlıca girmek için rolünüzü seçin.
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

        <div
          role="radiogroup"
          aria-label="Rolünüzü seçin"
          className="grid grid-cols-1 gap-4 sm:grid-cols-2"
        >
          {ROLES.map((role) => {
            const definition = ROLE_DEFINITIONS[role];
            const isPending = pendingRole === role;
            return (
              <button
                key={role}
                type="button"
                role="radio"
                aria-checked="false"
                disabled={busy}
                data-testid={`role-card-${role}`}
                onClick={() => handleSelectRole(role)}
                className="group flex flex-col items-start gap-3 rounded-2xl border border-border bg-surface p-6 text-left shadow-sm transition hover:-translate-y-0.5 hover:border-brand-300 hover:shadow-md focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60"
              >
                <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-brand-50 text-brand-600 transition group-hover:bg-brand-100">
                  <svg
                    viewBox="0 0 24 24"
                    fill="currentColor"
                    className="h-6 w-6"
                    aria-hidden="true"
                  >
                    <path d={ROLE_ICON_PATHS[role]} />
                  </svg>
                </span>
                <span className="text-base font-bold text-foreground">
                  {definition.label}
                </span>
                <span className="text-sm leading-relaxed text-muted">
                  {definition.description}
                </span>
                {isPending ? (
                  <span className="text-xs font-semibold text-brand-700">
                    Giriş yapılıyor…
                  </span>
                ) : null}
              </button>
            );
          })}
        </div>

        <div className="mt-8 text-center">
          <button
            type="button"
            onClick={() => setManualOpen((open) => !open)}
            className="text-sm font-semibold text-muted underline-offset-4 transition hover:text-brand-700 hover:underline"
          >
            {manualOpen ? "Demo hesaplarına dön" : "Farklı bir hesapla giriş yap"}
          </button>
        </div>

        {manualOpen ? (
          <form
            onSubmit={handleManualSubmit}
            data-testid="manual-login-form"
            className="mx-auto mt-6 flex w-full max-w-sm flex-col gap-4 rounded-2xl border border-border bg-surface p-6 shadow-sm"
          >
            <label className="flex flex-col gap-1.5 text-left">
              <span className="text-xs font-semibold uppercase tracking-wide text-muted">
                E-posta
              </span>
              <input
                type="email"
                required
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                className="rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
              />
            </label>
            <label className="flex flex-col gap-1.5 text-left">
              <span className="text-xs font-semibold uppercase tracking-wide text-muted">
                Şifre
              </span>
              <input
                type="password"
                required
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                className="rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
              />
            </label>
            <button
              type="submit"
              disabled={busy}
              className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {busy ? "Giriş yapılıyor…" : "Giriş yap"}
            </button>
          </form>
        ) : null}
      </div>
    </main>
  );
}
