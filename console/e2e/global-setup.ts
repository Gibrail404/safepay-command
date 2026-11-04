// Test fixtures only: three small cases labelled as simulated, so the browser tests have something to open. They are not product data.
const item = (ref: string, score: number, linked = 0) => ({ ref, score, time_step: 40, facts: { neighbours: 3, linked_alerts: linked } });
export default async function globalSetup() {
  const res = await fetch("http://127.0.0.1:8100/v1/cases/import", {
    method: "POST",
    headers: { "X-API-Key": "e2e-admin", "Content-Type": "application/json" },
    body: JSON.stringify({
      cases: [
        { external_id: "fx-1", source: "e2e-fixture", provenance: "simulated", priority: "high", title: "Fixture: two linked alerts", items: [item("fx-a", 0.97, 1), item("fx-b", 0.93, 1)], facts: { dataset: "test fixture" }, truth: { "fx-a": 1, "fx-b": 0 } },
        { external_id: "fx-2", source: "e2e-fixture", provenance: "simulated", priority: "normal", title: "Fixture: one weak alert", items: [item("fx-c", 0.6)], facts: { dataset: "test fixture" }, truth: { "fx-c": 0 } },
        { external_id: "fx-3", source: "e2e-fixture", provenance: "real", priority: "normal", title: "Fixture: second case", items: [item("fx-d", 0.95)], facts: { dataset: "test fixture" } },
      ],
    }),
  });
  if (!res.ok) throw new Error(`fixture import failed: ${res.status}`);
}
