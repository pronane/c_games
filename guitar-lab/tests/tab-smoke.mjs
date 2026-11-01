// Tab lesson end-to-end in a real browser against the real engine:
// upload a Guitar Pro file -> notation + tab -> tune prompt -> play -> record (fake mic) ->
// compare against the tab's exact notes -> summary. Also a pasted text tab.
//   BROWSER_EXECUTABLE_PATH=/path/to/chrome npm run test:tab
import { chromium as pw } from "playwright-core";
import { fileURLToPath } from "node:url";
const fixture = (n) => fileURLToPath(new URL(`./fixtures/${n}`, import.meta.url));
const shots = process.env.SCREENSHOT_DIR;
(async () => {
  const browser = await pw.launch({
    args: [
      "--no-sandbox",
      "--use-fake-ui-for-media-stream",
      "--use-fake-device-for-media-stream",
      "--autoplay-policy=no-user-gesture-required",
      // FAKE_AUDIO: a WAV the fake microphone plays (e.g. a rendered take); default is a beep.
      ...(process.env.FAKE_AUDIO ? [`--use-file-for-fake-audio-capture=${process.env.FAKE_AUDIO}`] : []),
    ],
    executablePath: process.env.BROWSER_EXECUTABLE_PATH,
    headless: true,
  });
  const page = await browser.newPage({ viewport: { width: 1280, height: 1000 } });
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await page.goto(process.env.STUDIO_URL ?? "http://127.0.0.1:5173");
  const proc = page.getByRole("group", { name: "Processing" });
  console.log("Processing:", (await proc.innerText()).replace(/\s+/g, " "));
  const lab = page.locator("#tab-lesson");
  await lab.locator("#tab-file").setInputFiles(process.env.TAB_FILE ?? fixture("drop-d-riff.gp"));
  await lab.locator(".notation-host svg").first().waitFor({ timeout: 60000 });
  console.log("Facts:", (await lab.locator(".song-facts").innerText()).replace(/\s+/g, " "));
  const tuning = lab.locator(".tuning-card");
  if (await tuning.count()) {
    console.log("Tuning prompt:", (await tuning.innerText()).replace(/\s+/g, " ").slice(0, 120));
    await tuning.getByRole("button", { name: /Tune to/ }).click();
    await tuning.waitFor({ state: "detached" });
    console.log("Tuned: prompt gone");
  } else console.log("Tuning: already matches the tab (no prompt)");
  if (shots) await lab.screenshot({ path: `${shots}/tab-lesson.png` });
  await lab.getByRole("button", { name: "Play the tab" }).click();
  await page.waitForTimeout(1500);
  await lab.getByRole("button", { name: "Pause" }).click();
  console.log("Played to:", await lab.locator(".transport .mono").innerText());
  await lab.locator("#tab-loop").check();
  await lab.getByLabel("Loop from bar").fill("5");
  await lab.getByLabel("Loop to bar").fill("6");
  await lab.getByRole("button", { name: /Record bars 5–6/ }).click();
  await lab.locator(".take-card").waitFor({ timeout: 60000 });
  console.log("Take:", await lab.locator(".take-card .helper").innerText());
  await lab.getByRole("button", { name: "Check my take against the tab" }).click();
  const engine = page.locator(".engine");
  await engine.locator("input[type=checkbox]").first().check();
  await engine.getByRole("button", { name: /Upload/ }).click();
  await page.locator(".take-summary").waitFor({ timeout: 180000 });
  console.log("Summary:", (await page.locator(".take-summary").innerText()).replace(/\s+/g, " ").slice(0, 200));
  const heard = page.locator(".heard-take");
  await heard.waitFor();
  await heard.getByRole("button", { name: "What the app heard" }).click();
  await heard.locator("button.on").first().waitFor();
  console.log("Playing back the take on the app's guitar:", await heard.locator("button.on").first().innerText());
  await heard.getByRole("button", { name: /Both/ }).click();
  await heard.getByRole("button", { name: "Show my take as notation and tab" }).click();
  await heard.locator(".notation-host svg").first().waitFor({ timeout: 60000 });
  console.log("Take as notation:", await heard.locator(".notation-host svg").count(), "SVG blocks;", await heard.getByText("Download my take as Guitar Pro").count() ? "Guitar Pro download offered" : "no download");
  if (shots) await heard.screenshot({ path: `${shots}/heard-take.png` });

  // Pasted text tab
  await lab.getByRole("button", { name: /Or paste a text tab/ }).click();
  const { readFileSync } = await import("node:fs");
  await lab.locator("#tab-text").fill(readFileSync(fixture("a-minor-arpeggio.txt"), "utf8"));
  await lab.getByRole("button", { name: "Use this tab" }).click();
  await lab.locator(".song-facts").getByText("Pasted tab").waitFor({ timeout: 30000 });
  await lab.locator(".notation-host svg").first().waitFor({ timeout: 60000 });
  console.log("Text tab:", (await lab.locator(".song-facts").innerText()).replace(/\s+/g, " "));
  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForTimeout(400);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1);
  if (shots) await lab.screenshot({ path: `${shots}/tab-phone.png` });
  console.log("Phone overflow:", overflow, "Errors:", errors);
  await browser.close();
  if (overflow || errors.length) process.exit(1);
})();
