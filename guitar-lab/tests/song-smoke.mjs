// Learn-a-song end-to-end check in a real browser against the real engine.
// Needs both services running and a song file:
//   SONG_FILE=/abs/path/song.mp3 BROWSER_EXECUTABLE_PATH=/path/to/chrome npm run test:song
// Uses Chrome's fake microphone (a steady tone) for the play-along recording.
import { chromium as pw } from "playwright-core";
if (!process.env.BROWSER_EXECUTABLE_PATH || !process.env.SONG_FILE)
  throw Error("Set BROWSER_EXECUTABLE_PATH and SONG_FILE.");
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
  await page.goto(process.env.STUDIO_URL ?? "http://127.0.0.1:5173");
  const lab = page.getByRole("region", { name: "Break a song into its instruments" });
  await lab.locator("#song-file").setInputFiles(process.env.SONG_FILE);
  await lab.locator("#song-consent").check();
  await lab.getByRole("button", { name: /Break it down for guitar/ }).click();
  await lab.getByText("What's in this song").waitFor({ timeout: 300000 });
  await lab.getByText("Loading the separated tracks").waitFor({ state: "detached", timeout: 60000 });
  const rows = await lab.locator(".mixer-row b").allInnerTexts();
  console.log("Mixer tracks:", rows.join(" | "));
  const facts = await lab.locator(".song-facts b").allInnerTexts();
  console.log("Key / tempo / length:", facts.join(" | "));
  const tuning = await lab.locator(".tuning-card").innerText();
  console.log("Tuning card:", tuning.split("\n").slice(0, 3).join(" / "));
  if (shots) await page.screenshot({ path: `${shots}/song-breakdown.png`, fullPage: true });

  // Tune to the suggestion, then ask for the lead passages across every guitar.
  const tuneButton = lab.locator(".tuning-card .primary");
  if (await tuneButton.isEnabled()) await tuneButton.click();
  await lab.getByText("Tuning set").waitFor();
  const targets = await page.locator(".tuning-card .helper").innerText();
  console.log("Tuner targets:", targets);
  // What I'll play: every lead passage when two guitars trade leads, else the first part.
  const options = await lab.locator("#my-part option").allInnerTexts();
  console.log("Parts I can play:", options.join(" | "));
  const everyLead = options.find((o) => o.startsWith("Every lead passage"));
  if (everyLead) await lab.locator("#my-part").selectOption({ label: everyLead });
  console.log("Tab follows the choice:", await lab.locator("#score-part").inputValue().catch(() => "single part"), "/", await lab.locator("#score-role").inputValue());
  await lab.getByRole("button", { name: "Show tab & notation" }).click();
  await lab.locator(".notation-host svg").first().waitFor({ timeout: 60000 });
  await page.waitForTimeout(1500);
  const svgs = await lab.locator(".notation-host svg").count();
  const tabText = await lab.locator(".notation-host").innerText().catch(() => "");
  console.log("Notation SVG blocks:", svgs, "· score label:", await lab.locator(".score > .helper").first().innerText());
  console.log("Notation text sample:", tabText.replace(/\s+/g, " ").slice(0, 160));
  if (shots) await lab.locator(".score").screenshot({ path: `${shots}/song-tab.png` });

  // Mixer presets and playback, then slowed down without changing pitch.
  await lab.getByRole("button", { name: "Band without it" }).click();
  await lab.getByRole("button", { name: "Play", exact: true }).click();
  await page.waitForTimeout(1200);
  const pos = await lab.locator(".transport .mono").innerText();
  await lab.getByRole("button", { name: "Pause" }).click();
  console.log("Playback advanced to:", pos);
  await lab.locator("#speed").selectOption("0.75");
  await lab.getByRole("button", { name: "Play", exact: true }).click();
  await lab.getByRole("button", { name: "Pause" }).waitFor({ timeout: 30000 });
  await page.waitForTimeout(2000);
  const slow = await lab.locator(".transport .mono").innerText();
  await lab.getByRole("button", { name: "Pause" }).click();
  console.log("At 75% speed, position after 2 s:", slow);

  // Click track on, then the one-time delay check. Chrome's fake microphone only beeps on
  // its own schedule, so the check must refuse to trust the result rather than save it.
  await lab.locator("#click-on").check();
  await lab.getByRole("button", { name: "Play", exact: true }).click();
  await lab.getByRole("button", { name: "Pause" }).waitFor({ timeout: 30000 });
  await lab.getByRole("button", { name: "Pause" }).click();
  await lab.locator("#click-on").uncheck();
  await lab.getByRole("button", { name: "Measure with speakers" }).click();
  await lab.getByRole("button", { name: "Measure with speakers" }).waitFor({ timeout: 30000 });
  console.log("Delay check:", await lab.locator(".latency").innerText().then((t) => t.replace(/\s+/g, " ").slice(0, 220)));

  if (process.env.EARLIER_TAKE) {
    await lab.locator("#earlier-take").setInputFiles(process.env.EARLIER_TAKE);
    await lab.locator(".located").waitFor({ timeout: 120000 });
    console.log("Earlier recording placed:", (await lab.locator(".located").innerText()).replace(/\s+/g, " "));
    console.log("Take:", await lab.locator(".take-card .helper").first().innerText());
  }

  // Loop bars 3-4 and play along with the fake microphone.
  await lab.locator("#loop-on").check();
  await lab.getByLabel("Loop from bar").fill(process.env.LOOP_FROM ?? "3");
  await lab.getByLabel("Loop to bar").fill(process.env.LOOP_TO ?? "4");
  await lab.getByRole("button", { name: "Play along & record" }).click();
  await lab.locator(".take-card").waitFor({ timeout: 60000 });
  console.log("Take:", await lab.locator(".take-card .helper").innerText());
  await lab.getByRole("button", { name: "Hear yourself in the band" }).click();
  await page.waitForTimeout(800);
  await lab.getByRole("button", { name: "Make a mix to keep" }).click();
  await lab.getByText("Download your version (WAV)").waitFor();
  await lab.getByRole("button", { name: "Compare with the original part" }).click();
  await page.getByText("Play-along take", { exact: false }).first().waitFor();
  console.log("Take handed to the comparison studio.");
  if (process.env.RUN_ENGINE_COMPARE) {
    // Specialist engine: consent, review the reference, approve, read the summary.
    const engine = page.locator(".engine");
    await engine.locator("input[type=checkbox]").first().check();
    await engine.getByRole("button", { name: /Upload|Start|Send/ }).first().click();
    await engine.getByText("I listened to this reference").waitFor({ timeout: 120000 });
    await engine.getByText("I listened to this reference").click();
    await engine.getByRole("button", { name: /Approve/ }).click();
    await page.locator(".take-summary").waitFor({ timeout: 180000 });
    console.log("Summary:", (await page.locator(".take-summary").innerText()).replace(/\s+/g, " ").slice(0, 400));
    if (shots) await page.locator(".take-summary").screenshot({ path: `${shots}/take-summary.png` });
  }

  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForTimeout(400);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1);
  if (shots) await lab.screenshot({ path: `${shots}/song-phone.png` });
  console.log("Phone overflow:", overflow, "Errors:", errors);
  await browser.close();
  if (overflow || errors.length) process.exit(1);
})();
