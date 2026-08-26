"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { verifyEmail } from "@/lib/api";
import { describeError } from "@/lib/api/errors";

/**
 * E-posta doğrulama ekranı — `/dogrula?token=...`
 *
 * Bu adım, sonucu görmenin ön koşulu. Doğrulanmamış bir hesabın hiçbir
 * rolü, hiçbir kurumu, hiçbir takım bağı yok: bağ KAYIT anında değil
 * DOĞRULAMA anında kuruluyor. Aksi halde bir takım üyesinin e-postasını
 * ilk kaydettiren kişi o takımın sonuçlarını görürdü.
 */
export function VerifyEmailScreen() {
  const router = useRouter();
  const params = useSearchParams();
  const token = params.get("token") ?? "";

  const [durum, setDurum] = useState<"bekliyor" | "tamam" | "hata">("bekliyor");
  const [mesaj, setMesaj] = useState("");
  const [baglananTakim, setBaglananTakim] = useState(0);

  // Bir jeton YALNIZCA BİR KEZ tüketilebilir. React 18+ geliştirme modunda
  // efektleri iki kez çalıştırıyor; korunmasaydı ikinci çağrı "bu bağlantı
  // geçersiz" der ve kullanıcı doğrulanmış olduğu hâlde hata görürdü.
  const denendi = useRef(false);

  useEffect(() => {
    if (denendi.current) return;
    denendi.current = true;

    if (!token) {
      setDurum("hata");
      setMesaj("Doğrulama bağlantısı eksik. E-postadaki bağlantıyı tam olarak açın.");
      return;
    }
    (async () => {
      try {
        const sonuc = await verifyEmail(token);
        setDurum("tamam");
        setMesaj(sonuc.message);
        setBaglananTakim(sonuc.linked_teams);
      } catch (cause) {
        setDurum("hata");
        setMesaj(describeError(cause));
      }
    })();
  }, [token]);

  return (
    <main className="flex min-h-screen w-full items-center justify-center bg-background px-4 py-16">
      <div className="w-full max-w-md rounded-2xl border border-border bg-surface p-8 text-center shadow-sm">
        <h1 className="text-2xl font-extrabold text-foreground">E-posta doğrulama</h1>

        {durum === "bekliyor" ? (
          <p data-testid="verify-pending" className="mt-4 text-sm text-muted">
            Doğrulanıyor…
          </p>
        ) : null}

        {durum === "tamam" ? (
          <div data-testid="verify-success" className="mt-4 flex flex-col gap-3">
            <p className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm font-medium text-emerald-700">
              {mesaj}
            </p>
            {/* "Doğrulandı ama hiçbir şey görmüyorum" en olası kafa
                karışıklığı: kayıt olmak tek başına bir başvuruya erişim
                vermiyor. İki durumu AYIRARAK anlatıyoruz. */}
            <p className="text-sm text-muted">
              {baglananTakim > 0
                ? `${baglananTakim} başvurunuz hesabınıza bağlandı. Giriş yapıp sonucunuzu görebilirsiniz.`
                : "Şu an size ait bir başvuru bulunamadı. Raporunuz bu e-posta adresiyle yüklendiğinde otomatik olarak hesabınıza bağlanacak."}
            </p>
          </div>
        ) : null}

        {durum === "hata" ? (
          <div data-testid="verify-error" className="mt-4 flex flex-col gap-3">
            <p
              role="alert"
              className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-medium text-rose-700"
            >
              {mesaj}
            </p>
            <p className="text-sm text-muted">
              Bağlantının süresi dolmuş ya da daha önce kullanılmış olabilir.
              Giriş ekranından yeni bir doğrulama bağlantısı isteyebilirsiniz.
            </p>
          </div>
        ) : null}

        <button
          type="button"
          onClick={() => router.push("/")}
          data-testid="verify-go-login"
          className="mt-6 rounded-lg bg-brand-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-brand-700"
        >
          Giriş ekranına git
        </button>
      </div>
    </main>
  );
}
