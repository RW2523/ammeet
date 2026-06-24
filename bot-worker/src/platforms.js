// Per-platform "join the meeting" adapters for the headless browser bot.
// Jitsi is fully working and credential-free; Google Meet / Teams / Zoom join flows
// are implemented but need a signed-in bot account + a live meeting to validate.

export function detectPlatform(url) {
  const u = url.toLowerCase();
  if (u.includes("meet.google.com")) return "google_meet";
  if (u.includes("teams.microsoft") || u.includes("teams.live")) return "teams";
  if (u.includes("zoom.us")) return "zoom";
  // jitsi.* / meet.jit.si / meet.ffmuc.net / self-hosted
  return "jitsi";
}

// ── Jitsi (proven, no credentials) ──────────────────────────────────────────
async function joinJitsi(page, url, { displayName }) {
  // Skip the pre-join gate and join muted (a bot doesn't broadcast).
  const cfg = [
    "config.prejoinPageEnabled=false",
    "config.prejoinConfig.enabled=false",
    "config.startWithAudioMuted=true",
    "config.startWithVideoMuted=true",
    `userInfo.displayName=${JSON.stringify(displayName)}`,
  ].join("&");
  const full = url.includes("#") ? url : `${url}#${cfg}`;
  await page.goto(full, { waitUntil: "domcontentloaded", timeout: 45000 });

  for (let i = 0; i < 45; i++) {
    const joined = await page
      .evaluate(() => {
        const c = window.APP && window.APP.conference;
        if (!c) return false;
        try {
          if (typeof c.isJoined === "function") return !!c.isJoined();
          if (c._room && typeof c._room.isJoined === "function") return !!c._room.isJoined();
          return typeof c.membersCount === "number";
        } catch {
          return false;
        }
      })
      .catch(() => false);
    if (joined) return true;
    await page.waitForTimeout(1000);
  }
  return false;
}

// ── Google Meet (needs a signed-in bot Google account to be admitted) ───────
async function joinGoogleMeet(page, url, { displayName }) {
  await page.goto(url, { waitUntil: "domcontentloaded", timeout: 45000 });
  await page.waitForTimeout(4000);

  const pageText = async () =>
    (await page.evaluate(() => document.body?.innerText || "").catch(() => "")) || "";

  // Google flat-out denies an un-signed-in / uninvited client — fail fast with a reason
  // instead of blocking in a dead lobby for the full timeout.
  const isDenied = (t) =>
    /can't join this video call|you can't join|return to home screen|not allowed to join|check your meeting code/i.test(t);
  if (isDenied(await pageText())) {
    throw new Error("Google denied entry — the bot isn't signed in or isn't invited to this meeting.");
  }

  // Dismiss permission / informational dialogs that can cover the Join button.
  for (const label of ["Got it", "Dismiss", "Continue without microphone and camera"]) {
    const b = await page.$(`button:has-text("${label}")`);
    if (b) await b.click().catch(() => {});
  }
  // Join muted + camera off (the bot is a silent recorder).
  for (const label of ["Turn off microphone", "Turn off camera"]) {
    const b = await page.$(`[aria-label="${label}"]`);
    if (b) await b.click().catch(() => {});
  }
  // Guest name field only appears when NOT signed in (and the host allows guests).
  const nameField = await page.$('input[aria-label*="your name" i], input[placeholder*="name" i]');
  if (nameField) await nameField.fill(displayName).catch(() => {});

  // Click the join CTA. Signed-in + invited → "Join now"; otherwise → "Ask to join".
  for (const label of ["Join now", "Ask to join", "Join", "Ask to Join"]) {
    const btn = await page.$(`button:has-text("${label}"), [aria-label="${label}"]`);
    if (btn) { await btn.click().catch(() => {}); break; }
  }

  // Resolve to one of: in-call (Leave button), denied, or lobby-timeout. Allow up to
  // ~120s because the host has to click "Admit" (default-deny for bots since 2026).
  for (let i = 0; i < 120; i++) {
    if (await page.$('button[aria-label*="Leave call" i], [aria-label*="Leave call" i]')) return true;
    const t = await pageText();
    if (isDenied(t)) {
      throw new Error("Google denied entry after the request — host declined or bot not permitted.");
    }
    await page.waitForTimeout(1000);
  }
  return false; // still in the lobby — the host never admitted the bot
}

// ── Microsoft Teams (web; needs a signed-in account for most tenants) ───────
async function joinTeams(page, url, { displayName }) {
  await page.goto(url, { waitUntil: "domcontentloaded", timeout: 45000 });
  await page.waitForTimeout(4000);
  // Choose "Continue on this browser" if offered
  const cont = await page.$('button:has-text("Continue on this browser"), a:has-text("Join on the web instead")');
  if (cont) await cont.click().catch(() => {});
  await page.waitForTimeout(3000);
  const nameField = await page.$('input[placeholder*="name" i]');
  if (nameField) await nameField.fill(displayName).catch(() => {});
  for (const label of ["Join now", "Join", "Continue"]) {
    const btn = await page.$(`button:has-text("${label}"), [aria-label="${label}"]`);
    if (btn) { await btn.click().catch(() => {}); break; }
  }
  for (let i = 0; i < 60; i++) {
    if (await page.$('[aria-label*="Leave" i], #hangup-button')) return true;
    await page.waitForTimeout(1000);
  }
  return false;
}

// ── Zoom (web client) ───────────────────────────────────────────────────────
async function joinZoom(page, url, { displayName }) {
  await page.goto(url, { waitUntil: "domcontentloaded", timeout: 45000 });
  await page.waitForTimeout(3000);
  const nameField = await page.$('#inputname, input[placeholder*="name" i]');
  if (nameField) await nameField.fill(displayName).catch(() => {});
  for (const label of ["Join", "Join Audio by Computer"]) {
    const btn = await page.$(`button:has-text("${label}"), #joinBtn`);
    if (btn) { await btn.click().catch(() => {}); break; }
  }
  for (let i = 0; i < 60; i++) {
    if (await page.$('[aria-label*="Leave" i], .footer__leave-btn')) return true;
    await page.waitForTimeout(1000);
  }
  return false;
}

export const JOINERS = {
  jitsi: joinJitsi,
  google_meet: joinGoogleMeet,
  teams: joinTeams,
  zoom: joinZoom,
};
