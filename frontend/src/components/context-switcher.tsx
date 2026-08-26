"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { selectRole as apiSelectRole } from "@/lib/api";
import { describeError } from "@/lib/api/errors";
import { ROLE_DEFINITIONS, ROLES, getDashboardPath, isRole, type Role } from "@/lib/roles";
import { useAuthStore } from "@/store/auth-store";

/**
 * Kurum ve rol değiştirici.
 *
 * NEDEN GEREKLİ: aynı e-posta birden fazla kurumda olabiliyor ve her kurumda
 * farklı rollere sahip olabiliyor. Değiştirmenin tek yolu çıkıp tekrar giriş
 * yapmak olsaydı, iki kuruma bağlı bir kullanıcı gün içinde defalarca şifre
 * girerdi.
 *
 * YETKİYİ ARAYÜZ DEĞİŞTİRMİYOR: seçim sunucuya gidiyor ve sunucu O KURUM+ROL
 * için YENİ bir token imzalıyor. Arayüz "ben şimdi yöneticiyim" diyerek yetki
 * kazanamaz — yetkiyi token taşıyor ve token'ı yalnızca sunucu imzalayabilir.
 *
 * KURUM SORUMLUSU KENDİ KURUMUNDA HER ROLÜ görebilir ("bu superuserlar her
 * role bakabilmeli"): o rolü kendine zaten verebildiği için engellemek
 * güvenlik değil yalnızca fazladan iki tıklama sağlardı.
 */
export function ContextSwitcher() {
  const router = useRouter();
  const signIn = useAuthStore((state) => state.signIn);
  const aktifRol = useAuthStore((state) => state.role);
  const aktifKurum = useAuthStore((state) => state.organizationId);
  const uyelikler = useAuthStore((state) => state.memberships);

  const [acik, setAcik] = useState(false);
  const [calisiyor, setCalisiyor] = useState(false);
  const [hata, setHata] = useState<string | null>(null);

  // Bir kurumda ORG_OWNER isek o kurumun TÜM rolleri seçilebilir.
  const secenekler = uyelikler.flatMap((u) => {
    const roller = u.roles.includes("ORG_OWNER") ? [...ROLES] : u.roles.filter(isRole);
    return roller.map((rol) => ({ kurum: u, rol: rol as Role }));
  });

  // Tek seçenek varsa değiştirecek bir şey yok; düğmeyi göstermiyoruz.
  if (secenekler.length <= 1) return null;

  async function gec(kurumId: string, kurumAdi: string | null, rol: Role) {
    setCalisiyor(true);
    setHata(null);
    try {
      const oturum = await apiSelectRole(rol, kurumId);
      signIn({
        token: oturum.token,
        role: oturum.activeRole ?? rol,
        roles: oturum.roles,
        organizationId: oturum.activeOrganizationId,
        organizationName: kurumAdi,
        memberships: oturum.memberships,
        email: oturum.email,
        userId: oturum.userId,
        fullName: oturum.fullName,
      });
      setAcik(false);
      router.push(getDashboardPath(rol));
    } catch (cause) {
      setHata(describeError(cause));
    } finally {
      setCalisiyor(false);
    }
  }

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setAcik((a) => !a)}
        aria-expanded={acik}
        data-testid="context-switch-toggle"
        className="rounded-lg border border-border px-3 py-2 text-sm font-semibold text-muted transition hover:border-brand-300 hover:text-brand-700"
      >
        Kurum / rol değiştir
      </button>

      {acik ? (
        <div
          data-testid="context-switch-panel"
          className="absolute right-0 z-10 mt-2 w-72 rounded-xl border border-border bg-surface p-2 shadow-lg"
        >
          {hata ? (
            <p
              role="alert"
              data-testid="context-switch-error"
              className="mb-2 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700"
            >
              {hata}
            </p>
          ) : null}

          <ul className="flex flex-col gap-1">
            {secenekler.map(({ kurum, rol }) => {
              const secili = kurum.organizationId === aktifKurum && rol === aktifRol;
              return (
                <li key={`${kurum.organizationId}:${rol}`}>
                  <button
                    type="button"
                    disabled={calisiyor || secili}
                    data-testid={`context-option-${kurum.organizationId}-${rol}`}
                    onClick={() =>
                      gec(kurum.organizationId, kurum.organizationName, rol)
                    }
                    className={`flex w-full flex-col items-start rounded-lg px-3 py-2 text-left text-sm transition disabled:cursor-default ${
                      secili
                        ? "bg-brand-50 text-brand-700"
                        : "text-foreground hover:bg-background"
                    }`}
                  >
                    <span className="text-xs font-semibold uppercase tracking-wide text-muted">
                      {kurum.organizationName ?? kurum.organizationId}
                    </span>
                    <span className="font-semibold">
                      {ROLE_DEFINITIONS[rol].label}
                      {secili ? " · şu an" : ""}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
