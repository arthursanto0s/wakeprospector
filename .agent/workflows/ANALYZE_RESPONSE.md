# WORKFLOW — ANALYZE RESPONSE

Input:
lead ID + response text

Steps:
1. Preserve original response.
2. Classify intent.
3. Extract questions/objections.
4. If explicit interest: INTERESTED_HANDOFF.
5. If refusal: NOT_INTERESTED.
6. If wrong person: NOT_RESPONSIBLE.
7. If ambiguous: UNCERTAIN.
8. Produce concise handoff summary.
