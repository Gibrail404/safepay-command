// Captures README screenshots and a short screen recording from a running API (with real cases) and console. Not a test.
// Usage: node e2e/screenshots.mjs <outdir for png> <outdir for video>
import { chromium } from "@playwright/test";
const [pngDir = "../docs/figures", videoDir = "/tmp/safepay-video"] = process.argv.slice(2);
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1100, height: 760 }, colorScheme: "light", recordVideo: { dir: videoDir, size: { width: 1100, height: 760 } } });
const page = await ctx.newPage();
page.on("dialog", (d) => d.accept());
const pause = (ms) => page.waitForTimeout(ms);

await page.goto("http://localhost:3000/");
await page.getByLabel("Server address").fill("http://127.0.0.1:8000");
await page.getByLabel("API key").fill("demo-key");
await page.getByLabel(/Your name/).fill("Demo analyst");
await page.getByRole("button", { name: "Connect" }).click();
await page.getByRole("link", { name: /linked alerts/ }).first().waitFor();
await pause(1500);
await page.screenshot({ path: `${pngDir}/console-queue.png` });

await page.getByRole("link", { name: /linked alerts at time step/ }).nth(3).click();
await page.getByRole("button", { name: /Run investigation|Run again/ }).click();
await page.getByRole("button", { name: "Replay run" }).waitFor({ timeout: 60000 });
await page.getByText("Investigation summary").scrollIntoViewIfNeeded();
await pause(900);
await page.getByRole("button", { name: "Replay run" }).click();
await pause(2200);
await page.screenshot({ path: `${pngDir}/console-trace-replay.png` });
await page.getByRole("button", { name: "Replay run" }).waitFor({ timeout: 20000 });
await page.getByRole("button", { name: /^AI summary/ }).click();
await pause(1200);
await page.screenshot({ path: `${pngDir}/console-case.png` });

await page.getByRole("link", { name: "Audit trail" }).click();
await page.getByText("Try to tamper with it").scrollIntoViewIfNeeded();
await pause(1200);
await page.locator(".blk > button").nth(3).click();
await pause(600);
await page.getByRole("button", { name: /Change record/ }).click();
await pause(1800);
await page.screenshot({ path: `${pngDir}/console-tamper.png` });
await page.getByRole("button", { name: /cover their tracks/ }).click();
await page.getByText(/no longer matches the one the server saved/).waitFor({ timeout: 20000 });
await pause(1500);
await page.screenshot({ path: `${pngDir}/console-tamper-covered.png` });

await page.getByRole("link", { name: "Decision Lab" }).click();
await page.locator(".stat-value").first().filter({ hasText: "%" }).waitFor({ timeout: 30000 });
await pause(1800);
await page.getByLabel("Hold from score").focus();
for (let i = 0; i < 10; i++) { await page.keyboard.press("ArrowRight"); await pause(160); }
await pause(2200);
await page.screenshot({ path: `${pngDir}/console-lab.png`, fullPage: false });

await page.goto("http://localhost:3000/reports/graph");
await page.getByText("Graph evaluation on the real Elliptic data").waitFor();
await pause(900);
await page.screenshot({ path: `${pngDir}/console-report.png` });
await ctx.close();
await browser.close();
console.log("saved");
