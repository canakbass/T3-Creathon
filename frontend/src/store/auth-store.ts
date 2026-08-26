"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";
import { setTokenReader, setUnauthorizedHandler } from "@/lib/api/client";
import { isRole, type Role } from "@/lib/roles";

export interface Membership {
  organizationId: string;
  organizationName: string | null;
  roles: string[];
}

export interface AuthState {
  /** Bu oturumda AKTİF olan rol. Token da bu role göre imzalanmıştır. */
  role: Role | null;
  /** Kullanıcının sahip olduğu TÜM roller — rol değiştirme menüsü için. */
  roles: Role[];
  /**
   * Bu oturumda AKTİF olan kurum. Token bunu da taşıyor.
   *
   * NEDEN SAKLANIYOR: kullanıcı hangi kurum adına işlem yaptığını her an
   * görmeli. Yanlış kurumda işlem yapmak, başka bir kurumun verisine
   * dokunmak demek — ve aynı e-posta birden fazla kurumda olabilir
   * ("hem TEKNOFEST yarışması hem ödev kontrolü için aynı maile bağlıysam?").
   */
  organizationId: string | null;
  organizationName: string | null;
  /** Hangi kurumda hangi roller — kurum/rol değiştirme menüsü için. */
  memberships: Membership[];
  /** Backend'den alınan JWT. Giriş yapılmadıysa null. */
  token: string | null;
  /** Giriş yapan kullanıcının e-postası — panel başlığında gösterilir. */
  email: string | null;
  fullName: string | null;
  userId: string | null;

  /**
   * Sadece rolü değiştirir, oturum AÇMAZ.
   *
   * Gerçek giriş `signIn` ile yapılıyor. Bu fonksiyon geriye dönük uyumluluk
   * için duruyor (mevcut testler bunu kullanıyor).
   */
  setRole: (role: Role) => void;
  /**
   * Kurumun ADINI tamamlar (kimliği değiştirmez).
   *
   * Kalıcı depodaki eski bir oturum yalnızca kimliği taşıyor olabilir; ham
   * "org-cbu" göstermek kullanıcının hangi kurum adına çalıştığını anlamasına
   * yetmez. YETKİYİ DEĞİŞTİRMEZ - yetki token'da ve yalnızca sunucu
   * imzalayabiliyor.
   */
  setOrganization: (organizationId: string, organizationName: string) => void;
  /** Başarılı bir `/api/auth/login` ya da `/select-role` sonrası oturumu kurar. */
  signIn: (session: {
    token: string;
    role: string;
    roles?: string[];
    organizationId?: string | null;
    organizationName?: string | null;
    memberships?: Membership[];
    email: string;
    userId: string;
    fullName?: string | null;
  }) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      role: null,
      roles: [],
      organizationId: null,
      organizationName: null,
      memberships: [],
      token: null,
      email: null,
      fullName: null,
      userId: null,

      setRole: (role) => set({ role }),

      setOrganization: (organizationId, organizationName) =>
        set({ organizationId, organizationName }),

      signIn: ({
        token,
        role,
        roles,
        organizationId,
        organizationName,
        memberships,
        email,
        userId,
        fullName,
      }) =>
        set({
          // Backend tanımadığımız bir rol döndürürse null bırakıyoruz;
          // RoleGuard bu durumda kullanıcıyı giriş ekranına geri gönderir.
          role: isRole(role) ? role : null,
          roles: (roles ?? []).filter(isRole),
          organizationId: organizationId ?? null,
          organizationName: organizationName ?? null,
          memberships: memberships ?? [],
          token,
          email,
          userId,
          fullName: fullName ?? null,
        }),

      logout: () =>
        set({
          role: null,
          roles: [],
          // Kurum bağlamı da SİLİNİYOR: kalsaydı, farklı bir kurumdaki
          // hesapla giriş yapan kullanıcı ekranda ESKİ kurumun adını
          // görürdü - yanlış kurum adına işlem yaptığını sanmasının en
          // kolay yolu.
          organizationId: null,
          organizationName: null,
          memberships: [],
          token: null,
          email: null,
          fullName: null,
          userId: null,
        }),
    }),
    {
      name: "aes-auth-storage",
    },
  ),
);

// API istemcisini store'a bağla.
//
// NEDEN BÖYLE: `lib/api/client.ts` bu store'u doğrudan import edemez, çünkü
// store da API istemcisini import ediyor — dairesel bağımlılık olurdu.
// Bunun yerine bağımlılık yönünü tersine çevirip okuyucuyu buradan
// enjekte ediyoruz.
setTokenReader(() => useAuthStore.getState().token);

// Token süresi dolduğunda (401) oturumu düşür. Aksi halde kullanıcı,
// her isteği sessizce başarısız olan "giriş yapmış" bir arayüzde kalırdı.
setUnauthorizedHandler(() => {
  if (useAuthStore.getState().token !== null) {
    useAuthStore.getState().logout();
  }
});
