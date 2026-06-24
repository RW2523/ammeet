// Verify whether the bot's persistent profile is signed in to Google.
import { chromium } from "playwright";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const dir = process.env.BOT_PROFILE_DIR || join(here, "..", "profile");

const ctx = await chromium.launchPersistentContext(dir, {
  headless: true,
  args: ["--no-sandbox", "--disable-blink-features=AutomationControlled"],
});
const page = ctx.pages()[0] || (await ctx.newPage());
await page.goto("https://myaccount.google.com/", { waitUntil: "domcontentloaded", timeout: 30000 }).catch(() => {});
await page.waitForTimeout(3500);

const url = page.url();
const text = (await page.evaluate(() => document.body?.innerText || "").catch(() => "")).replace(/\s+/g, " ").slice(0, 160);
const signedIn = url.includes("myaccount.google.com") && !/signin|ServiceLogin/i.test(url);

console.log("FINAL_URL:", url);
console.log("SIGNED_IN:", signedIn);
console.log("SNIPPET:", text);
await ctx.close();
