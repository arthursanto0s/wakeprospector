---
name: outreach-preparation
description: >-
  Use this skill to craft the opening WhatsApp message from Arthur da Wake, tailored to the
  verified responsible person (with proper Dr./Dra. honorifics and gender agreement) or
  institutional contact.
---

# SKILL — OUTREACH PREPARATION

Generates natural, grammatically impeccable Portuguese opening messages with automatic time-of-day detection (`Bom dia` [05h–11h59], `Boa tarde` [12h–17h59], `Boa noite` [18h–04h59]):

1. **1º Contato — Quando enviando para o Número Pessoal do Doutor(a) / Sócio(a) (Medical / Veterinary / Legal with title)**:
   - Male: `"[Bom dia | Boa tarde | Boa noite], Dr. [Primeiro Nome], tudo bem?"` (e só!)
   - Female: `"[Bom dia | Boa tarde | Boa noite], Dra. [Primeiro Nome], tudo bem?"` (e só!)
2. **1º Contato — Quando enviando para o Número Pessoal de Proprietário Geral (sem honorífico Dr./Dra.)**:
   - `"[Bom dia | Boa tarde | Boa noite], [Primeiro Nome], tudo bem?"` (e só!)
3. **2º Contato (Fallback) — Quando enviando para a Clínica / Recepção / Atendimento Institucional**:
   - `"[Bom dia | Boa tarde | Boa noite]! Gostaria de falar com o responsável [pela/pelo] [Nome Limpo da Empresa]."`

Rules:
- Always dynamically detect the current time of day (`Bom dia`, `Boa tarde`, `Boa noite`) both in Python (`get_time_greeting()`) and in real-time JavaScript in the CRM frontend (`applyLiveGreeting()`).
- Clean corporate suffixes (`LTDA`, `ME`, `EIRELI`, redundant neighborhood tags) so the company name reads naturally in the clinic fallback message.
- Do not over-explain, promise results, or send automatically. Human review is mandatory.
