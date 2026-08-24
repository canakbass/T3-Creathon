"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";
import { setTokenReader, setUnauthorizedHandler } from "@/lib/api/client";
import { isRole, type Role } from "@/lib/roles";

export interface AuthState {
  role: Role | null;
  /** Backend'den alınan JWT. Giriş yapılmadıysa null. */
  token: string | null;
  /** Giriş yapan kullanıcının e-postası — panel başlığında gösterilir. */
  email: string | null;
  userId: string | null;

  /**
   * Sadece rolü değiştirir, oturum AÇMAZ.
   *
   * Gerçek giriş `signIn` ile yapılıyor. Bu fonksiyon geriye dönük uyumluluk
   * için duruyor (mevcut testler bunu kullanıyor) ve token gerektirmeyen
   * yönlendirme senaryolarında işe yarıyor.
   */
  setRole: (role: Role) => void;
  /** Başarılı bir `/api/auth/login` sonrası oturumu kurar. */
  signIn: (session: { token: string; role: string; email: string; userId: string }) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      role: null,
      token: null,
      email: null,
      userId: null,

      setRole: (role) => set({ role }),

      signIn: ({ token, role, email, userId }) =>
        set({
          // Backend tanımadığımız bir rol döndürürse null bırakıyoruz;
          // RoleGuard bu durumda kullanıcıyı giriş ekranına geri gönderir.
          role: isRole(role) ? role : null,
          token,
          email,
          userId,
        }),

      logout: () => set({ role: null, token: null, email: null, userId: null }),
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
