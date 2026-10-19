// Builds the served widget from its readable source:
//   npm run build:widget
// frontend/widget/v1.js  ->  portal/static/widget/v1.js (minified)
// The header carries the source's sha256, which tests/speakers/test_widget.py
// checks, so CI notices a source change that was not rebuilt without Node.
import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { minify } from "terser";

const source = readFileSync("frontend/widget/v1.js", "utf8");
const digest = createHash("sha256").update(source).digest("hex");
const result = await minify(source, {
  compress: { passes: 2 },
  mangle: true,
  format: { comments: false },
});
// The MIT notice travels with every copy, and this file runs on other
// people's sites: the copyright lines come from LICENSE-MIT.
// "Copyright (c) 2025 PyLadies, 2026 Mariatta Wijaya": one notice, kept
// short since the banner counts against the widget's size budget.
const holders = readFileSync("LICENSE-MIT", "utf8")
  .split("\n")
  .filter((line) => line.startsWith("Copyright (c) "))
  .map((line) => line.slice("Copyright (c) ".length));
const banner =
  `/*! Flashlights widget v1. MIT License, Copyright (c) ` +
  `${holders.join(", ")}. Source: frontend/widget/v1.js (sha256 ${digest}). */\n`;
writeFileSync("portal/static/widget/v1.js", banner + result.code + "\n");
console.log(`portal/static/widget/v1.js: ${Buffer.byteLength(banner + result.code)} bytes`);
