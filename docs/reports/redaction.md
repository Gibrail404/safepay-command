# Name and address redaction (generated; do not edit by hand)

Before customer text reaches an AI model, the redactor replaces personal details with tokens. Patterns handle emails, card numbers, phone numbers, IBANs, ID numbers and street addresses. For **people's names** there are two layers: a small spaCy language model, and a **name list** (about 105,484 name words from the real US Census and OFAC lists, with ordinary English words removed). The list redacts a run of two or more known name words, or one name word right after a cue such as 'landlord', 'pay' or 'named', or a name word touching a name the model already found. Cities and countries are deliberately left readable.

**Honest evaluation.** The list is built from real name lists, so testing it on those same names would be circular. The test names below are made only of words that the *evaluation list* (a random half of the real list, 52,706 words) does not contain, so they stand in for names the list has never seen. The last column uses the full shipped list on the same names and is an optimistic number, not an estimate.

Name model available when this ran: yes.

## Did the personal detail disappear from the text? (fully removed)

| What was inserted into a sentence | Patterns only | Language model only | Model plus the list (unseen words) | Model plus the full list (optimistic) |
|---|---|---|---|---|
| US-style names, words the list has not seen (300) | 0% (0 of 300; 95% interval 0% to 1%) | 92% (276 of 300; 95% interval 88% to 95%) | 92% (276 of 300; 95% interval 88% to 95%) | 99% (296 of 300; 95% interval 97% to 99%) |
| Real OFAC individuals, words the list has not seen (300) | 0% (1 of 300; 95% interval 0% to 2%) | 75% (226 of 300; 95% interval 70% to 80%) | 76% (227 of 300; 95% interval 71% to 80%) | 99% (296 of 300; 95% interval 97% to 99%) |
| Street addresses (synthetic) | 100% (200 of 200; 95% interval 98% to 100%) | 100% (200 of 200; 95% interval 98% to 100%) | 100% (200 of 200; 95% interval 98% to 100%) | 100% (200 of 200; 95% interval 98% to 100%) |

Left in place or only partly removed, for the same rows:

| What was inserted into a sentence | Model only: partly / left in place | Model plus the list (unseen words): partly / left in place |
|---|---|---|
| US-style names, words the list has not seen (300) | 0% / 8% | 0% / 8% |
| Real OFAC individuals, words the list has not seen (300) | 7% / 18% | 7% / 17% |
| Street addresses (synthetic) | 0% / 0% | 0% / 0% |

'Partly removed' means some words of a multi-word name were redacted and others stayed visible.

## Does it change ordinary text it should not?

On the real SMS Spam Collection (5,574 messages) the language model alone changed 14% (799 of 5574; 95% interval 13% to 15%) of messages, and the list changed **5% (275 of 5574; 95% interval 4% to 6%) more** (with the full list). Many contain a real first name, which is correct to redact, so these numbers are upper bounds on wrong changes, not error rates. What the list added, a random sample: `Box`; `GRAVEL`; `HEY HEY`; `AMY URE`; `Virgin`; `Wen`; `Hero`; `SHEFFIELD`; `MIX`; `Christmas`; `Code`; `Ocean`; `Cha Cha`; `Merry Christmas`; `N-Gage`; `FREE`; `Clos`; `Free`; `Hey`; `FREE`.

Time per message with both layers: median 1.6 ms, 95th percentile 2.5 ms.

## Limits (read these)

- Names built from random pairs of real words are a proxy for real customers' names. Real names have more variety, and nicknames, misspellings and lower-case typing are not tested (the list only matches capitalised words).
- Common words that are also names (for example Mark, Rose, Baker) are only redacted when they follow a cue word, touch a name the model found, or sit in a run of two name words.
- Addresses are synthetic and follow one common format; other formats and languages are not tested. Names in non-Latin scripts are not tested at all.
- Redacted tokens appear in the model's input, so a claim copied from the redacted text will not match the customer's original words and is rejected by the existing word-for-word check; the system then falls back to a safe default.
