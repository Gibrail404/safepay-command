import { expect, test, type Page } from "@playwright/test";

const API = "http://127.0.0.1:8100";
async function connect(page: Page, key: string, name = "Tester") {
  await page.goto("/");
  await page.getByLabel("Server address").fill(API);
  await page.getByLabel("API key").fill(key);
  await page.getByLabel(/Your name/).fill(name);
  await page.getByRole("button", { name: "Connect" }).click();
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Cases", exact: true }).click();      // the landing page is the overview; most tests start from the case queue
}

test("a wrong key shows a plain error, not a crash", async ({ page }) => {
  await connect(page, "wrong-key");
  await expect(page.getByRole("alert").first()).toContainText("The API key was not accepted");
});

test("an account with no cases shows the empty state", async ({ page }) => {
  await connect(page, "empty-key");
  await expect(page.getByText("No cases here yet")).toBeVisible();
});

test("queue shows the fixture cases with provenance chips and counts", async ({ page }) => {
  await connect(page, "e2e-admin");
  await expect(page.getByRole("link", { name: "Fixture: two linked alerts" })).toBeVisible();
  await expect(page.locator(".stat-label", { hasText: "Open cases" })).toBeVisible();
  await expect(page.locator(".stat-value").first()).toHaveText("4");
  await expect(page.getByText("Simulated").first()).toBeVisible();
  await expect(page.getByText("Real data").first()).toBeVisible();
});

test("investigate, decide, see labels revealed, then find it in the audit trail", async ({ page }) => {
  page.on("dialog", (d) => d.accept());
  await connect(page, "e2e-admin", "Ana Analyst");
  await page.getByRole("link", { name: "Fixture: two linked alerts" }).click();
  await expect(page.getByRole("heading", { name: "Fixture: two linked alerts" })).toBeVisible();
  await expect(page.getByText("What the dataset says")).toHaveCount(0);          // truth hidden before a decision

  await page.getByRole("button", { name: "Run investigation" }).click();
  await expect(page.getByText(/Safe plain-text summary/)).toBeVisible();          // no AI key in this setup, so the safe fallback is used
  await expect(page.locator(".cite").first()).toBeVisible();

  await page.getByRole("button", { name: "Dismiss as licit" }).click();
  await expect(page.getByText("What the dataset says (revealed after your decision)")).toBeVisible();
  await expect(page.getByRole("cell", { name: "Illicit", exact: true })).toBeVisible();
  await expect(page.getByText(/by Ana Analyst/)).toBeVisible();

  await page.getByRole("link", { name: "Audit trail" }).click();
  await expect(page.getByText("Chain intact")).toBeVisible();
  await expect(page.getByText(/Ana Analyst → dismissed_licit \(2 labels\)/)).toBeVisible();
});

test("a weak lone alert abstains without any AI", async ({ page }) => {
  await connect(page, "e2e-admin");
  await page.getByRole("link", { name: "Fixture: one weak alert" }).click();
  await page.getByRole("button", { name: "Run investigation" }).click();
  await expect(page.getByText(/Not enough evidence to recommend/)).toBeVisible();
  await expect(page.getByText(/Fixed rule, no AI used/)).toBeVisible();
});

