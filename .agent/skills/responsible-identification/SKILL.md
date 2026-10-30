---
name: responsible-identification
description: >-
  Use this skill to identify the owner, partner, technical manager (RT), or marketing/commercial
  decision-maker of a business using official registries (QSA/CNPJ, CRMV, OAB) and public channels.
---

# SKILL — RESPONSIBLE IDENTIFICATION

Goal:
Identify the most relevant decision-maker for hiring a website or digital service.

Search priority order:
1. Owner / Founding Partner / Sócio-Administrador (via QSA / CNPJ);
2. Technical Responsible / Clinical Director (via CRMV-RJ, OAB-RJ, CRO-RJ, CRM-RJ, etc.);
3. Marketing / Commercial / Expansion Manager;
4. Unit Manager / Administrator;
5. Direct Attendance / Scheduling Coordinator.

For each candidate record:
- full name;
- exact role (and registration/CNPJ when available);
- relationship proof linking `person ↔ company`;
- verified source URL;
- confidence level (`HIGH`, `MEDIUM`, `LOW`, `UNKNOWN`).

Never infer ownership merely from surname coincidence, customer photos, or social media followers (`T02`). If two sources conflict on ownership, log explicit conflict (`T06`).
