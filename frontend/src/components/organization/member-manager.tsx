"use client";

import { useCallback, useEffect, useRef, useState } from "react";
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
 * ekleyebilmeli" — ve sonrasında: "herkesi dizmeyelim, sayfalama ve role göre
 * filtreleme olsun".
 *
 * FİLTRELEME VE SAYFALAMA SUNUCUDA. Tüm üyeleri çekip tarayıcıda kesmek
 * "sayfalama" görünümü verirken rehberin TAMAMINI yine de tel üzerinden
 * geçirirdi; listenin yalnızca sorumluya açık olmasının anlamı kalmazdı.
 *
 * NEDEN AYRI BİR EKRAN: hesap AÇMAK (kimliğe kefil olmak) ile mevcut bir
 * üyenin ROLÜNÜ değiştirmek ayrı işler. Tek formda olsalardı "yeni hesap mı
 * açıyorum, var olanı mı değiştiriyorum" sorusu her seferinde belirsiz
 * kalırdı.
 *
 * BURADA GÖRÜNEN ROLLER YALNIZCA BU KURUMDAKİLER. Aynı kişi başka bir
 * kurumda bambaşka rollere sahip olabilir ve o roller burada GÖRÜNMEZ —
 * görünse, bir kurumun sorumlusu üyesinin başka kurumlardaki konumunu
 * öğrenirdi.
 */

const SAYFA_BOYU = 25;
/** Arama kutusunda yazmayı bırakınca kaç ms sonra istek atılsın. */
const ARAMA_GECIKMESI_MS = 300;