test("a read-only role can look but not act", async ({ page }) => {
  await connect(page, "e2e-viewer");
  await page.getByRole("link", { name: "Fixture: second case" }).click();
  await expect(page.getByText("Your role is read-only")).toBeVisible();
  await expect(page.getByRole("button", { name: "Escalate" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Run investigation" })).toBeDisabled();
});

test("reports page labels simulated and real reports", async ({ page }) => {
  await connect(page, "e2e-admin");
  await page.getByRole("link", { name: "Reports" }).click();
  const report = page.getByRole("main").getByRole("link", { name: "Decision Lab" });      // the nav also has a "Decision Lab" link (the live page)
  await expect(report).toBeVisible();
  await report.click();
  await expect(page.getByText("Simulated").first()).toBeVisible();
  await expect(page.getByText(/All numbers on this page come from a simulator/)).toBeVisible();
});

test("on a phone-sized screen the page does not scroll sideways", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await connect(page, "e2e-admin");
  await expect(page.getByRole("link", { name: "Fixture: second case" })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});


test("the run trace shows real steps, replays, and links to the ledger entry", async ({ page }) => {
  await connect(page, "e2e-admin");
  await page.getByRole("link", { name: "Fixture: second case" }).click();
  await page.getByRole("button", { name: "Run investigation" }).click();
  await expect(page.getByText(/The AI gave no usable answer/)).toBeVisible();
  const steps = page.getByRole("list", { name: "Steps of this run" }).getByRole("button");
  await expect(steps).toHaveCount(8);                                              // facts, screen, rule, ai, fact check, fallback, priority, ledger
  await page.getByRole("button", { name: "Replay run" }).click();
  await expect(page.getByRole("button", { name: "Replaying…" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Replay run" })).toBeEnabled({ timeout: 15_000 });
  await page.getByRole("button", { name: /^Fact check/ }).click();
  await expect(page.getByText("The AI gave no reply to check.")).toBeVisible();      // honest: it is skipped, not shown as passed
  await page.getByRole("button", { name: /^Audit ledger/ }).click();
  await expect(page.getByText(/Record #\d+/)).toBeVisible();
});

test("a weak lone alert's trace stops at the abstain rule", async ({ page }) => {
  await connect(page, "e2e-admin");
  await page.getByRole("link", { name: "Fixture: one weak alert" }).click();
  await page.getByRole("button", { name: /Run investigation|Run again/ }).click();
  await expect(page.getByRole("button", { name: /^Abstain rule: Stopped here/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /^AI summary: Not used/ })).toBeVisible();
});

test("tamper demo: your browser verifies the chain, a change breaks it, covering tracks is still caught", async ({ page }) => {
  await connect(page, "e2e-admin");
  await page.getByRole("link", { name: "Audit trail" }).click();
  const verdict = page.getByRole("status").filter({ hasText: /records verify in your browser|Chain breaks|saved separately/ });
  await expect(verdict).toContainText("verify in your browser");
  const first = page.locator(".blk > button").first();
  await first.click();
  await page.getByRole("button", { name: /Change record/ }).click();
  await expect(verdict).toContainText("Chain breaks at record");
  await expect(page.locator(".bs-untrusted").first()).toBeVisible();                // later records are no longer trusted
  await page.getByRole("button", { name: /cover their tracks/ }).click();
  await expect(verdict).toContainText("no longer matches the one the server saved", { timeout: 15_000 });
  await page.getByRole("button", { name: "Reset" }).click();
  await expect(verdict).toContainText("verify in your browser");
});

test("decision lab: a simulated result that moves when you move the slider", async ({ page }) => {
  await connect(page, "e2e-admin");
  await page.getByRole("link", { name: "Decision Lab" }).click();
  await expect(page.getByText("Simulated").first()).toBeVisible();
  const stat = page.locator(".stat-value").first();
  await expect(stat).toHaveText(/^\d+%$/, { timeout: 30_000 });
  await page.waitForTimeout(900);
  const before = Number((await stat.innerText()).replace("%", ""));
  await page.getByLabel("Hold from score").focus();
  for (let i = 0; i < 12; i++) await page.keyboard.press("ArrowRight");               // raising the hold threshold must stop less scam money
  await expect.poll(async () => Number((await stat.innerText()).replace("%", "")), { timeout: 30_000 }).toBeLessThan(before);
  await expect(page.getByRole("img", { name: /Scam money stopped against good payments held/ })).toBeVisible();
});


// These use the real risk model and real held-out transactions (so they need the project's data and trained model locally), with a scripted customer and no AI key.
test("interception: an honest scam victim's answers get the payment held and the hidden truth is revealed", async ({ page }) => {
  await connect(page, "e2e-admin");
  await page.getByRole("link", { name: "Interception" }).click();
  await page.getByRole("radio", { name: /Scam victim who answers honestly/ }).click();
  await page.getByText("Play the customer for me").click();
  await page.getByRole("button", { name: "Start this payment" }).click();
  await expect(page.getByText("What this scenario really was")).toBeVisible({ timeout: 60_000 });
  await expect(page.locator(".decision").getByText("Held for review")).toBeVisible();
  await expect(page.getByText("Someone else told the customer to pay").first()).toBeVisible();
  await expect(page.getByText("The policy held a real scam.")).toBeVisible();
  await expect(page.getByRole("list", { name: "Steps of this run" }).getByRole("button")).toHaveCount(8);
  await expect(page.getByText(/Recorded as ledger entry/)).toBeVisible();
});

test("interception: playing the customer by typing, a genuine payment is not held", async ({ page }) => {
  await connect(page, "e2e-admin");
  await page.getByRole("link", { name: "Interception" }).click();
  await page.getByRole("radio", { name: /Large payment to a new payee/ }).click();
  await page.getByRole("button", { name: "Start this payment" }).click();
  for (const a of ["I am paying my builder for the bathroom work.", "Yes, I have met him several times.", "No, there is no rush."]) {
    await page.getByLabel("Your answer").fill(a);
    await page.getByRole("button", { name: "Send" }).click();
    await expect(page.locator(".bubble.a", { hasText: a })).toBeVisible();
  }
  await expect(page.getByText("What this scenario really was")).toBeVisible({ timeout: 30_000 });
  await expect(page.locator(".decision").getByText("Allowed")).toBeVisible();
  await expect(page.getByText("A genuine payment went through.")).toBeVisible();
});

test("interception: an ordinary payment goes straight to the policy with no questions", async ({ page }) => {
  await connect(page, "e2e-admin");
  await page.getByRole("link", { name: "Interception" }).click();
  await page.getByRole("radio", { name: /Ordinary payment to a known payee/ }).click();
  await page.getByText("Play the customer for me").click();
  await page.getByRole("button", { name: "Start this payment" }).click();
  await expect(page.getByText(/No reason to add friction/)).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole("heading", { name: "Conversation with the customer" })).toHaveCount(0);
  await expect(page.locator(".decision").getByText("Allowed")).toBeVisible();
});

test("interception: a read-only role cannot start a payment", async ({ page }) => {
  await connect(page, "e2e-viewer");
  await page.getByRole("link", { name: "Interception" }).click();
  await expect(page.getByRole("button", { name: "Your role is read-only" })).toBeDisabled();
});


test("overview: real counts, the AI guardrail gauge and the open cases", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Server address").fill(API);
  await page.getByLabel("API key").fill("e2e-admin");
  await page.getByLabel(/Your name/).fill("Tester");
  await page.getByRole("button", { name: "Connect" }).click();
  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
  await expect(page.getByText("AI answers that passed the fact check on the first try.")).toBeVisible();
  await expect(page.getByRole("img", { name: /percent of AI answers passed the fact check first time|No AI summaries yet/ })).toBeVisible();
  await expect(page.getByRole("img", { name: "Ledger records per hour over the last 24 hours" })).toBeVisible();      // earlier tests recorded activity
  await expect(page.getByRole("heading", { name: "Open cases to look at" })).toBeVisible();
  await expect(page.getByText(/Everything here is counted from what this server has really recorded/)).toBeVisible();
});

test("overview: an account with no activity shows empty states, not made-up numbers", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Server address").fill(API);
  await page.getByLabel("API key").fill("empty-key");
  await page.getByLabel(/Your name/).fill("Tester");
  await page.getByRole("button", { name: "Connect" }).click();
  await expect(page.getByText("Nothing was recorded in the last 24 hours.")).toBeVisible();
  await expect(page.getByText(/No payment decisions yet/)).toBeVisible();
  await expect(page.getByRole("img", { name: "No AI summaries yet" })).toBeVisible();
});

test("a case with real links shows the alert network", async ({ page }) => {
  await connect(page, "e2e-admin");
  await page.getByRole("link", { name: "Fixture: linked pair" }).click();
  await expect(page.getByRole("heading", { name: "How these alerts are linked" })).toBeVisible();
  await expect(page.getByRole("img", { name: "2 alerts and 1 direct links between them" })).toBeVisible();
});
