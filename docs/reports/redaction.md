# Name and address redaction (generated; do not edit by hand)

Before customer text reaches an AI model, the redactor replaces personal details with tokens. Patterns already handle emails, card numbers, phone numbers, IBANs and ID numbers. This report measures the added layer for **people's names** (a small spaCy language model) and **street addresses** (patterns). Cities and countries are deliberately left readable.

Name model available when this ran: yes.

## Did the personal detail disappear from the text?

| What was inserted into a sentence | Patterns only: fully removed | With the name model: fully removed | With the name model: partly removed | With the name model: left in place |
|---|---|---|---|---|
| US-style names (real Census parts) | 0% (0 of 300; 95% interval 0% to 1%) | 88% (265 of 300; 95% interval 84% to 91%) | 3% (9 of 300; 95% interval 2% to 6%) | 9% (26 of 300; 95% interval 6% to 12%) |
| Real OFAC individuals (many non-US names) | 0% (1 of 300; 95% interval 0% to 2%) | 73% (218 of 300; 95% interval 67% to 77%) | 9% (28 of 300; 95% interval 7% to 13%) | 18% (54 of 300; 95% interval 14% to 23%) |
| Street addresses (synthetic) | 100% (200 of 200; 95% interval 98% to 100%) | 100% (200 of 200; 95% interval 98% to 100%) | 0% (0 of 200; 95% interval 0% to 2%) | 0% (0 of 200; 95% interval 0% to 2%) |

'Partly removed' means some words of a multi-word name were redacted and others stayed visible.

## Does it change ordinary text it should not?

On the real SMS Spam Collection (5,574 messages), the name layer changed 14% (804 of 5574; 95% interval 14% to 15%) of messages. Many of those contain a real first name, which is correct to redact; this number is an upper bound on wrong changes, not an error rate. A random sample of what it redacted: `come wen`; `Wen`; `bx420-ip4-5we`; `you‘ll`; `Yummy`; `Mark`; `Grumpy`; `Kate`; `Dogging Network`; `K:)k:)good:)study`; `Kallis`; `Reply Toll Free`; `LS1 3AJ`; `Oru Minnaminunginte Nurungu Vettam`; `Xmas`.

Time per message: median 1.6 ms, 95th percentile 2.6 ms.

## Limits (read these)

- A statistical name model misses unusual names and can redact words that are not names; the numbers above are for these test sets only.
- US-style test names are real parts paired at random; addresses are synthetic and follow one common format. Addresses in other formats, other languages and other scripts are not tested.
- Names in non-Latin scripts are not tested at all.
- Redacted tokens appear in the model's input, so a claim copied from the redacted text will not match the customer's original words and is rejected by the existing word-for-word check; the system then falls back to a safe default.
