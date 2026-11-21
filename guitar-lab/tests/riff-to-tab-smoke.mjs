// Your take to tab, in a real browser against the real engine. Needs both services running
// and a short recording of solo guitar:
//   RIFF_FILE=/abs/riff.wav BROWSER_EXECUTABLE_PATH=/path/to/chrome npm run test:riff
// Records with Chrome's fake microphone (a steady beep) to check the recording flow, then
// writes the given file out as tab and checks the text tab and the downloads.
import { chromium as pw } from "playwright-core";
if (!process.env.BROWSER_EXECUTABLE_PATH || !process.env.RIFF_FILE) throw Error("Set BROWSER_EXECUTABLE_PATH and RIFF_FILE.");
const shots = process.env.SCREENSHOT_DIR;
(async () => {
  const browser = await pw.launch({
    args: ["--no-sandbox", "--disable-dev-shm-usage", "--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream", "--autoplay-policy=no-user-gesture-required"],
    executablePath: process.env.BROWSER_EXECUTABLE_PATH,
    headless: true,
  });
  const page = await browser.newPage({ viewport: { width: 1280, height: 1000 }, acceptDownloads: true });
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  await page.goto(process.env.STUDIO_URL ?? "http://127.0.0.1:5173");
  const panel = page.getByRole("region", { name: "Turn your playing into tab" });
  await panel.scrollIntoViewIfNeeded();

  // Record a couple of seconds to the click.
  await panel.locator("#riff-bpm").fill("120");
  await panel.getByRole("button", { name: "Record a riff" }).click();
  await panel.getByRole("button", { name: "Stop recording" }).waitFor({ timeout: 15000 });
  await page.waitForTimeout(4500);
  await panel.getByRole("button", { name: "Stop recording" }).click();
  await panel.locator(".riff-take").waitFor({ timeout: 15000 });
  console.log("Recorded:", await panel.locator(".riff-take .helper").first().innerText());

  // A real recording of solo guitar, written out.
  await panel.locator("#riff-file").setInputFiles(process.env.RIFF_FILE);
  await panel.getByText(/s\. The tempo and where bar 1 starts/).waitFor({ timeout: 30000 });
  await panel.locator("#riff-title").fill("Smoke riff");
  await panel.locator("#riff-consent").check();
  await panel.getByRole("button", { name: "Write it out as tab" }).click();
  await panel.locator(".riff-result, .riff-to-tab .error").first().waitFor({ timeout: 300000 });
  if (await panel.locator(".error").count()) throw Error("Failed: " + (await panel.locator(".error").innerText()));
  console.log("Grid:", (await panel.locator(".riff-grid .helper").innerText()).replace(/\s+/g, " "), "BPM", await panel.locator("#riff-grid-bpm").inputValue());
  const text = await panel.getByLabel("Text tab").innerText();
  console.log("Text tab:\n" + text.split("\n").slice(0, 6).join("\n"));
  const labels = text.split("\n").slice(0, 6).map((l) => l.split("|")[0].trim());
  if (labels.join("") !== "eBGDAE") throw Error("Text tab strings out of order: " + labels.join(" "));
  await panel.locator(".alphaTabSurface, .notation svg, .at-surface").first().waitFor({ timeout: 60000 }).catch(() => {});
  const links = await panel.locator(".downloads a").evaluateAll((as) => as.map((a) => a.getAttribute("download")));
  console.log("Downloads:", links.join(" | "));
  if (!links.includes("Smoke riff.gp") || !links.includes("Smoke riff.musicxml")) throw Error("Missing downloads.");
  const [download] = await Promise.all([page.waitForEvent("download"), panel.locator('.downloads a[download$=".gp"]').click()]);
  const size = (await (await download.createReadStream()).toArray()).reduce((a, b) => a + b.length, 0);
  console.log("Guitar Pro file:", size, "bytes");
  if (size < 500) throw Error("Guitar Pro file is empty.");

  // Halve the tempo and rewrite.
  const bpm = Number(await panel.locator("#riff-grid-bpm").inputValue());
  await panel.locator("#riff-grid-bpm").fill(String(Math.round(bpm / 2)));
  await panel.getByRole("button", { name: "Rewrite with this tempo" }).click();
  await page.waitForTimeout(3000);
  console.log("Rewritten at", Math.round(bpm / 2), "BPM:", (await panel.getByLabel("Text tab").innerText()).split("\n")[0].slice(0, 80));
  if (shots) await panel.screenshot({ path: `${shots}/riff-to-tab.png` });

  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForTimeout(400);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1);
  if (shots) await panel.screenshot({ path: `${shots}/riff-to-tab-phone.png` });
  console.log("Phone overflow:", overflow, "Errors:", errors);
  await browser.close();
  if (overflow || errors.length) process.exit(1);
})();
