// Proof-of-concept: can a headless browser actually JOIN a live Jitsi meeting?
import { chromium } from "playwright";

const host = process.env.JITSI_HOST || "meet.jit.si";
const room = process.argv[2] || `ammeet-bot-test-${Date.now()}`;
const headless = process.env.HEADLESS !== "false";

// Skip the pre-join screen and join muted (a listening bot doesn't broadcast).
const cfg = [
  "config.prejoinPageEnabled=false",
  "config.prejoinConfig.enabled=false",
  "config.startWithAudioMuted=true",
  "config.startWithVideoMuted=true",
  "config.disableInitialGUM=false",
  'userInfo.displayName="AmMeeting Assistant"',
].join("&");
const url = `https://${host}/${room}#${cfg}`;

console.log(`[probe] joining ${host} room "${room}" (headless=${headless})`);

const browser = await chromium.launch({
  headless,
  args: [
    "--use-fake-ui-for-media-stream",
    "--use-fake-device-for-media-stream",
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox",
    "--autoplay-policy=no-user-gesture-required",
  ],
});
const context = await browser.newContext({ permissions: ["camera", "microphone"] });
const page = await context.newPage();

let joined = false;
try {
  await page.goto(url, { waitUntil: "domcontentloaded", timeout: 45000 });

  // With prejoin disabled, Jitsi joins directly. The authoritative signal is the
  // internal conference API reporting we've joined the room.
  for (let i = 0; i < 40 && !joined; i++) {
    joined = await page
      .evaluate(() => {
        const c = window.APP && window.APP.conference;
        // isJoined() across Jitsi versions; fall back to having a local id / participants
        if (!c) return false;
        try {
          if (typeof c.isJoined === "function") return !!c.isJoined();
          if (c._room && typeof c._room.isJoined === "function") return !!c._room.isJoined();
          if (typeof c.membersCount === "number") return true;
        } catch {
          return false;
        }
        return false;
      })
      .catch(() => false);
    if (!joined) await page.waitForTimeout(1000);
  }

  // Secondary visual confirmation: the in-call conference timer / large video exist.
  const timer = await page.$('[class*="conference-timer"], #largeVideoContainer');
  await page.screenshot({ path: "recordings/jitsi-join.png" });
  const title = await page.title();
  console.log(`[probe] title="${title}"`);
  console.log(`[probe] conference API joined: ${joined}; in-call UI present: ${!!timer}`);

  if (joined) {
    // Read live participant count to prove we're really in the room.
    const count = await page
      .evaluate(() => {
        try { return window.APP.conference.membersCount; } catch { return null; }
      })
      .catch(() => null);
    console.log(`[probe] participants in room (incl. bot): ${count}`);
  } else {
    const txt = (await page.locator("body").innerText().catch(() => "")).slice(0, 160).replace(/\n/g, " ");
    console.log(`[probe] not joined; visible: ${txt}`);
  }

  await page.waitForTimeout(3000);
} catch (e) {
  console.log("[probe] ERROR:", String(e).slice(0, 200));
} finally {
  await browser.close();
  console.log(joined ? "[probe] RESULT: JOINED ✅" : "[probe] RESULT: did not confirm join ❌");
  process.exit(joined ? 0 : 1);
}
