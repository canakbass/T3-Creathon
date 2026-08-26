import { Suspense } from "react";
import { ResetPasswordScreen } from "@/components/auth/reset-password-screen";

/** Şifre sıfırlama sayfası: `/sifre-sifirla?token=...` */
export default function ResetPasswordPage() {
  return (
    <Suspense fallback={null}>
      <ResetPasswordScreen />
    </Suspense>
  );
}
