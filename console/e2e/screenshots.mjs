// Captures README screenshots from a running API (with real cases) and console. Not a test. Usage: node e2e/screenshots.mjs <outdir>
import { chromium } from "@playwright/test";
const out = process.argv[2] || "../docs/figures";
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1200, height: 860 }, colorScheme: "light" });
page.on("dialog", (d) => d.accept());
await page.goto("http://localhost:3000/");
await page.getByLabel("Server address").fill("http://127.0.0.1:8000");
await page.getByLabel("API key").fill("demo-key");
await page.getByLabel(/Your name/).fill("Demo analyst");
await page.getByRole("button", { name: "Connect" }).click();
await page.getByRole("link", { name: /linked alerts/ }).first().waitFor();
await page.screenshot({ path: `${out}/console-queue.png` });

await page.getByRole("link", { name: /linked alerts at time step/ }).nth(2).click();
await page.getByRole("button", { name: /Run investigation|Run again/ }).click();
await page.locator(".cite").first().waitFor({ timeout: 60000 });
await page.getByText("Investigation summary").scrollIntoViewIfNeeded();
await page.screenshot({ path: `${out}/console-case.png`, fullPage: false });

await page.goto("http://localhost:3000/reports/graph");
await page.getByText("Graph evaluation on the real Elliptic data").waitFor();
await page.screenshot({ path: `${out}/console-report.png` });
await page.goto("http://localhost:3000/audit");
await page.getByText("Chain intact").waitFor();
await page.screenshot({ path: `${out}/console-audit.png` });
await browser.close();
console.log("saved");