export function MemberManager() {
  const [uyeler, setUyeler] = useState<WireOrganizationMember[] | null>(null);
  const [toplam, setToplam] = useState(0);
  const [sayfa, setSayfa] = useState(0);
  // Sunucunun GERCEKTEN uyguladigi sayfa penceresi. Kendi sabitimizi
  // kullanmiyoruz: sunucu `limit`i kendi ust siniriyla kirpabilir ve o
  // durumda "3 / 1" gibi imkansiz bir sayfa numarasi gosterirdik.
  const [pencere, setPencere] = useState({ limit: SAYFA_BOYU, offset: 0, adet: 0 });
  const [rol, setRol] = useState("");
  const [arama, setArama] = useState("");
  const [gecikmisArama, setGecikmisArama] = useState("");
  const [hata, setHata] = useState<string | null>(null);
  const [calisan, setCalisan] = useState<string | null>(null);
  const [yukleniyor, setYukleniyor] = useState(true);

  // Arama kutusu her tuşta istek atmasın: yönetici "mehmet" yazarken altı
  // ayrı istek gider, cevaplar sırasız dönerse ekranda YANLIŞ sonuç kalır.
  useEffect(() => {
    const zamanlayici = setTimeout(() => setGecikmisArama(arama), ARAMA_GECIKMESI_MS);
    return () => clearTimeout(zamanlayici);
  }, [arama]);

  // Filtre değişince ilk sayfaya dön: 4. sayfadayken filtre daraltılırsa
  // sonuç 1 sayfaya düşer ve kullanıcı BOŞ bir sayfada kalırdı.
  useEffect(() => {
    setSayfa(0);
  }, [rol, gecikmisArama]);

  // Sıra numarası: yalnızca EN SON istek ekrana yazsın. Yavaş dönen eski bir
  // istek, yeni sonucun üstüne yazarsa kullanıcı filtresine uymayan bir liste
  // görür ve nedenini anlayamaz.
  const istekSirasi = useRef(0);

  const yukle = useCallback(async () => {
    const benim = ++istekSirasi.current;
    setYukleniyor(true);
    try {
      const sayfaVerisi = await listOrganizationMembers({
        role: rol || null,
        q: gecikmisArama || null,
        limit: SAYFA_BOYU,
        offset: sayfa * SAYFA_BOYU,
      });
      if (benim !== istekSirasi.current) return;
      setUyeler(sayfaVerisi.items);
      setToplam(sayfaVerisi.total);
      setPencere({
        limit: sayfaVerisi.limit || SAYFA_BOYU,
        offset: sayfaVerisi.offset ?? 0,
        adet: sayfaVerisi.items.length,
      });
      setHata(null);
    } catch (cause) {
      if (benim !== istekSirasi.current) return;
      setHata(describeError(cause));
      setUyeler([]);
    } finally {
      if (benim === istekSirasi.current) setYukleniyor(false);
    }
  }, [rol, gecikmisArama, sayfa]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  /**
   * Sunucudan dönen üyeyi listeye yazar.
   *
   * Sunucunun döndürdüğü rolleri kullanıyoruz, elde tahmin etmiyoruz: son
   * sözü kimin söylediği belirsiz kalırsa ekran, sunucunun reddettiği bir
   * değişikliği yapılmış gibi gösterebilir.
   */
  function guncelle(yeni: WireOrganizationMember) {
    setUyeler((mevcut) => (mevcut ?? []).map((u) => (u.id === yeni.id ? yeni : u)));
  }

  async function ver(uye: WireOrganizationMember, secilen: string) {
    setCalisan(uye.id);
    setHata(null);
    try {
      guncelle(await grantOrganizationRole(uye.id, secilen));
    } catch (cause) {
      setHata(describeError(cause));
    } finally {
      setCalisan(null);
    }
  }

  async function al(uye: WireOrganizationMember, secilen: string) {
    setCalisan(uye.id);
    setHata(null);
    try {
      guncelle(await revokeOrganizationRole(uye.id, secilen));
    } catch (cause) {
      // Kurumun SON sorumlusu kaldırılamaz; sunucu bunu 400 ile söylüyor ve
      // mesajı olduğu gibi gösteriyoruz — kurum sorumlusuz kalırsa üye
      // yönetimi tamamen kilitlenir.
      setHata(describeError(cause));
    } finally {
      setCalisan(null);
    }
  }

  // Aralik ve gezinme, SUNUCUNUN dondugu pencereden hesaplaniyor - kendi
  // sayfa sayacimizdan degil. "Sonraki var mi" sorusunun en dogru cevabi
  // "gosterdigim son kayit toplamdan kucuk mu": sunucu limiti kirpsa da,
  // arada kayit silinse de dogru kalir.
  const ilk = toplam === 0 ? 0 : pencere.offset + 1;
  const son = pencere.offset + pencere.adet;
  const sonrakiVar = son < toplam;
  const oncekiVar = pencere.offset > 0;
  const sayfaNo = Math.floor(pencere.offset / pencere.limit) + 1;
  const sayfaAdedi = Math.max(1, Math.ceil(toplam / pencere.limit));

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
        <div className="flex flex-wrap items-center gap-2">
          <select
            value={rol}
            onChange={(e) => setRol(e.target.value)}
            data-testid="member-role-filter"
            aria-label="Role göre filtrele"
            className="rounded-lg border border-border bg-background px-2 py-1.5 text-sm text-foreground"
          >
            <option value="">Tüm roller</option>
            {ROLES.map((r) => (
              <option key={r} value={r}>
                {ROLE_DEFINITIONS[r].label}
              </option>
            ))}
          </select>
          <input
            value={arama}
            onChange={(e) => setArama(e.target.value)}
            placeholder="E-posta ya da ad ara"
            data-testid="member-search"
            aria-label="Üye ara"
            className="rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground"
          />
        </div>
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

      {uyeler === null ? (
        <p className="mt-4 text-sm text-muted">Yükleniyor…</p>
      ) : null}

      {uyeler !== null && uyeler.length === 0 && !hata ? (
        <p data-testid="member-empty" className="mt-4 text-sm text-muted">
          {rol || gecikmisArama
            ? "Bu filtreye uyan üye yok."
            : "Kurumda henüz üye yok. Hesap Aç bölümünden ekleyebilirsiniz."}
        </p>
      ) : null}

      <ul className="mt-4 flex flex-col gap-3">
        {(uyeler ?? []).map((uye) => (
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
              {ROLES.map((r) => {
                const sahip = uye.roles.includes(r);
                return (
                  <button
                    key={r}
                    type="button"
                    disabled={calisan === uye.id}
                    aria-pressed={sahip}
                    data-testid={`member-${uye.email}-${r}`}
                    onClick={() => (sahip ? al(uye, r) : ver(uye, r))}
                    className={`rounded-lg border px-3 py-1 text-xs font-semibold transition disabled:cursor-not-allowed disabled:opacity-60 ${
                      sahip
                        ? "border-brand-300 bg-brand-50 text-brand-700"
                        : "border-border text-muted hover:border-brand-300 hover:text-brand-700"
                    }`}
                  >
                    {ROLE_DEFINITIONS[r].label}
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

      {toplam > 0 ? (
        <div className="mt-5 flex flex-wrap items-center justify-between gap-3">
          {/* Kaçıncı kayıtlarda olduğunu YAZIYORUZ: yalnızca "önceki/sonraki"
              göstermek, sorumlunun listenin neresinde olduğunu bilmesini
              engeller ve aradığı kişiyi bulamadığında aramayı mı yoksa
              sayfayı mı değiştireceğine karar veremez. */}
          <p data-testid="member-range" className="text-xs text-muted">
            {toplam} üyeden {ilk}–{son} arası
            {yukleniyor ? " · yükleniyor…" : ""}
          </p>
          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled={!oncekiVar || yukleniyor}
              onClick={() => setSayfa((s) => Math.max(0, s - 1))}
              data-testid="member-prev"
              className="rounded-lg border border-border px-3 py-1 text-xs font-semibold text-muted transition hover:border-brand-300 hover:text-brand-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              Önceki
            </button>
            <span data-testid="member-page" className="text-xs text-muted">
              {sayfaNo} / {sayfaAdedi}
            </span>
            <button
              type="button"
              disabled={!sonrakiVar || yukleniyor}
              onClick={() => setSayfa((s) => s + 1)}
              data-testid="member-next"
              className="rounded-lg border border-border px-3 py-1 text-xs font-semibold text-muted transition hover:border-brand-300 hover:text-brand-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              Sonraki
            </button>
          </div>
        </div>
      ) : null}
    </section>
  );
}
