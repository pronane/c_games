// Play along through your own amp and be marked against your tab, in a real browser against
// the real engine. Needs both services running, a song file and its tab:
//   SONG_FILE=/abs/song.wav TAB_FILE=/abs/song.gp4 BROWSER_EXECUTABLE_PATH=/path/to/chrome npm run test:play-along
// Uses Chrome's fake microphone (a steady beep) for the take, so the score itself is
// meaningless; this checks the flow: your sound, monitoring, the take, listening three ways,
// marking against the tab, and practising the weak bars.
import { chromium as pw } from "playwright-core";
if (!process.env.BROWSER_EXECUTABLE_PATH || !process.env.SONG_FILE || !process.env.TAB_FILE)
  throw Error("Set BROWSER_EXECUTABLE_PATH, SONG_FILE and TAB_FILE.");
const shots = process.env.SCREENSHOT_DIR;
(async () => {
  const browser = await pw.launch({
    args: [
      "--no-sandbox",
      "--disable-dev-shm-usage",
      "--use-fake-ui-for-media-stream",
      "--use-fake-device-for-media-stream",
      "--autoplay-policy=no-user-gesture-required",
    ],
    executablePath: process.env.BROWSER_EXECUTABLE_PATH,
    headless: true,
  });
  const page = await browser.newPage({ viewport: { width: 1280, height: 1000 } });
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  await page.goto(process.env.STUDIO_URL ?? "http://127.0.0.1:5173");
  const lab = page.getByRole("region", { name: "Break a song into its instruments" });
  await lab.locator("#song-file").setInputFiles(process.env.SONG_FILE);
  await lab.locator("#song-consent").check();
  await lab.getByRole("button", { name: /Break it down for guitar/ }).click();
  await lab.getByText("What's in this song").waitFor({ timeout: 600000 });
  await lab.getByText("Loading the separated tracks").waitFor({ state: "detached", timeout: 120000 });
  console.log("Song broken down.");

  // The player's tab, lined up with the recording.
  await lab.locator("#tab-parts-file").setInputFiles(process.env.TAB_FILE);
  await lab.locator(".tab-parts .tab-check, .tab-parts table, .tab-parts .parts").first().waitFor({ timeout: 600000 });
  console.log("Tab lined up:", (await lab.locator(".tab-parts").innerText()).replace(/\s+/g, " ").slice(400, 900));

  // Your sound: crunch with reverb, heard live.
  await lab.locator("#your-drive").selectOption("crunch");
  await lab.locator("#your-reverb").check();
  await lab.locator("#your-monitor").check();
  await lab.getByRole("button", { name: "Try the sound" }).click();
  await lab.getByRole("button", { name: "Stop listening" }).waitFor({ timeout: 15000 });
  await page.waitForTimeout(800);
  await lab.getByRole("button", { name: "Stop listening" }).click();
  console.log("Your sound:", (await lab.locator(".your-sound .helper").innerText()).replace(/\s+/g, " ").slice(0, 200));
  if (shots) await lab.locator(".your-sound").screenshot({ path: `${shots}/your-sound.png` });

  // Record a few bars along with the band, hearing yourself through the amp.
  await lab.locator("#loop-on").check();
  await lab.getByLabel("Loop from bar").fill(process.env.LOOP_FROM ?? "12");
  await lab.getByLabel("Loop to bar").fill(process.env.LOOP_TO ?? "16");
  await lab.getByRole("button", { name: "Play along & record" }).click();
  await lab.locator(".take-card").waitFor({ timeout: 120000 });
  console.log("Take:", await lab.locator(".take-card .helper").first().innerText());
  for (const name of ["Hear yourself in the band", "Just me", "The original"]) {
    await lab.getByRole("button", { name, exact: true }).click();
    await page.waitForTimeout(700);
  }
  console.log("Listened three ways.");

  // Marked against the tab.
  const options = await lab.locator("#mark-against option").allInnerTexts();
  console.log("Mark against:", options.join(" | "));
  if (!options.some((o) => o.startsWith("Your tab:"))) throw Error("No tab part offered to mark against.");
  await lab.getByRole("button", { name: "Review my take" }).click();
  await lab.locator(".take-diff, .take-card ~ .error, section .error").first().waitFor({ timeout: 300000 });
  if (!(await lab.locator(".take-diff").count())) throw Error("Review failed: " + (await lab.locator(".error").first().innerText()));
  const cards = await lab.locator(".take-diff .diff-score small").allInnerTexts();
  console.log("Scored against:", cards.join(" | "));
  if (!cards[0]?.toLowerCase().startsWith("your tab:")) throw Error("The tab is not the first score.");
  if (shots) await lab.locator(".take-card").screenshot({ path: `${shots}/marked-against-tab.png` });

  // Practise the weak bars.
  const loopButton = lab.getByRole("button", { name: "Loop the weakest bars, slower" });
  if (await loopButton.count()) {
    await loopButton.click();
    console.log(
      "Practising bars",
      await lab.getByLabel("Loop from bar").inputValue(),
      "to",
      await lab.getByLabel("Loop to bar").inputValue(),
      "at",
      await lab.locator("#speed").inputValue(),
    );
  }

  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForTimeout(400);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1);
  if (shots) await lab.screenshot({ path: `${shots}/play-along-phone.png` });
  console.log("Phone overflow:", overflow, "Errors:", errors);
  await browser.close();
  if (overflow || errors.length) process.exit(1);
})();
