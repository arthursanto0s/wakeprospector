---
name: adversarial-lead-audit
description: >-
  Use this skill whenever discovering, verifying, qualifying, or reviewing leads for any niche
  and neighborhood. Performs a complete OSINT and public API sweep (Google Maps, BrasilAPI/ReceitaWS
  CNPJ/QSA, professional councils like CRMV/OAB/CRO, Instagram/Linktree), identifies the owner or
  marketing/commercial decision-maker phone, explains why that phone belongs to that exact business,
  and applies an Adversarial Audit ("Advogado do Diabo") that challenges every decision with
  counter-arguments before approving a lead.
---

# SKILL — AUDITORIA CONTRADITÓRIA E VARREDURA COMPLETA DE LEADS (`adversarial-lead-audit`)

Esta skill garante **precisão 1:1 absoluta** entre **Empresa ↔ Bairro ↔ Proprietário/Decisor ↔ Número de WhatsApp**, eliminando falsos positivos, telefones trocados entre empresas, números sintéticos e empresas que já possuem website próprio.

---

## 1. Varredura Completa Multi-Fonte e APIs Públicas (Zero-Cost)

Para cada empresa ou profissional candidato no bairro e nicho solicitados, execute a coleta cruzada em múltiplas camadas gratuitas:

1. **Google Maps / Perfil da Empresa e Diretórios Locais**:
   - Confirmar nome fantasia exato, endereço físico completo (logradouro, número, sala/loja, shopping/condomínio) e se pertence estritamente ao bairro solicitado.
   - Extrair o telefone principal e verificar o campo de website.
2. **APIs Públicas de CNPJ e Quadro Societário (QSA)**:
   - Consultar gratuitamente via `https://brasilapi.com.br/api/cnpj/v1/{cnpj}` ou `https://receitaws.com.br/v1/cnpj/{cnpj}` (ou busca pública em `cnpj.biz` / `cnpja.com`).
   - Extrair Razão Social, situação cadastral (`ATIVA`), CNAE compatível com o nicho e o **Quadro de Sócios e Administradores (QSA)** para identificar o verdadeiro proprietário.
   - **Atenção Crítica**: Nunca utilizar o telefone do escritório de contabilidade cadastrado no CNPJ como se fosse o telefone do proprietário. O telefone do CNPJ só é válido se corroborado pelos canais comerciais da própria empresa.
3. **Conselhos de Classe e Registros Técnicos (CRMV, OAB, CRO, CRM, CREFITO, etc.)**:
   - Identificar o Responsável Técnico (RT) ou profissional titular que assina pela clínica/escritório.
4. **Canais Digitais Ativos (Instagram, Linktree, Beacons, WhatsApp Business)**:
   - Inspecionar a bio do Instagram e agregadores de links (`linktr.ee`, `bio.site`, `wa.me/`) para extrair o **link direto de WhatsApp (`55DD9XXXXXXXX`)** configurado pela própria empresa/proprietário.

---

## 2. Identificação do Decisor e Auditoria de Proveniência do Número (`phone_provenance`)

O objetivo da Wake Studio é falar com quem **decide a contratação de um site ou serviço digital**:
1. **Proprietário / Sócio-Administrador / Fundador** (Prioridade 1);
2. **Responsável Técnico Titular / Diretor Clínico** (Prioridade 2);
3. **Gestor de Marketing / Comercial / Gerente de Unidade** (Prioridade 3);
4. **Canal Oficial Direto de Atendimento/Agendamento da Empresa** (quando operado diretamente pela gestão).

### Regra de Ouro do Telefone:
- **Proveniência Obrigatória (`phone_provenance`)**: Todo número deve vir acompanhado de uma justificativa explícita e auditável respondendo: *"Por que temos certeza de que este número pertence especificamente a esta empresa/decisor e não a outra?"*
- **Unicidade Estrita (1:1)**: Dois leads distintos **jamais** podem compartilhar o mesmo número de telefone normalizado.
- **Integridade do 9º Dígito**:
  - Celulares brasileiros possuem 11 dígitos nacionais (`DDD + 9 + 8 dígitos`, iniciando com `96`, `97`, `98` ou `99` após o DDD) → E.164 de 13 dígitos (`55DD9XXXXXXXX`).
  - Telefones fixos possuem 10 dígitos nacionais (`DDD + [2-5]XXXXXXX`) → **Jamais** inserir o dígito `9` artificialmente na frente de um número fixo.

---

## 3. Protocolo Dialético de Combate ("Advogado do Diabo")

Antes de aprovar qualquer lead para a fila `READY_FOR_REVIEW`, você **DEVE** combater a sua própria escolha com argumentos críticos (Tese → Antítese → Síntese):

### A. Tese (Proposta Inicial)
- Declaração objetiva de quem é a empresa, quem é o decisor identificado e qual é a hipótese de oportunidade comercial para criação de website.

### B. Antítese (Combate com Argumentos / Advogado do Diabo)
Questione implacavelmente o candidato em **4 frentes**:
1. **Contestação de Website Oculto**: *"Será que essa empresa realmente não tem site? E se ela tiver um domínio próprio (`.com.br`, `.vet.br`, `.adv.br`, `.med.br`) que apenas não apareceu no primeiro resultado, ou que está dentro do Linktree?"*
2. **Contestação de Correspondência do Número**: *"Tem certeza absoluta de que o número `(DD) 9XXXX-XXXX` abre o WhatsApp desta clínica específica? Não há risco de ser o número de uma clínica homônima, de outro bairro, de um ex-sócio ou de outra empresa da lista?"*
3. **Contestação de Localização e Operação Ativa**: *"A empresa está realmente ativa hoje no endereço informado dentro do bairro pedido, ou mudou-se / fechou?"*
4. **Contestação de Canal Decisor**: *"Ao enviar a mensagem do Arthur da Wake para este número, a mensagem chegará ao proprietário, responsável técnico ou setor de marketing/contratação, ou cairá em um call center terceirizado sem poder de decisão?"*

### C. Síntese (Veredito Comprobatório Pós-Auditoria)
- Apresente a refutação factual de cada objeção da Antítese com base nas evidências coletadas (URLs verificadas, ausência de domínio próprio confirmada via checagem de links e buscas diretas, confirmação cruzada do número no perfil oficial da empresa).
- Se qualquer objeção **não puder ser refutada** (ex: a empresa possui site próprio ativo, ou o número pertence a outra empresa), o lead deve ser **reprovado/descartado (`DISCARDED`)** ou corrigido imediatamente antes de ir ao CRM.

---

## 4. Execução via Código e Validação Determinística

1. Sempre utilize o serviço `AdversarialAuditService` em [`src/audit.py`](../../../src/audit.py) ou o comando de auditoria na CLI (`python -m src.cli audit-leads`) após qualquer ingestão.
2. Nenhum lote de prospecção está concluído até que `AdversarialAuditService.audit_all_leads()` retorne **0 colisões de telefone**, **0 números sintéticos**, **0 incoerências de mensagem** e **100% dos leads em `READY_FOR_REVIEW` com dossiê de auditoria contraditória preenchido**.
