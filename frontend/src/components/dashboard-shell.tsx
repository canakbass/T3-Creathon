"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { getMyOrganization } from "@/lib/api";
import { ROLE_DEFINITIONS, type Role } from "@/lib/roles";
import { useAuthStore } from "@/store/auth-store";

interface DashboardShellProps {
  role: Role;
  children: React.ReactNode;
}

export function DashboardShell({ role, children }: DashboardShellProps) {
  const router = useRouter();
  const logout = useAuthStore((state) => state.logout);
  const organizationId = useAuthStore((state) => state.organizationId);
  const organizationName = useAuthStore((state) => state.organizationName);
  const setOrganization = useAuthStore((state) => state.setOrganization);
  const definition = ROLE_DEFINITIONS[role];

  // Kurum ADI her zaman elde olmuyor: kalıcı depodaki (localStorage) eski bir
  // oturum yalnızca kimliği taşıyor olabilir. Adı sunucudan tamamlıyoruz -
  // ham "org-cbu" göstermek, kullanıcının hangi kurum adına çalıştığını
  // anlamasına yetmez.
  useEffect(() => {
    if (!organizationId || organizationName) return;
    let iptal = false;
    (async () => {
      try {
        const kurum = await getMyOrganization();
        if (!iptal) setOrganization(kurum.id, kurum.name);
      } catch {
        // Kurum adı ikincil bir bilgi; alınamazsa panel çalışmaya devam
        // etmeli. Kimlik yine de gösteriliyor.
      }
    })();
    return () => {
      iptal = true;
    };
  }, [organizationId, organizationName, setOrganization]);

  function handleLogout() {
    logout();
    router.push("/");
  }

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b border-border bg-surface">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-4">
          <div>
            {/* KURUM ADI EN ÜSTTE ve rolden ÖNCE: aynı e-posta birden fazla
                kurumda olabiliyor ("hem TEKNOFEST yarışması hem ödev
                kontrolü için aynı maile bağlıysam?") ve yanlış kurumda işlem
                yapmak başka bir kurumun verisine dokunmak demek. Kullanıcı
                hangi kurum adına çalıştığını her an görmeli. */}
            <p
              data-testid="org-context"
              className="text-xs font-semibold uppercase tracking-wide text-brand-700"
            >
              {organizationName ?? organizationId ?? "AI Destekli Değerlendirme Sistemi"}
            </p>
            <h1 className="text-lg font-bold text-foreground">{definition.label} Paneli</h1>
          </div>
          <button
            type="button"
            onClick={handleLogout}
            className="rounded-lg border border-border px-4 py-2 text-sm font-semibold text-muted transition hover:border-brand-300 hover:text-brand-700"
          >
            Çıkış yap
          </button>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-6 py-10">{children}</main>
    </div>
  );
}
