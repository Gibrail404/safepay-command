// Captures README screenshots and a short screen recording from a running API (with real cases, real model, live AI) and console. Not a test.
// Usage: node e2e/screenshots.mjs <outdir for png> <outdir for video>
import { chromium } from "@playwright/test";
const [pngDir = "../docs/figures", videoDir = "/tmp/safepay-video"] = process.argv.slice(2);
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1100, height: 760 }, colorScheme: "light", recordVideo: { dir: videoDir, size: { width: 1100, height: 760 } } });
const page = await ctx.newPage();
page.on("dialog", (d) => d.accept());
const pause = (ms) => page.waitForTimeout(ms);
const nav = (name) => page.getByRole("navigation", { name: "Main" }).getByRole("link", { name, exact: true });

await page.goto("http://localhost:3000/");
await page.getByLabel("Email").fill(process.env.DEMO_EMAIL ?? "demo@example.com");
await page.getByLabel("Password").fill(process.env.DEMO_PASSWORD ?? "");
await page.getByRole("button", { name: "Sign in", exact: true }).click();
await page.getByRole("heading", { name: "Overview" }).waitFor();

// 1. interception, played by typing, scam victim answering honestly
await nav("Interception").click();
await page.getByRole("radio", { name: /Scam victim who answers honestly/ }).click();
await pause(500);
await page.getByRole("button", { name: "Start this payment" }).click();
const answers = ["A man from my bank phoned and told me to move my savings to a safe account today.", "No, I have never met him. He only called me.", "Yes, he said it is urgent and I must not tell anyone."];
for (let i = 0; i < answers.length; i++) {
  await page.getByLabel("Your answer").waitFor({ timeout: 60000 });
  await page.getByLabel("Your answer").pressSequentially(answers[i], { delay: 12 });
  await pause(300);
  await page.getByRole("button", { name: "Send" }).click();
  await page.waitForTimeout(400);
}
await page.getByText("What this scenario really was").waitFor({ timeout: 90000 });
await page.getByRole("heading", { name: "Decision", exact: true }).scrollIntoViewIfNeeded();
await pause(1800);
await page.screenshot({ path: `${pngDir}/console-interception.png` });

// 2. a case: network, run replay, override
await nav("Cases").click();
await page.getByRole("link", { name: /linked alerts at time step/ }).nth(2).click();
await page.getByRole("heading", { name: "How these alerts are linked" }).waitFor();
await pause(1500);
await page.screenshot({ path: `${pngDir}/console-case.png` });
await page.getByRole("button", { name: /Run investigation|Run again/ }).click();
await page.getByRole("button", { name: "Replay run" }).waitFor({ timeout: 60000 });
await page.getByText("Investigation summary").scrollIntoViewIfNeeded();
await pause(700);
await page.getByRole("button", { name: "Replay run" }).click();
await pause(2600);
await page.screenshot({ path: `${pngDir}/console-trace-replay.png` });
await page.getByRole("button", { name: "Replay run" }).waitFor({ timeout: 20000 });
const reason = page.getByLabel("Reason for overriding the AI");
if (await reason.isVisible().catch(() => false)) {
  await reason.pressSequentially("Hot wallet of a known exchange, confirmed with the compliance desk.", { delay: 10 });
  await pause(400);
  await page.getByRole("button", { name: "Dismiss as licit" }).click();
  await page.getByText("Overrode the AI").waitFor({ timeout: 20000 });
  await pause(1500);
  await page.screenshot({ path: `${pngDir}/console-override.png` });
}

// 3. audit: tamper
await nav("Audit trail").click();
await page.getByText("Try to tamper with it").scrollIntoViewIfNeeded();
await pause(1000);
await page.locator(".blk > button").nth(3).click();
await page.getByRole("button", { name: /Change record/ }).click();
await pause(1500);
await page.screenshot({ path: `${pngDir}/console-tamper.png` });
await page.getByRole("button", { name: /cover their tracks/ }).click();
await page.getByText(/no longer matches the one the server saved/).waitFor({ timeout: 20000 });
await pause(1200);

// 4. decision lab
await nav("Decision Lab").click();
await page.locator(".stat-value").first().filter({ hasText: "%" }).waitFor({ timeout: 30000 });
await pause(1500);
await page.getByLabel("Hold from score").focus();
for (let i = 0; i < 10; i++) { await page.keyboard.press("ArrowRight"); await pause(130); }
await pause(1800);
await page.screenshot({ path: `${pngDir}/console-lab.png` });

// 5. overview with everything we just did
await nav("Overview").click();
await page.getByText("AI answers that passed the fact check on the first try.").waitFor();
await pause(2200);
await page.screenshot({ path: `${pngDir}/console-overview.png`, fullPage: false });
await nav("Reports").click();
await page.getByRole("link", { name: /Interception: does the AI questioning/ }).click();
await page.getByText("Interception: does the AI questioning add anything?").waitFor();
await pause(1200);
await page.screenshot({ path: `${pngDir}/console-report.png` });
await ctx.close();
await browser.close();
console.log("saved");
