# Case notes and unresolved questions

The original `Кейс_ForteBank.docx` was not present in the empty repository. This implementation uses the requirements reproduced in the supplied build brief; it does not claim to have inspected the original case file.

The supplied brief reports an FAQ reference to **Insufficient data**, while the explicit successful judge schema has only `no_violation` and `violation`. This application retains those two successful values. Incomplete, corrupt, timed-out, unconfigured, and otherwise failed processing returns `failed` without a successful verdict.

The brief reports that a document-level citation can be accepted without a precise paragraph. A verified rule may therefore have a null `section_or_paragraph`; reviewers must see that lack of precision. The brief also mentions public documents from other banks. Such a source must be labelled as another bank's material, never presented as binding ForteBank policy or Kazakhstan legislation by assumption.

These are recorded ambiguities, not organizer clarifications. The production rule registry is intentionally empty. No regulation, source excerpt, paragraph number, taxonomy, or binding cashier procedure has been fabricated.

The 100 MB upload limit, 300 second media limit, 285 second accepted-job budget, architecture, and UI layout are implementation choices. The supplied evaluation budget is five minutes. A deadline mechanism does not establish that local inference is fast enough; benchmark actual deployment hardware and a permitted validation split.
