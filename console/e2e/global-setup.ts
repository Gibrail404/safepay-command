// Test fixtures only: three small cases labelled as simulated, so the browser tests have something to open. They are not product data.
const item = (ref: string, score: number, linked = 0) => ({ ref, score, time_step: 40, facts: { neighbours: 3, linked_alerts: linked } });
export default async function globalSetup() {
  const res = await fetch("http://127.0.0.1:8100/v1/cases/import", {
    method: "POST",
    headers: { "X-API-Key": "e2e-admin", "Content-Type": "application/json" },
    body: JSON.stringify({
      cases: [
        { external_id: "fx-1", source: "e2e-fixture", provenance: "simulated", priority: "high", title: "Fixture: two linked alerts", items: [item("fx-a", 0.97, 1), item("fx-b", 0.93, 1)], facts: { dataset: "test fixture", links: [["fx-a", "fx-b"]] }, truth: { "fx-a": 1, "fx-b": 0 } },
        { external_id: "fx-2", source: "e2e-fixture", provenance: "simulated", priority: "normal", title: "Fixture: one weak alert", items: [item("fx-c", 0.6)], facts: { dataset: "test fixture" }, truth: { "fx-c": 0 } },
        { external_id: "fx-4", source: "e2e-fixture", provenance: "simulated", priority: "normal", title: "Fixture: linked pair", items: [item("fx-e", 0.9, 1), item("fx-f", 0.85, 1)], facts: { dataset: "test fixture", links: [["fx-e", "fx-f"]] } },
        { external_id: "fx-3", source: "e2e-fixture", provenance: "real", priority: "normal", title: "Fixture: second case", items: [item("fx-d", 0.95)], facts: { dataset: "test fixture" } },
      ],
    }),
  });
  if (!res.ok) throw new Error(`fixture import failed: ${res.status}`);
  const people = [["e2e-admin", "admin@e2e.test", "Tester", "admin"], ["e2e-admin", "ana@e2e.test", "Ana Analyst", "admin"], ["e2e-admin", "viewer@e2e.test", "Vera Viewer", "viewer"], ["empty-key", "empty@e2e.test", "Tester", "admin"]];
  for (const [key, email, name, role] of people) {      // test accounts, added the way an admin would add people
    const r = await fetch("http://127.0.0.1:8100/v1/auth/users", { method: "POST", headers: { "X-API-Key": key, "Content-Type": "application/json" }, body: JSON.stringify({ email, name, role, password: "test-password-1" }) });
    if (!r.ok) throw new Error(`test account ${email} failed: ${r.status}`);
  }
}
