"use client";

import { useEffect, useState } from "react";
import {
  grantOrganizationRole,
  listOrganizationMembers,
  revokeOrganizationRole,
} from "@/lib/api";
import { describeError } from "@/lib/api/errors";
import { ROLES, ROLE_DEFINITIONS, isRole } from "@/lib/roles";
import type { WireOrganizationMember } from "@/lib/api/types";

/**
 * Kurum sorumlusunun ÜYE YÖNETİMİ ekranı.
 *
 * Kullanıcının istediği şey: "bu superuserlar kendi kurumundaki hakemleri,
 * yöneticileri, değerlendirme yöneticileri gibi herkesi değiştirebilmeli,
 * ekleyebilmeli."
 *
 * NEDEN AYRI BİR EKRAN: hesap AÇMA (AccountCreator) ile ROL DEĞİŞTİRME ayrı
 * işler. Hesap açmak kimliğe kefil olmak; rol değiştirmek mevcut bir kişinin
 * yetkisini değiştirmek. İkisi tek formda olsaydı "yeni hesap mı açıyorum,
 * var olanı mı değiştiriyorum" sorusu her seferinde belirsiz kalırdı.
 *
 * BURADA GÖRÜNEN ROLLER YALNIZCA BU KURUMDAKİLER. Aynı kişi başka bir
 * kurumda bambaşka rollere sahip olabilir ve o roller burada GÖRÜNMEZ -
 * görünse, bir kurumun sorumlusu üyesinin başka kurumlardaki konumunu
 * öğrenirdi.
 */
export function MemberManager() {
  const [uyeler, setUyeler] = useState<WireOrganizationMember[] | null>(null);
  const [hata, setHata] = useState<string | null>(null);
  const [calisan, setCalisan] = useState<string | null>(null);
  const [arama, setArama] = useState("");

  useEffect(() => {
    let iptal = false;
    (async () => {
      try {
        const liste = await listOrganizationMembers();
        if (!iptal) setUyeler(liste);
      } catch (cause) {
        if (!iptal) setHata(describeError(cause));
      }
    })();
    return () => {
      iptal = true;
    };
  }, []);

  /**
   * Sunucudan dönen üyeyi listeye yazar.
   *
   * Sunucunun döndürdüğü rolleri kullanıyoruz, elde tahmin etmiyoruz: son
   * sözü kimin söylediği belirsiz kalırsa ekran, sunucunun reddettiği bir
   * değişikliği yapılmış gibi gösterebilir.
   */
  function guncelle(yeni: WireOrganizationMember) {
    setUyeler((mevcut) =>
      (mevcut ?? []).map((u) => (u.id === yeni.id ? yeni : u)),
    );
  }

  async function ver(uye: WireOrganizationMember, rol: string) {
    setCalisan(uye.id);
    setHata(null);
    try {
      guncelle(await grantOrganizationRole(uye.id, rol));
    } catch (cause) {
      setHata(describeError(cause));
    } finally {
      setCalisan(null);
    }
  }

  async function al(uye: WireOrganizationMember, rol: string) {
    setCalisan(uye.id);
    setHata(null);
    try {
      guncelle(await revokeOrganizationRole(uye.id, rol));
    } catch (cause) {
      // Kurumun SON sorumlusu kaldırılamaz; sunucu bunu 400 ile söylüyor ve
      // mesajı olduğu gibi gösteriyoruz - kurum sorumlusuz kalırsa üye
      // yönetimi tamamen kilitlenir.
      setHata(describeError(cause));
    } finally {
      setCalisan(null);
    }
  }

  const gorunen = (uyeler ?? []).filter((u) => {
    const q = arama.trim().toLocaleLowerCase("tr");
    if (!q) return true;
    return (
      u.email.toLocaleLowerCase("tr").includes(q) ||
      (u.full_name ?? "").toLocaleLowerCase("tr").includes(q)
    );
  });

  return (
    <section
      data-testid="member-manager"
      className="rounded-2xl border border-border bg-surface p-6 shadow-sm"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold text-foreground">Kurum Üyeleri</h2>
          <p className="mt-1 text-sm text-muted">
            Yalnızca kendi kurumunuzun üyelerini görür ve değiştirirsiniz.
          </p>
        </div>
        <input
          value={arama}
          onChange={(e) => setArama(e.target.value)}
          placeholder="E-posta ya da ad ara"
          data-testid="member-search"
          aria-label="Üye ara"
          className="rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground"
        />
      </div>

      {hata ? (
        <p
          role="alert"
          data-testid="member-error"
          className="mt-4 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700"
        >
          {hata}
        </p>
      ) : null}

      {uyeler === null && !hata ? (
        <p className="mt-4 text-sm text-muted">Yükleniyor…</p>
      ) : null}

      {uyeler !== null && gorunen.length === 0 ? (
        <p data-testid="member-empty" className="mt-4 text-sm text-muted">
          {uyeler.length === 0
            ? "Kurumda henüz üye yok. Hesap Aç bölümünden ekleyebilirsiniz."
            : "Aramaya uyan üye yok."}
        </p>
      ) : null}

      <ul className="mt-4 flex flex-col gap-3">
        {gorunen.map((uye) => (
          <li
            key={uye.id}
            data-testid={`member-${uye.email}`}
            className="rounded-xl border border-border px-4 py-3"
          >
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <span className="text-sm font-semibold text-foreground">{uye.email}</span>
              {uye.full_name ? (
                <span className="text-xs text-muted">{uye.full_name}</span>
              ) : null}
            </div>

            <div className="mt-3 flex flex-wrap gap-2">
              {ROLES.map((rol) => {
                const sahip = uye.roles.includes(rol);
                return (
                  <button
                    key={rol}
                    type="button"
                    disabled={calisan === uye.id}
                    aria-pressed={sahip}
                    data-testid={`member-${uye.email}-${rol}`}
                    onClick={() => (sahip ? al(uye, rol) : ver(uye, rol))}
                    className={`rounded-lg border px-3 py-1 text-xs font-semibold transition disabled:cursor-not-allowed disabled:opacity-60 ${
                      sahip
                        ? "border-brand-300 bg-brand-50 text-brand-700"
                        : "border-border text-muted hover:border-brand-300 hover:text-brand-700"
                    }`}
                  >
                    {ROLE_DEFINITIONS[rol].label}
                  </button>
                );
              })}
            </div>

            {/* Sunucu tanımadığımız bir rol döndürürse SESSİZCE yutmuyoruz:
                yetkisi olan bir rolün ekranda görünmemesi, sorumlunun
                "bu kişinin yetkisi yok" sanmasına yol açar. */}
            {uye.roles.some((r) => !isRole(r)) ? (
              <p className="mt-2 text-xs text-amber-700">
                Bu üyenin arayüzün tanımadığı rolleri var:{" "}
                {uye.roles.filter((r) => !isRole(r)).join(", ")}
              </p>
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  );
}
