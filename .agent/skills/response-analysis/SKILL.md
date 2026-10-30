---
name: response-analysis
description: >-
  Use this skill to classify incoming WhatsApp responses from prospects and trigger immediate
  human handoff when interest or a meeting request is detected.
---

# SKILL — RESPONSE ANALYSIS

Classify incoming prospect replies into:
- `RESPONSIBLE_CONFIRMED`
- `NOT_RESPONSIBLE`
- `ASKING_CONTEXT`
- `INTERESTED`
- `NOT_INTERESTED`
- `MEETING_REQUEST`
- `UNCERTAIN`

Extract:
- intent;
- questions asked;
- objections raised;
- recommended next action.

Critical Rule:
- `INTERESTED` or `MEETING_REQUEST` => transition immediately to `INTERESTED_HANDOFF`, generate executive handoff dossier, and cease autonomous outreach.
- `NOT_INTERESTED` => transition immediately to `NOT_INTERESTED` and stop contact.
