import { expect, test } from "@playwright/test";

test("renders the bounded continuity product contract without browser errors", async ({ page }) => {
  const consoleErrors = [];
  const pageErrors = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("pageerror", (error) => pageErrors.push(error.message));

  await page.goto("/");
  await expect(page).toHaveTitle("GHA Indie Worker — own the execution");
  await expect(page.getByRole("heading", { level: 1 })).toContainText(
    "Keep GitHub as the trigger.",
  );
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Own execution.");
  await expect(page.getByText("No caller shell", { exact: true })).toBeVisible();
  await expect(page.getByText("build-server.v1", { exact: true }).first()).toBeVisible();
  await expect(page.locator("h1")).toHaveCount(1);
  await expect(page.locator('meta[name="description"]')).toHaveCount(1);
  await expect(page.locator('script[src]')).toHaveCount(0);

  expect(consoleErrors).toEqual([]);
  expect(pageErrors).toEqual([]);
});

test("switches all four real contract examples deterministically", async ({ page }) => {
  await page.goto("/#clients");
  const selector = page.getByLabel("Select client language");
  await expect(selector.locator("option")).toHaveCount(4);
  await expect(page.locator("[data-file]")).toHaveText("profile.json");
  await expect(page.locator("[data-sample=profile]")).toContainText(
    '"profile": "flutter-android-debug"',
  );

  await selector.selectOption("deploy");
  await expect(page.locator("[data-file]")).toHaveText("deploy.json");
  await expect(page.locator("[data-sample=deploy]")).toContainText(
    '"jobKind": "build-and-deploy"',
  );
  await expect(page.locator("[data-sample=profile]")).toBeHidden();

  await selector.selectOption("curl");
  await expect(page.locator("[data-file]")).toHaveText("submit.sh");
  await expect(page.locator("[data-sample=curl]")).toContainText(
    "authorization: Bearer $BUILD_SERVER_TOKEN",
  );

  await selector.selectOption("events");
  await expect(page.locator("[data-file]")).toHaveText("subjects.txt");
  await expect(page.locator("[data-sample=events]")).toContainText(
    "dd.remote.build_server.results",
  );
});

test("copies only the visible contract when the Clipboard API succeeds", async ({ page }) => {
  await page.addInitScript(() => {
    let copied = "";
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: {
        writeText: async (value) => {
          copied = value;
        },
        readText: async () => copied,
      },
    });
  });
  await page.goto("/#clients");
  const selector = page.getByLabel("Select client language");
  await selector.selectOption("events");

  const copy = page.getByRole("button", { name: "Copy" });
  await copy.click();
  await expect(copy).toHaveText("Copied");
  const clipboard = await page.evaluate(() => navigator.clipboard.readText());
  expect(clipboard).toContain("dd.remote.build_server.requests");
  expect(clipboard).toContain("dd.remote.build_server.results");
  expect(clipboard).not.toContain('"profile": "flutter-android-debug"');
});

test("falls back to focusing the visible code when clipboard access is denied", async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: {
        writeText: async () => {
          throw new Error("clipboard denied for deterministic fallback test");
        },
      },
    });
  });
  await page.goto("/#clients");
  await page.getByLabel("Select client language").selectOption("curl");

  const copy = page.getByRole("button", { name: "Copy" });
  await copy.click();
  await expect(copy).toHaveText("Select code");
  await expect(page.locator("[data-sample=curl] pre")).toBeFocused();
  await expect(page.locator("[data-sample=profile]")).toBeHidden();
});

test("preserves canonical organization and source links", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator('a[href="https://github.com/gha-indie-worker"]')).toHaveCount(2);
  await expect(
    page.locator('a[href="https://github.com/gha-indie-worker/gha-indie-worker.rs"]'),
  ).toHaveCount(3);
  await expect(page.locator('a[href^="http://"]')).toHaveCount(0);
});

test("remains usable under reduced-motion preference and a narrow viewport", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(page.getByLabel("Select client language")).toBeVisible();
  await expect(page.getByRole("button", { name: "Copy" })).toBeVisible();
  const horizontalOverflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(horizontalOverflow).toBeLessThanOrEqual(1);
});
