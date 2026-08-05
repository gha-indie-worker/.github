#!/usr/bin/env node
import { readFile, writeFile, mkdir } from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const read = (relative) => readFile(path.join(root, relative), "utf8");
const fail = (message) => {
  throw new Error(message);
};
const requireValue = (condition, message) => {
  if (!condition) fail(message);
};

const credentialPatterns = [
  /ghp_[A-Za-z0-9]{20,}/,
  /github_pat_[A-Za-z0-9_]{20,}/,
  /-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----/,
];

const [packageRaw, config, page, readme] = await Promise.all([
  read("package.json"),
  read("astro.config.mjs"),
  read("src/pages/index.astro"),
  read("README.md"),
]);

for (const [name, text] of Object.entries({ packageRaw, config, page, readme })) {
  for (const pattern of credentialPatterns) {
    requireValue(!pattern.test(text), `${name}: credential-shaped material is forbidden`);
  }
  requireValue(!text.includes("<<<<<<< "), `${name}: unresolved conflict marker`);
  requireValue(!text.includes("=======\n"), `${name}: unresolved conflict marker`);
  requireValue(!text.includes(">>>>>>> "), `${name}: unresolved conflict marker`);
}

const packageJson = JSON.parse(packageRaw);
requireValue(packageJson.private === true, "package must remain private while staged");
requireValue(packageJson.type === "module", "package must use ESM");
requireValue(packageJson.dependencies?.astro === "5.13.2", "Astro must remain exact 5.13.2");
for (const script of ["dev", "validate", "build", "preview", "test:browser"]) {
  requireValue(typeof packageJson.scripts?.[script] === "string", `missing npm script ${script}`);
}
requireValue(Object.keys(packageJson.dependencies ?? {}).length === 1, "only Astro may be a runtime dependency");

requireValue(config.includes('site: "https://gha-indie-worker.github.io"'), "canonical Pages URL missing");
requireValue(config.includes('output: "static"'), "site must remain static output");

const requiredPageMarkers = [
  "GHA Indie Worker — own the execution",
  "Keep GitHub as the trigger.",
  "Own execution.",
  "build-server.v1",
  "No caller shell",
  "callers cannot inject command text",
  "Fixed profiles",
  "Fiducia locks",
  "Postgres + NATS",
  "data-sdk",
  "data-language",
  "data-copy",
  'id:"profile"',
  'id:"deploy"',
  'id:"curl"',
  'id:"events"',
  "https://github.com/gha-indie-worker/gha-indie-worker.rs",
];
for (const marker of requiredPageMarkers) {
  requireValue(page.includes(marker), `page is missing contract marker ${JSON.stringify(marker)}`);
}
requireValue((page.match(/<h1>/g) ?? []).length === 1, "page must contain exactly one h1");
requireValue(page.includes('name="description"'), "page must expose a meta description");
requireValue(page.includes("prefers-reduced-motion:reduce"), "reduced-motion CSS is required");
requireValue(!page.includes("eval("), "page must not use eval");
requireValue(!page.includes("innerHTML"), "page must not write HTML dynamically");
requireValue(!/<script[^>]+src=/i.test(page), "third-party script sources are forbidden");

for (const marker of [
  "https://linear.app/denman/project/githubcomgha-indie-worker-941d4102f7dc",
  "https://github.com/orgs/gha-indie-worker/projects/1",
  "https://github.com/gha-indie-worker/.github/issues/8",
  "The staging repository and artifact are evidence",
]) {
  requireValue(readme.includes(marker), `README is missing ${marker}`);
}

const report = {
  schema_version: 1,
  astro_version: packageJson.dependencies.astro,
  canonical_site: "https://gha-indie-worker.github.io",
  sample_contracts: ["build-server.v1", "build-and-deploy", "http", "nats"],
  external_script_sources: 0,
  private_staging_package: true,
  valid: true,
};

const outputIndex = process.argv.indexOf("--json-output");
if (outputIndex >= 0) {
  const output = process.argv[outputIndex + 1];
  requireValue(Boolean(output), "--json-output requires a path");
  const absolute = path.resolve(process.cwd(), output);
  await mkdir(path.dirname(absolute), { recursive: true });
  await writeFile(absolute, `${JSON.stringify(report, null, 2)}\n`);
}

console.log(`validated staged marketing site: Astro ${report.astro_version}, 4 contract examples`);
