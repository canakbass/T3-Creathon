import { Suspense } from "react";
import { VerifyEmailScreen } from "@/components/auth/verify-email-screen";

/**
 * E-posta doğrulama sayfası.
 *
 * Bağlantı e-postadan geliyor: `/dogrula?token=...`. Jetonu yalnızca posta
 * kutusunun sahibi görüyor — doğrulamanın tamamı buna dayanıyor.
 */
export default function VerifyEmailPage() {
  return (
    <Suspense fallback={null}>
      <VerifyEmailScreen />
    </Suspense>
  );
}
