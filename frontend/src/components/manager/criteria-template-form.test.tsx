import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CriteriaTemplateForm } from "./criteria-template-form";

async function fillWeight(user: ReturnType<typeof userEvent.setup>, index: number, value: string) {
  const weightInput = screen.getByLabelText(new RegExp(`Metrik ${index + 1} ağırlık`, "i"));
  await user.clear(weightInput);
  if (value) await user.type(weightInput, value);
}

describe("CriteriaTemplateForm", () => {
  it("renders the report type, and at least one metric and heading row", () => {
    render(<CriteriaTemplateForm />);

    expect(screen.getByLabelText(/rapor türü/i)).toBeInTheDocument();
    // Kategori alani KALDIRILDI: yarismanin kategorisi yarisma olusturulurken
    // BIR KEZ seciliyor; sablon formundaki ikinci secim hicbir yere
    // kaydedilmiyordu (olu alan).
    expect(screen.queryByLabelText(/^kategori$/i)).not.toBeInTheDocument();
    expect(screen.getByLabelText(/metrik 1 adı/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^zorunlu başlık 1$/i)).toBeInTheDocument();
  });

  it("shows validation errors when submitting an empty form", async () => {
    const user = userEvent.setup();
    render(<CriteriaTemplateForm />);

    await user.click(screen.getByRole("button", { name: /şablonu kaydet/i }));

    expect(
      await screen.findByText(/rapor türü en az 3 karakter olmalı/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/metrik adı en az 2 karakter olmalı/i)).toBeInTheDocument();
    expect(screen.getByText(/başlık en az 2 karakter olmalı/i)).toBeInTheDocument();
  });

  it("rejects a template name shorter than 3 characters", async () => {
    const user = userEvent.setup();
    render(<CriteriaTemplateForm />);

    await user.type(screen.getByLabelText(/rapor türü/i), "AI");
    await user.click(screen.getByRole("button", { name: /şablonu kaydet/i }));

    expect(
      await screen.findByText(/rapor türü en az 3 karakter olmalı/i),
    ).toBeInTheDocument();
  });

  it("flags metric weights that don't add up to 100%", async () => {
    const user = userEvent.setup();
    render(<CriteriaTemplateForm />);

    await user.type(screen.getByLabelText(/rapor türü/i), "Kritik Tasarım Raporu");
    await user.type(screen.getByLabelText(/metrik 1 adı/i), "Teknik uygulanabilirlik");
    await fillWeight(user, 0, "40");
    await user.type(screen.getByLabelText(/^zorunlu başlık 1$/i), "Özet");

    await user.click(screen.getByRole("button", { name: /şablonu kaydet/i }));

    expect(
      await screen.findByText(/metrik ağırlıkları toplamda %100 olmalı.*%40/i),
    ).toBeInTheDocument();
  });

  it("adds and removes metric rows, disabling remove when only one remains", async () => {
    const user = userEvent.setup();
    render(<CriteriaTemplateForm />);

    expect(screen.getByLabelText(/metrik 1 kaldır/i)).toBeDisabled();

    await user.click(screen.getByRole("button", { name: /metrik ekle/i }));
    expect(screen.getByLabelText(/metrik 2 adı/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/metrik 1 kaldır/i)).not.toBeDisabled();

    await user.click(screen.getByLabelText(/metrik 2 kaldır/i));
    expect(screen.queryByLabelText(/metrik 2 adı/i)).not.toBeInTheDocument();
    expect(screen.getByLabelText(/metrik 1 kaldır/i)).toBeDisabled();
  });

  it("submits successfully with valid data, shows a success banner, and resets the form", async () => {
    const user = userEvent.setup();
    const onSaved = jest.fn();
    render(<CriteriaTemplateForm onSaved={onSaved} />);

    await user.type(screen.getByLabelText(/rapor türü/i), "Kritik Tasarım Raporu");
    await user.type(screen.getByLabelText(/metrik 1 adı/i), "Teknik uygulanabilirlik");
    await fillWeight(user, 0, "100");
    await user.type(screen.getByLabelText(/^zorunlu başlık 1$/i), "Özet");

    await user.click(screen.getByRole("button", { name: /şablonu kaydet/i }));

    const banner = await screen.findByTestId("template-saved-banner");
    expect(within(banner).getByText(/kritik tasarım raporu/i)).toBeInTheDocument();

    expect(onSaved).toHaveBeenCalledTimes(1);
    expect(onSaved).toHaveBeenCalledWith(
      expect.objectContaining({
        reportTypeName: "Kritik Tasarım Raporu",
        metrics: [{ name: "Teknik uygulanabilirlik", weight: 100, description: "" }],
        requiredHeadings: [{ value: "Özet" }],
      }),
    );

    expect(screen.getByLabelText(/rapor türü/i)).toHaveValue("");
    expect(screen.getByLabelText(/metrik 1 adı/i)).toHaveValue("");
  });

  it("dismisses the success banner when the close button is clicked", async () => {
    const user = userEvent.setup();
    render(<CriteriaTemplateForm />);

    await user.type(screen.getByLabelText(/rapor türü/i), "Kritik Tasarım Raporu");
    await user.type(screen.getByLabelText(/metrik 1 adı/i), "Teknik uygulanabilirlik");
    await fillWeight(user, 0, "100");
    await user.type(screen.getByLabelText(/^zorunlu başlık 1$/i), "Özet");
    await user.click(screen.getByRole("button", { name: /şablonu kaydet/i }));

    const banner = await screen.findByTestId("template-saved-banner");
    await user.click(within(banner).getByRole("button", { name: /kapat/i }));

    expect(screen.queryByTestId("template-saved-banner")).not.toBeInTheDocument();
  });

  it("yarışmanın AMACI ve rapordan BEKLENTİLER gönderiliyor", async () => {
    // Şartname yöneticinin görevini "şablonu, KATEGORİ BİLGİLERİNİ ve
    // kriterleri TANIMLAR" diye yazıyor; formda yalnızca başlıklar,
    // ağırlıklar ve ad vardı. "Bu yarışma ne için var, rapordan ne
    // bekleniyor" sorusunun cevabını yazacak yer YOKTU.
    const onSaved = jest.fn();
    const user = userEvent.setup();
    render(<CriteriaTemplateForm onSaved={onSaved} />);

    await user.type(
      screen.getByLabelText(/rapor türü/i),
      "Kritik Tasarım Raporu",
    );
    await user.type(
      screen.getByTestId("template-purpose"),
      "Lise öğrencilerini havacılıkta yapay zekâya yönlendirmek.",
    );
    await user.type(
      screen.getByTestId("template-expectations"),
      "Özgün problem tanımı ve ölçülebilir sonuç.",
    );
    await user.type(screen.getByLabelText(/metrik 1 adı/i), "Özgünlük");
    await fillWeight(user, 0, "100");
    await user.type(
      screen.getByTestId("metric-description-0"),
      "Fikrin literatürdeki benzerlerinden farkı anlatılmalı.",
    );
    await user.type(screen.getByLabelText(/^zorunlu başlık 1$/i), "Özet");
    await user.click(screen.getByRole("button", { name: /şablonu kaydet/i }));

    await waitFor(() => expect(onSaved).toHaveBeenCalledTimes(1));
    expect(onSaved).toHaveBeenCalledWith(
      expect.objectContaining({
        purpose: "Lise öğrencilerini havacılıkta yapay zekâya yönlendirmek.",
        reportExpectations: "Özgün problem tanımı ve ölçülebilir sonuç.",
        metrics: [
          {
            name: "Özgünlük",
            weight: 100,
            description: "Fikrin literatürdeki benzerlerinden farkı anlatılmalı.",
          },
        ],
      }),
    );
  });

  it("amaç ve beklentiler İSTEĞE BAĞLI — boşken de kaydediliyor", () => {
    // Zorunlu yapmak, hızlıca bir yarışma kurmak isteyen yöneticiyi
    // kompozisyon yazmaya mecbur bırakırdı.
    render(<CriteriaTemplateForm onSaved={jest.fn()} />);
    expect(screen.getByTestId("template-purpose")).not.toBeRequired();
    expect(screen.getByTestId("template-expectations")).not.toBeRequired();
  });
});
