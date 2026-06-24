import express from "express";
import { randomUUID } from "node:crypto";
import { BrowserBot } from "./bot.js";

const app = express();
app.use(express.json({ limit: "20mb" }));

const bots = new Map();
const PORT = process.env.PORT || 4500;

app.get("/health", (_req, res) => res.json({ status: "ok", bots: bots.size }));

// Create + deploy a bot into a meeting (mirrors the Recall.ai create-bot contract).
app.post("/bots", async (req, res) => {
  const { meeting_url, display_name, webhook_url } = req.body || {};
  if (!meeting_url) return res.status(400).json({ error: "meeting_url required" });
  const id = randomUUID();
  const bot = new BrowserBot(id, { meetingUrl: meeting_url, displayName: display_name, webhookUrl: webhook_url });
  bots.set(id, bot);
  // Fire-and-forget the join; status is polled via GET /bots/:id
  bot.start().catch((e) => {
    bot.status = "error";
    bot.lastError = String(e).slice(0, 300);
    console.error(`[bot ${id}] start failed:`, e);
  });
  res.status(201).json({ id, status: "joining", platform: bot.platform });
});

app.get("/bots/:id", (req, res) => {
  const bot = bots.get(req.params.id);
  if (!bot) return res.status(404).json({ error: "not found" });
  res.json(bot.info());
});

app.get("/bots/:id/transcript", (req, res) => {
  const bot = bots.get(req.params.id);
  if (!bot) return res.status(404).json({ error: "not found" });
  res.json({ segments: bot.transcript });
});

app.post("/bots/:id/output-audio", async (req, res) => {
  const bot = bots.get(req.params.id);
  if (!bot) return res.status(404).json({ error: "not found" });
  const { b64 } = req.body || {};
  const ok = await bot.speak(b64 ? Buffer.from(b64, "base64") : null);
  res.json({ ok });
});

app.post("/bots/:id/leave", async (req, res) => {
  const bot = bots.get(req.params.id);
  if (!bot) return res.status(404).json({ error: "not found" });
  await bot.leave();
  bots.delete(req.params.id);
  res.json({ status: "left" });
});

app.listen(PORT, () => console.log(`[bot-worker] listening on :${PORT} (AUDIO_CAPTURE=${process.env.AUDIO_CAPTURE || "off"})`));
