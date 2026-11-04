"""Model gateway: the single door through which any LLM is called. It redacts personal data first, treats text as untrusted, validates every reply,
retries once, enforces budgets and timeouts, walks a fallback chain across providers, and ends in a deterministic path. No LLM sits in the kernel."""
