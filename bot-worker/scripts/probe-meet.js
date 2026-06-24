// Attempt to join a REAL Google Meet and report exactly where we land.
import { chromium } from "playwright";

const url = process.argv[2];
if (!url) { console.log("usage: node scripts/probe-meet.js <meet-url>"); process.exit(2); }
const headless = process.env.HEADLESS !== "false";

console.log(`[meet] joining ${url} (headless=${headless})`);

const browser = await chromium.launch({
  headless,
  args: [
    "--use-fake-ui-for-media-stream",
    "--use-fake-device-for-media-stream",
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox",
    "--lang=en-US",
  ],
});
const context = await browser.newContext({
  permissions: ["camera", "microphone"],
  locale: "en-US",
  userAgent:
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
});
const page = await context.newPage();

async function snap(tag) {
  await page.screenshot({ path: `recordings/meet-${tag}.png` }).catch(() => {});
  const text = (await page.locator("body").innerText().catch(() => "")).replace(/\s+/g, " ").slice(0, 280);
  console.log(`[meet] (${tag}) text: ${text}`);
}
async function buttons() {
  return page.$$eval("button,[role=button]", (els) =>
    els.map((e) => (e.innerText || e.getAttribute("aria-label") || "").trim()).filter(Boolean).slice(0, 20)
  ).catch(() => []);
}

let joined = false;
try {
  await page.goto(url, { waitUntil: "domcontentloaded", timeout: 45000 });
  await page.waitForTimeout(4000);
  await snap("01-landing");
  console.log("[meet] buttons:", JSON.stringify(await buttons()));

  // Dismiss cookie / "Got it" dialogs
  for (const label of ["Accept all", "I agree", "Got it", "Dismiss", "No thanks"]) {
    const b = await page.$(`button:has-text("${label}")`);
    if (b) { await b.click().catch(() => {}); await page.waitForTimeout(1000); console.log(`[meet] dismissed "${label}"`); }
  }

  // Guest name field (only if guest join is allowed)
  const nameField = await page.$('input[aria-label*="name" i], input[placeholder*="name" i], input[type="text"]');
  if (nameField) { await nameField.fill("AmMeeting Assistant").catch(() => {}); console.log("[meet] entered guest name"); }
  else console.log("[meet] no guest-name field (likely sign-in required)");

  await page.waitForTimeout(1500);
  await snap("02-prejoin");
  console.log("[meet] buttons:", JSON.stringify(await buttons()));

  // Click Ask to join / Join now
  let clicked = null;
  for (const label of ["Ask to join", "Join now", "Join", "Switch here"]) {
    const b = await page.$(`button:has-text("${label}"), [aria-label="${label}"]`);
    if (b) { await b.click().catch(() => {}); clicked = label; break; }
  }
  console.log(`[meet] clicked: ${clicked || "(no join button found)"}`);

  // Wait to see if we get admitted (in-call) or sit in the lobby / get blocked
  for (let i = 0; i < 40; i++) {
    if (await page.$('[aria-label*="Leave call" i]')) { joined = true; break; }
    await page.waitForTimeout(1500);
  }
  await snap("03-final");
  console.log("[meet] buttons:", JSON.stringify(await buttons()));
  console.log(`[meet] in-call (Leave button present): ${joined}`);
} catch (e) {
  console.log("[meet] ERROR:", String(e).slice(0, 240));
} finally {
  await browser.close();
  console.log(joined ? "[meet] RESULT: JOINED ✅" : "[meet] RESULT: NOT in-call (see screenshots/text above)");
  process.exit(joined ? 0 : 1);
}
