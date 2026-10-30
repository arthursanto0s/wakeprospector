---
name: company-verification
description: >-
  Use this skill to verify a candidate business's identity, niche, exact address/neighborhood,
  operating status, and own website status before advancing it in the Wake Prospector pipeline.
---

# SKILL — COMPANY VERIFICATION

Verify:
- business identity (trade name + legal entity/CNPJ where available);
- niche compatibility;
- exact location (city, neighborhood, street address, shopping/condominium);
- active operating status;
- own website status.

Website rules:
- official proprietary domain (`.com.br`, `.vet.br`, `.adv.br`, `.com`, etc.) = `WEBSITE_FOUND` (exclude from V1 queue with mandatory discard reason);
- Instagram / Facebook / Linktree / Beacons / Google Maps / directory = NOT own website (`NO_WEBSITE_CONFIRMED` or `NO_WEBSITE_FOUND`);
- uncertain result = `UNCERTAIN`.

Always cross-check with `adversarial-lead-audit` to challenge whether a hidden website exists inside social bios or Linktree.
Document all primary/secondary sources.
