"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";
import { setTokenReader, setUnauthorizedHandler } from "@/lib/api/client";
import { isRole, type Role } from "@/lib/roles";

export interface AuthState {
  /** Bu oturumda AKTİF olan rol. Token da bu role göre imzalanmıştır. */
  role: Role | null;
  /** Kullanıcının sahip olduğu TÜM roller — rol değiştirme menüsü için. */
  roles: Role[];
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
  /** Başarılı bir `/api/auth/login` ya da `/select-role` sonrası oturumu kurar. */
  signIn: (session: {
    token: string;
    role: string;
    roles?: string[];
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
      token: null,
      email: null,
      fullName: null,
      userId: null,

      setRole: (role) => set({ role }),

      signIn: ({ token, role, roles, email, userId, fullName }) =>
        set({
          // Backend tanımadığımız bir rol döndürürse null bırakıyoruz;
          // RoleGuard bu durumda kullanıcıyı giriş ekranına geri gönderir.
          role: isRole(role) ? role : null,
          roles: (roles ?? []).filter(isRole),
          token,
          email,
          userId,
          fullName: fullName ?? null,
        }),

      logout: () =>
        set({
          role: null,
          roles: [],
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
