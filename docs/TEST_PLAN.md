# TEST PLAN

## Critical tests

### T01 — Duplicate
Same company found from two sources must become one lead with multiple sources.

### T02 — False owner
Person shares company surname but no ownership evidence.
Expected: not marked owner.

### T03 — Phone ambiguity
Phone appears on company page but no person association.
Expected: company contact, not personal contact.

### T04 — Existing website
Company has official domain.
Expected: WEBSITE_FOUND and excluded from V1 target queue.

### T05 — Directory only
Company exists only in directory profile.
Expected: no own website inferred.

### T06 — Conflicting owner
Two sources name different responsible persons.
Expected: conflict recorded, confidence reduced.

### T07 — Strong opportunity
Active digital business, no site, commercial signals.
Expected: STRONG or POSSIBLE with evidence.

### T08 — No evidence
Sparse business presence.
Expected: UNCERTAIN/LOW_PRIORITY, not invented.

### T09 — Interest
User supplies a response showing meaningful interest.
Expected: INTERESTED_HANDOFF and no autonomous continuation.

### T10 — Refusal
Response declines.
Expected: NOT_INTERESTED and no pressure sequence.
