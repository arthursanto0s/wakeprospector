# PROJECT SPECIFICATION

## 1. Missão

Criar um agente interno para a Wake Studio capaz de descobrir e preparar leads locais de alta relevância potencial para abordagem comercial.

## 2. Entrada mínima

- nicho;
- localização;
- quantidade desejada.

Exemplos:

- 20 veterinárias em Niterói;
- 30 adegas em São Gonçalo;
- 15 salões de beleza em Icaraí.

## 3. Pipeline

DISCOVERY
→ ENTITY VERIFICATION
→ WEBSITE VERIFICATION
→ RESPONSIBLE IDENTIFICATION
→ CONTACT IDENTIFICATION
→ OPPORTUNITY ANALYSIS
→ QUALIFICATION
→ OUTREACH PREPARATION
→ HUMAN CONTACT
→ RESPONSE ANALYSIS
→ HUMAN HANDOFF

## 4. Resultado mínimo por lead

- internal_id;
- business_name;
- category;
- city;
- neighborhood/address if useful;
- website_status;
- website evidence;
- phone(s);
- social profiles;
- responsible name if found;
- responsible role;
- responsible evidence;
- contact number;
- contact type;
- contact evidence;
- confidence;
- opportunity classification;
- evidence summary;
- uncertainties;
- suggested opening message;
- sources;
- discovered_at;
- updated_at;
- pipeline_status.

## 5. Status do pipeline

NEW
RESEARCHING
VERIFIED
NO_WEBSITE
RESPONSIBLE_FOUND
CONTACT_FOUND
QUALIFIED
READY_FOR_REVIEW
CONTACTED
WAITING_REPLY
RESPONDED
INTERESTED_HANDOFF
NOT_INTERESTED
NOT_RESPONSIBLE
DISCARDED
UNCERTAIN

## 6. Regras de descarte

Descartar ou separar da fila principal quando:

- não pertence ao nicho;
- localização incompatível;
- é duplicado;
- possui site próprio confirmado;
- empresa não pode ser confirmada;
- contato é claramente inválido;
- evidências são insuficientes para uso responsável.

## 7. Não apagar evidência

Um lead descartado deve continuar registrado com o motivo.

## 8. Não usar score falso

Não implementar inicialmente "87/100".

Usar classificação explicável:

STRONG
POSSIBLE
UNCERTAIN
LOW_PRIORITY

## 9. Saída para revisão humana

A ficha deve permitir decisão rápida:

- Quem é?
- Onde está?
- Tem site?
- Quem é o responsável?
- Qual número devo usar?
- Por que vale a pena abordar?
- Quais são as incertezas?
- De onde veio cada informação?
- Qual mensagem inicial sugerida?
