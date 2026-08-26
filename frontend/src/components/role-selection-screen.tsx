"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import {
  login as apiLogin,
  selectRole as apiSelectRole,
  type Membership,
  type Session,
} from "@/lib/api";
import { describeError } from "@/lib/api/errors";
import { ROLE_DEFINITIONS, getDashboardPath, isRole, type Role } from "@/lib/roles";
import { AccountForm } from "@/components/auth/account-forms";
import { NoMembershipScreen } from "@/components/auth/no-membership-screen";
import { useAuthStore } from "@/store/auth-store";

const ROLE_ICON_PATHS: Record<Role, string> = {
  ORG_OWNER:
    "M12 2 3 6v6c0 5 3.8 9.3 9 10 5.2-.7 9-5 9-10V6l-9-4Zm0 5a3 3 0 1 1 0 6 3 3 0 0 1 0-6Zm0 12c-2.2 0-4.2-1.1-5.4-2.8.9-1.6 3-2.7 5.4-2.7s4.5 1.1 5.4 2.7C16.2 17.9 14.2 19 12 19Z",
  COMPETITION_MANAGER:
    "M3 7.5 12 3l9 4.5v9L12 21l-9-4.5v-9Zm9-1.7L5.5 9v6L12 18.2 18.5 15V9L12 5.8Z",
  REFEREE:
    "M12 2 4 5v6c0 5 3.4 8.7 8 10 4.6-1.3 8-5 8-10V5l-8-3Zm0 9.5 3 1.7-.8-3.4 2.6-2.3-3.5-.3L12 4l-1.3 3.2-3.5.3 2.6 2.3-.8 3.4L12 11.5Z",
  COMPETITOR:
    "M12 2a5 5 0 0 1 5 5c0 2.2-1.4 4-3.3 4.7L15 21H9l1.3-9.3C8.4 11 7 9.2 7 7a5 5 0 0 1 5-5Z",
  EVALUATION_MANAGER:
    "M4 4h16v3H4V4Zm0 6.5h10v3H4v-3ZM4 17h16v3H4v-3Zm13-6.5h3v3h-3v-3Z",
};

/**
 * Giriş ve KURUM+ROL seçimi.
 *
 * NEDEN TEK SEÇİM: kurum ve rol ayrı ayrı seçilseydi "kurum seçildi ama rol
 * seçilmedi" gibi yarım bir durum oluşurdu ve o yarım oturumun ne göreceği
 * her ekranda ayrı ayrı düşünülmek zorunda kalırdı. Tek atomik seçim bu
 * sınıfı tümden yok ediyor.
 *
 * KAYIT ARTIK AÇIK ama tek başına hiçbir şey açmıyor: hesap açılıyor,
 * hiçbir rol ve hiçbir kurum verilmiyor. Sonucu görmenin yolu e-postayı
 * DOĞRULAMAK — çünkü bir raporun sonucunu TAKIM ÜYELİĞİ belirliyor, üyelik
 * e-postaya bağlı ve kayıt doğrulamasız açık olsaydı bir takım üyesinin
 * e-postasını ilk kaydettiren kişi o takımın sonuçlarını görürdü.
 *
 * Yönetici hesap açmaya devam ediyor (bkz. AccountCreator); o hesaplarda
 * kimliğe yönetici kefil oluyor. İki yol birbirinin yerine geçmiyor,
 * birbirini tamamlıyor.
 */
