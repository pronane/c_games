import { chromium as pw } from "playwright-core";
if (!process.env.BROWSER_EXECUTABLE_PATH)
  throw Error("Set BROWSER_EXECUTABLE_PATH to a local Chromium executable.");
(async () => {
  const browser = await pw.launch({
    args: ["--no-sandbox", "--disable-dev-shm-usage"],
    executablePath: process.env.BROWSER_EXECUTABLE_PATH,
    headless: true,
  });
  const page = await browser.newPage({
    viewport: { width: 1440, height: 1100 },
  });
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await page.goto(process.env.STUDIO_URL ?? "http://127.0.0.1:5173");
  await page.getByRole("button", { name: "Try a sample session" }).click();
  await page
    .getByText("Polyphonic notes · Basic Pitch", { exact: false })
    .waitFor();
  const section = page.getByRole("region", {
    name: "Specialist analysis engine",
  });
  await section.getByRole("checkbox").check();
  await section
    .getByRole("button", { name: "Upload excerpts & prepare guitar" })
    .click();
  await section
    .getByText("Supplied guitar reference · quality check")
    .waitFor({ timeout: 30000 });
  console.log("Review stage reached.");
  const approval = section.getByRole("checkbox");
  await approval.check();
  await section
    .getByRole("button", { name: "Approve reference & analyse" })
    .click();
  await section
    .getByText("Editable transcription", { exact: false })
    .waitFor({ timeout: 120000 });
  const rows = await page.locator(".editable-notes tbody tr").count();
  console.log("Real pipeline notes:", rows);
  if (rows === 0) throw Error("Expected notes from real Basic Pitch");
  const first = page.locator(".editable-notes tbody tr").first();
  const pitch = first.getByRole("combobox").first();
  const initial = Number(await pitch.inputValue());
  await pitch.selectOption(String(initial + 1));
  await section
    .getByRole("button", { name: "Save & recompute differences" })
    .click();
  await section.getByText("Recomputed from your edited notes.").waitFor();

  await page.setViewportSize({ width: 390, height: 844 });

  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth > window.innerWidth,
  );
  console.log("Mobile page overflow:", overflow, "Errors:", errors);
  if (overflow || errors.length) throw Error("Browser regression");
  await section
    .getByRole("button", { name: "Delete session", exact: true })
    .click();
  await section
    .getByRole("button", { name: "Upload excerpts & prepare guitar" })
    .waitFor();
  console.log("Edit/recompute and delete passed.");
  await browser.close();
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
