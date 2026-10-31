import { chromium } from "playwright-core";
import assert from "node:assert/strict";
if (!process.env.BROWSER_EXECUTABLE_PATH)
  throw Error("Set BROWSER_EXECUTABLE_PATH");
const browser = await chromium.launch({
  executablePath: process.env.BROWSER_EXECUTABLE_PATH,
  headless: true,
  args: ["--no-sandbox", "--disable-dev-shm-usage"],
});
try {
  const page = await browser.newPage({
      viewport: { width: 1440, height: 1000 },
    }),
    errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await page.goto(process.env.STUDIO_URL ?? "http://127.0.0.1:5173");
  await page
    .getByLabel("Instrument tuning", { exact: true })
    .selectOption("drop_d");
  await page.getByLabel("Capo fret", { exact: true }).selectOption("2");
  assert.ok(
    (await page.locator(".instrument-setup").textContent()).includes("E2"),
  );
  await page
    .getByLabel("Instrument profile", { exact: true })
    .selectOption("bass");
  assert.equal(await page.getByLabel("Capo fret", { exact: true }).count(), 0);
  await page
    .getByLabel("Instrument tuning", { exact: true })
    .selectOption("drop_d");
  assert.ok(
    (await page.locator(".instrument-setup").textContent()).includes("D1"),
  );
  // The sample remains a clearly synthetic exercise; it is not a piano quality test.
  await page.getByRole("button", { name: "Try a sample session" }).click();
  await page
    .getByLabel("Instrument profile", { exact: true })
    .selectOption("piano");
  assert.equal(
    await page.getByLabel("Instrument tuning", { exact: true }).count(),
    0,
  );
  assert.equal(
    await page.getByLabel("Preferred notation").inputValue(),
    "notes",
  );
  assert.equal(await page.getByText(/Take ready:/).count(), 0);
  await page.evaluate(async () => {
    const { encodeWav } = await import("/src/engineApi.ts");
    const rate = 44100,
      samples = Float32Array.from(
        { length: rate * 2 },
        (_, i) => 0.3 * Math.sin((2 * Math.PI * 220 * i) / rate),
      );
    const dt = new DataTransfer();
    dt.items.add(
      new File([encodeWav([samples], rate)], "piano-profile-synthetic.wav", {
        type: "audio/wav",
      }),
    );
    const input = document.querySelector(".upload-take input");
    input.files = dt.files;
    input.dispatchEvent(new Event("change", { bubbles: true }));
  });
  await page.getByText(/Take ready: piano-profile-synthetic.wav/).waitFor();
  const section = page.getByRole("region", {
    name: "Specialist analysis engine",
  });
  await section.getByRole("checkbox").check();
  const [created] = await Promise.all([
    page.waitForResponse(
      (r) => r.url().endsWith("/api/jobs") && r.request().method() === "POST",
    ),
    section
      .getByRole("button", { name: "Upload excerpts & prepare piano" })
      .click(),
  ]);
  const job = await created.json();
  assert.equal(job.instrument_profile.id, "piano");
  assert.equal(job.instrument_profile.midi_min, 21);
  assert.equal(job.instrument_profile.midi_max, 108);
  await section
    .getByText("Supplied piano reference · quality check")
    .waitFor({ timeout: 30000 });
  await section.getByRole("checkbox").check();
  await section
    .getByRole("button", { name: "Approve reference & analyse" })
    .click();
  await section
    .getByText("Editable transcription", { exact: false })
    .waitFor({ timeout: 120000 });
  assert.equal(
    (await section.locator(".editable-notes tbody tr").count()) > 0,
    true,
  );
  const pitch = section
    .locator(".editable-notes tbody tr")
    .first()
    .getByRole("combobox")
    .first();
  assert.equal(
    await pitch.locator("option").first().getAttribute("value"),
    "21",
  );
  assert.equal(
    await pitch.locator("option").last().getAttribute("value"),
    "108",
  );
  assert.equal(await section.locator(".tab-scroll").isVisible(), false);
  await pitch.selectOption("21");
  await section
    .getByRole("button", { name: "Save & recompute differences" })
    .click();
  await section.getByText("Recomputed from your edited notes.").waitFor();
  await page.setViewportSize({ width: 390, height: 844 });
  assert.equal(
    await page.evaluate(
      () => document.documentElement.scrollWidth > window.innerWidth,
    ),
    false,
  );
  await section
    .getByRole("button", { name: "Delete session", exact: true })
    .click();
  assert.deepEqual(errors, []);
  console.log(
    "Profiles: drop-D/capo, bass range, piano note-only display, profile upload/provenance, real ONNX pipeline and A0 edit passed on synthetic audio.",
  );
} finally {
  await browser.close();
}