export function RoleSelectionScreen() {
  const router = useRouter();
  const signIn = useAuthStore((state) => state.signIn);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // Seçim adımında elde tutulan oturum (token alındı, kurum+rol seçilmedi).
  const [bekleyen, setBekleyen] = useState<Session | null>(null);
  const [adim, setAdim] = useState<"giris" | "kayit" | "sifremi-unuttum">("giris");

  function oturumuKur(session: Session, kurum: Membership | null) {
    signIn({
      token: session.token,
      role: session.activeRole ?? "",
      roles: session.roles,
      organizationId: session.activeOrganizationId,
      organizationName: kurum?.organizationName ?? null,
      memberships: session.memberships,
      email: session.email,
      userId: session.userId,
      fullName: session.fullName,
    });
  }

  /**
   * Oturum tamamsa panele gider; seçim gerekiyorsa seçim adımına geçer.
   *
   * ÜÇÜNCÜ BİR DURUM VAR ve atlanmıştı: hiçbir üyeliği olmayan hesap.
   * Kullanıcının bildirdiği hata buydu — "kurumu ve rolü seçin" yazıyordu
   * ama seçilecek HİÇBİR ŞEY yoktu. Kayıt hiçbir rol ve hiçbir kurum
   * vermiyor (vermemeli de), o yüzden bu durum NORMAL; yapılması gereken
   * kullanıcıya bir sonraki adımı göstermek.
   */
  function oturumuIsle(session: Session) {
    if (session.activeRole && isRole(session.activeRole)) {
      const kurum =
        session.memberships.find(
          (m) => m.organizationId === session.activeOrganizationId,
        ) ?? null;
      oturumuKur(session, kurum);
      router.push(getDashboardPath(session.activeRole));
      return;
    }
    setBekleyen(session);
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

  async function handleSelect(kurum: Membership, role: Role) {
    if (!bekleyen) return;
    setBusy(true);
    setError(null);
    try {
      // Sunucu, seçilen KURUM+ROL'e göre YENİ bir token imzalıyor. Arayüz
      // kendi başına ne rol ne kurum değiştirebilir.
      const session = await apiSelectRole(role, kurum.organizationId, bekleyen.token);
      oturumuKur(session, kurum);
      router.push(getDashboardPath(role));
    } catch (cause) {
      setError(describeError(cause));
    } finally {
      setBusy(false);
    }
  }

  const secimGerekli = bekleyen !== null;
  const uyeliksiz = bekleyen !== null && bekleyen.memberships.length === 0;

  if (uyeliksiz && bekleyen) {
    return (
      <NoMembershipScreen
        email={bekleyen.email}
        emailVerified={bekleyen.emailVerified}
        onKurumKuruldu={() => {
          // Oturumu tazelemek için giriş ekranına dönüyoruz: kurum
          // kurulduktan sonra token HÂLÂ rolsüz ve kurumsuz. Yeni yetkinin
          // token'a girmesi için sunucunun yeniden imzalaması gerekiyor -
          // arayüz kendi başına yetki ekleyemez.
          setBekleyen(null);
          setInfo(
            "Kurumunuz oluşturuldu. Sorumlu olarak girmek için tekrar giriş yapın.",
          );
        }}
        onCikis={() => {
          setBekleyen(null);
          setInfo(null);
        }}
      />
    );
  }

  if (!secimGerekli && adim !== "giris") {
    return (
      <main className="flex min-h-screen w-full flex-col items-center justify-center bg-background px-4 py-16">
        <div className="w-full max-w-md">
          <h1 className="mb-6 text-center text-3xl font-extrabold tracking-tight text-foreground">
            {adim === "kayit" ? "Hesap oluşturun" : "Şifremi unuttum"}
          </h1>
          <AccountForm mod={adim} onGeriDon={() => setAdim("giris")} />
        </div>
      </main>
    );
  }

  return (
    <main className="flex min-h-screen w-full flex-col items-center justify-center bg-background px-4 py-16">
      <div className="w-full max-w-xl">
        <div className="mb-8 text-center">
          <span className="inline-flex items-center rounded-full border border-border bg-surface px-3 py-1 text-xs font-semibold uppercase tracking-wide text-brand-700">
            AI Destekli Değerlendirme Sistemi
          </span>
          <h1 className="mt-4 text-3xl font-extrabold tracking-tight text-foreground sm:text-4xl">
            {secimGerekli ? "Hangi kurum adına devam edeceksiniz?" : "Giriş yapın"}
          </h1>
          <p className="mt-3 text-sm text-muted sm:text-base">
            {secimGerekli
              ? "Birden fazla seçeneğiniz var. Bu oturumda kullanacağınız kurumu ve rolü seçin."
              : "Rapor ve belge değerlendirme paneline erişmek için."}
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

        {secimGerekli ? (
          <>
            <div className="flex flex-col gap-6" data-testid="membership-picker">
              {(bekleyen?.memberships ?? []).map((kurum) => (
                <section key={kurum.organizationId}>
                  {/* Kurum adı BAŞLIK olarak duruyor, rol kartının içinde bir
                      etiket olarak değil: aynı rol iki kurumda da olabilir ve
                      kullanıcının önce "hangi kurum" sorusunu cevaplaması
                      gerekiyor. */}
                  <h2
                    data-testid={`org-heading-${kurum.organizationId}`}
                    className="mb-3 text-sm font-bold uppercase tracking-wide text-brand-700"
                  >
                    {kurum.organizationName ?? kurum.organizationId}
                  </h2>
                  <div
                    role="radiogroup"
                    aria-label={`${kurum.organizationName ?? kurum.organizationId} rolleri`}
                    className="grid grid-cols-1 gap-4 sm:grid-cols-2"
                  >
                    {kurum.roles.filter(isRole).map((role) => {
                      const definition = ROLE_DEFINITIONS[role];
                      return (
                        <button
                          key={role}
                          type="button"
                          role="radio"
                          aria-checked="false"
                          disabled={busy}
                          data-testid={`role-card-${kurum.organizationId}-${role}`}
                          onClick={() => handleSelect(kurum, role)}
                          className="group flex flex-col items-start gap-3 rounded-2xl border border-border bg-surface p-6 text-left shadow-sm transition hover:-translate-y-0.5 hover:border-brand-300 hover:shadow-md focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 disabled:cursor-not-allowed disabled:opacity-60"
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
                        </button>
                      );
                    })}
                  </div>
                </section>
              ))}
            </div>
            <div className="mt-8 text-center">
              <button
                type="button"
                onClick={() => {
                  setBekleyen(null);
                  setError(null);
                }}
                className="text-sm font-semibold text-muted underline-offset-4 transition hover:text-brand-700 hover:underline"
              >
                Farklı bir hesapla giriş yap
              </button>
            </div>
          </>
        ) : (
          <form
            onSubmit={handleLogin}
            data-testid="login-form"
            className="flex flex-col gap-4 rounded-2xl border border-border bg-surface p-6 shadow-sm"
          >
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
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
              />
            </label>

            <button
              type="submit"
              disabled={busy}
              className="mt-2 rounded-lg bg-brand-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {busy ? "Lütfen bekleyin…" : "Giriş yap"}
            </button>

            <div className="flex flex-wrap items-center justify-center gap-x-4 gap-y-1 text-sm">
              <button
                type="button"
                onClick={() => setAdim("kayit")}
                data-testid="go-register"
                className="font-semibold text-brand-700 underline-offset-4 hover:underline"
              >
                Hesap oluştur
              </button>
              <button
                type="button"
                onClick={() => setAdim("sifremi-unuttum")}
                data-testid="go-reset"
                className="font-semibold text-muted underline-offset-4 hover:text-brand-700 hover:underline"
              >
                Şifremi unuttum
              </button>
            </div>
            <p className="text-center text-xs leading-relaxed text-muted">
              Hesabınızı kurumunuzun yöneticisi de açabilir; o durumda giriş
              bilgileri size iletilir. Kendiniz kayıt olursanız sonucunuzu
              görebilmek için e-posta adresinizi doğrulamanız gerekir.
            </p>
          </form>
        )}

        {!secimGerekli ? (
          <details className="mx-auto mt-6 max-w-md rounded-xl border border-border bg-surface/60 px-4 py-3 text-sm">
            <summary className="cursor-pointer font-semibold text-muted">
              Demo hesapları
            </summary>
            <div className="mt-3 flex flex-col gap-2 text-xs text-muted">
              <p>
                <span className="font-semibold text-foreground">
                  T3 Vakfı — tüm roller:
                </span>{" "}
                asdfghjkl@gmail.com / asdfghjkl
              </p>
              <p>manager@teknofest.org · referee@teknofest.org · competitor@teknofest.org (password123)</p>
              {/* İkinci kurum: "A kurumu B'yi göremiyor" kuralı ancak karşı
                  tarafta gerçek hesaplar varsa denenebilir. */}
              <p>
                <span className="font-semibold text-foreground">
                  Manisa CBÜ — ayrı kurum:
                </span>{" "}
                sorumlu@cbu.edu.tr · ogretim@cbu.edu.tr (parola123)
              </p>
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
