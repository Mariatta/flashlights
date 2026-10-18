// Copies the third-party browser libraries the pages use out of node_modules
// into portal/static/vendor/, so every page is served by the instance itself:
//   npm ci && npm run vendor
// package.json pins each version. frontend/vendored.json records the version
// and sha256 of every copied file, which tests/portal/test_vendored_assets.py
// checks, so CI notices a version bump that was not copied, without Node.
import { createHash } from "node:crypto";
import { copyFileSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { basename, dirname } from "node:path";

// package -> [folder under portal/static/vendor, files inside the package]
const LIBRARIES = {
  bootstrap: [
    "bootstrap",
    [
      "dist/css/bootstrap.min.css",
      "dist/css/bootstrap.min.css.map",
      "dist/js/bootstrap.bundle.min.js",
      "dist/js/bootstrap.bundle.min.js.map",
      "LICENSE",
    ],
  ],
  "chart.js": ["chartjs", ["dist/chart.umd.min.js", "dist/chart.umd.min.js.map", "LICENSE.md"]],
  "htmx.org": ["htmx", ["dist/htmx.min.js", "LICENSE"]],
  jquery: ["jquery", ["dist/jquery.min.js", "LICENSE.txt"]],
  select2: ["select2", ["dist/css/select2.min.css", "dist/js/select2.min.js", "LICENSE.md"]],
};

const pinned = JSON.parse(readFileSync("package.json", "utf8")).devDependencies;
const record = {};
for (const [name, [folder, files]] of Object.entries(LIBRARIES)) {
  const installed = JSON.parse(readFileSync(`node_modules/${name}/package.json`, "utf8"));
  if (installed.version !== pinned[name]) {
    throw new Error(`${name}: node_modules has ${installed.version}, package.json pins ${pinned[name]}; run npm ci`);
  }
  const target = `portal/static/vendor/${folder}`;
  rmSync(target, { recursive: true, force: true });
  const copied = {};
  for (const file of files) {
    const destination = `${target}/${basename(file)}`;
    mkdirSync(dirname(destination), { recursive: true });
    copyFileSync(`node_modules/${name}/${file}`, destination);
    copied[`vendor/${folder}/${basename(file)}`] = createHash("sha256")
      .update(readFileSync(destination))
      .digest("hex");
  }
  record[name] = { version: installed.version, files: copied };
  console.log(`${target}: ${name} ${installed.version}`);
}
writeFileSync("frontend/vendored.json", JSON.stringify(record, null, 2) + "\n");
