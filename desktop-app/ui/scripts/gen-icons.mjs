#!/usr/bin/env node
// Placeholder icon generator — draws a rounded blue square with "AM" and
// writes PNGs into ../src-tauri/icons/. Zero dependencies (node's zlib only,
// no remote assets). Full platform sets (.icns/.ico) are produced later by
// `cargo tauri icon icons/icon.png` — see ../../README.md.
//
// Usage: node scripts/gen-icons.mjs

import zlib from "node:zlib";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const OUT_DIR = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../../src-tauri/icons",
);

// ── minimal PNG encoder (RGBA8, no interlace) ────────────────────────────────
const CRC_TABLE = (() => {
  const t = new Int32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    t[n] = c;
  }
  return t;
})();

function crc32(buf) {
  let c = 0xffffffff;
  for (let i = 0; i < buf.length; i++) c = CRC_TABLE[(c ^ buf[i]) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

function chunk(type, data) {
  const len = Buffer.alloc(4);
  len.writeUInt32BE(data.length);
  const body = Buffer.concat([Buffer.from(type, "ascii"), data]);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(body));
  return Buffer.concat([len, body, crc]);
}

function encodePNG(size, rgba) {
  const stride = size * 4;
  const raw = Buffer.alloc((stride + 1) * size);
  for (let y = 0; y < size; y++) {
    raw[y * (stride + 1)] = 0; // filter: None
    rgba.copy(raw, y * (stride + 1) + 1, y * stride, (y + 1) * stride);
  }
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(size, 0);
  ihdr.writeUInt32BE(size, 4);
  ihdr[8] = 8; // bit depth
  ihdr[9] = 6; // color type RGBA
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk("IHDR", ihdr),
    chunk("IDAT", zlib.deflateSync(raw, { level: 9 })),
    chunk("IEND", Buffer.alloc(0)),
  ]);
}

// ── drawing ──────────────────────────────────────────────────────────────────
// 5x7 bitmap glyphs.
const GLYPHS = {
  A: ["01110", "10001", "10001", "11111", "10001", "10001", "10001"],
  M: ["10001", "11011", "10101", "10101", "10001", "10001", "10001"],
};

function drawIcon(size) {
  const rgba = Buffer.alloc(size * size * 4); // starts fully transparent
  const margin = Math.round(size * 0.06);
  const rMin = margin;
  const rMax = size - margin - 1;
  const radius = Math.max(2, Math.round(size * 0.2));
  const bg = [0x25, 0x63, 0xeb]; // blue-600, the product accent

  const insideRounded = (x, y) => {
    if (x < rMin || x > rMax || y < rMin || y > rMax) return false;
    const cx = x < rMin + radius ? rMin + radius : x > rMax - radius ? rMax - radius : x;
    const cy = y < rMin + radius ? rMin + radius : y > rMax - radius ? rMax - radius : y;
    const dx = x - cx;
    const dy = y - cy;
    return dx * dx + dy * dy <= radius * radius;
  };

  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      if (!insideRounded(x, y)) continue;
      const i = (y * size + x) * 4;
      // subtle vertical shade so it doesn't look dead flat
      const shade = 1 - 0.15 * (y / size);
      rgba[i] = Math.round(bg[0] * shade);
      rgba[i + 1] = Math.round(bg[1] * shade);
      rgba[i + 2] = Math.round(bg[2] * shade);
      rgba[i + 3] = 255;
    }
  }

  // "AM" centered, white
  const text = ["A", "M"];
  const cols = text.length * 5 + (text.length - 1); // 1-col gap
  const scale = Math.max(1, Math.floor(size / 20));
  const tw = cols * scale;
  const th = 7 * scale;
  const ox = Math.floor((size - tw) / 2);
  const oy = Math.floor((size - th) / 2);
  text.forEach((ch, gi) => {
    const rows = GLYPHS[ch];
    const gx = ox + gi * 6 * scale;
    for (let ry = 0; ry < 7; ry++) {
      for (let rx = 0; rx < 5; rx++) {
        if (rows[ry][rx] !== "1") continue;
        for (let sy = 0; sy < scale; sy++) {
          for (let sx = 0; sx < scale; sx++) {
            const px = gx + rx * scale + sx;
            const py = oy + ry * scale + sy;
            if (px < 0 || px >= size || py < 0 || py >= size) continue;
            const i = (py * size + px) * 4;
            rgba[i] = 255;
            rgba[i + 1] = 255;
            rgba[i + 2] = 255;
            rgba[i + 3] = 255;
          }
        }
      }
    }
  });

  return encodePNG(size, rgba);
}

fs.mkdirSync(OUT_DIR, { recursive: true });
const outputs = [
  ["32x32.png", 32],
  ["128x128.png", 128],
  ["128x128@2x.png", 256],
  ["icon.png", 512],
];
for (const [name, size] of outputs) {
  const file = path.join(OUT_DIR, name);
  fs.writeFileSync(file, drawIcon(size));
  console.log(`wrote ${file} (${size}x${size})`);
}
