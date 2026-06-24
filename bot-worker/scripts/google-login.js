// One-time manual Google login for the bot.
//
// Google blocks AUTOMATED logins, but a human can log in once into a persistent
// browser profile, and the bot then reuses that signed-in session to join Google
// Meet. Run:  BOT_PROFILE_DIR=./profile node scripts/google-login.js
// A real Chrome window opens — log the bot's (throwaway) Google account in by hand,
// then press Ctrl+C. The profile is saved; start the worker with the same
// BOT_PROFILE_DIR and it joins Meet already signed in.

import { chromium } from "playwright";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const dir = process.env.BOT_PROFILE_DIR || join(here, "..", "profile");

console.log(`[google-login] persistent profile dir: ${dir}`);
const ctx = await chromium.launchPersistentContext(dir, {
  headless: false,
  viewport: { width: 1100, height: 820 },
  args: ["--no-sandbox", "--disable-blink-features=AutomationControlled"],
});
const page = ctx.pages()[0] || (await ctx.newPage());
await page.goto("https://accounts.google.com/");

console.log("\n  → A Chrome window opened. Log in to the bot's Google account there.");
console.log("  → Solve any 2FA / 'verify it's you' prompts yourself.");
console.log("  → When you're signed in (you can also open https://meet.google.com to confirm),");
console.log("    come back here and press Ctrl+C. The login is saved to the profile.\n");

process.on("SIGINT", async () => {
  try { await ctx.close(); } catch {}
  console.log("\n[google-login] saved. Start the worker with BOT_PROFILE_DIR=" + dir);
  process.exit(0);
});

await new Promise(() => {}); // keep the window open until Ctrl+C
