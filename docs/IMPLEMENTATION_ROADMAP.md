# IMPLEMENTATION ROADMAP

## Phase 0 — Read and audit
Read all docs/rules/skills. Resolve contradictions before coding.

## Phase 1 — Foundation
- project metadata;
- SQLite/local persistence;
- lead schema;
- source schema;
- statuses;
- deduplication;
- logs.

## Phase 2 — Agent workflows
- discovery;
- company verification;
- responsible identification;
- contact identification;
- opportunity analysis;
- qualification.

## Phase 3 — Review interface
Only the minimum interface necessary to inspect lead cards and status.

## Phase 4 — Outreach preparation
- message generator;
- human review;
- contact state.

## Phase 5 — Response analysis
- conversation storage;
- intent classification;
- handoff.

## Phase 6 — Audit
Run `docs/TEST_PLAN.md`.
Verify no unsupported automation or paid dependency was introduced.

## Phase 7 — Only then consider V2
Do not expand scope before V1 is operational.
