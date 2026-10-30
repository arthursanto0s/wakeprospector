# IMPLEMENTATION CONTRACT

Antigravity must treat this document set as the source of truth.

## Before coding

1. Read all files under `docs/`.
2. Read all `.agent/rules/`.
3. Identify contradictions.
4. Do not silently invent major requirements.
5. If a conflict exists, prefer:
   PROJECT_SPEC → SECURITY → OPERATING_MANUAL → ARCHITECTURE → individual skill.

## During coding

- Keep V1 small.
- Prefer simple local components.
- Avoid unnecessary dependencies.
- Do not introduce paid services.
- Do not introduce remote infrastructure without explicit approval.
- Do not replace agent reasoning with brittle hard-coded scraping rules.
- Keep deterministic logic testable.

## During research

- Never fabricate a source.
- Never fabricate a responsible person.
- Never fabricate a phone.
- Never mark a site as absent solely because a search result was empty.
- Never silently resolve conflicting evidence.

## During output

Every qualified lead must have:
- evidence;
- uncertainty notes;
- source references;
- recommended contact;
- suggested opening message;
- human review flag.

## Done means

A feature is not complete merely because the UI exists.

It is complete when:
- data model works;
- state transitions work;
- evidence is preserved;
- failures are explicit;
- the agent can use the workflow;
- test cases cover critical errors.
