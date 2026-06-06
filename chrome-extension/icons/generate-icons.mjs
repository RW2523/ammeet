/**
 * Script to generate icon PNGs from the SVG source using the Canvas API.
 * Run in Node.js: node generate-icons.mjs
 * Requires: npm install -g @resvg/resvg-js
 */
// This script is provided for reference. Icons can also be created using any
// image editor and saved as icon16.png, icon32.png, icon48.png, icon128.png
// in the icons/ directory.

import { readFileSync, writeFileSync } from "fs";

const svgContent = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">
  <rect width="128" height="128" rx="20" fill="#1e293b"/>
  <rect x="8" y="8" width="112" height="112" rx="16" fill="#0f172a"/>
  <!-- Brain/AI circuit icon -->
  <circle cx="64" cy="50" r="20" fill="none" stroke="#3b82f6" stroke-width="4"/>
  <circle cx="64" cy="50" r="8" fill="#3b82f6"/>
  <!-- Microphone -->
  <rect x="57" y="75" width="14" height="22" rx="7" fill="#22c55e"/>
  <path d="M48 88 Q48 100 64 100 Q80 100 80 88" fill="none" stroke="#22c55e" stroke-width="3" stroke-linecap="round"/>
  <line x1="64" y1="100" x2="64" y2="108" stroke="#22c55e" stroke-width="3" stroke-linecap="round"/>
  <!-- Signal waves left -->
  <path d="M36 42 Q28 50 36 58" fill="none" stroke="#60a5fa" stroke-width="3" stroke-linecap="round"/>
  <path d="M28 36 Q16 50 28 64" fill="none" stroke="#93c5fd" stroke-width="2.5" stroke-linecap="round" opacity="0.6"/>
  <!-- Signal waves right -->
  <path d="M92 42 Q100 50 92 58" fill="none" stroke="#60a5fa" stroke-width="3" stroke-linecap="round"/>
  <path d="M100 36 Q112 50 100 64" fill="none" stroke="#93c5fd" stroke-width="2.5" stroke-linecap="round" opacity="0.6"/>
</svg>`;

writeFileSync("icons/icon.svg", svgContent);
console.log("SVG written. Use a tool like Inkscape, SVGOMG, or online converters");
console.log("to export as icon16.png, icon32.png, icon48.png, icon128.png");
