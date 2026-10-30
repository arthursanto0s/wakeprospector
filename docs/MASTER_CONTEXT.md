# MASTER CONTEXT — WAKE PROSPECTOR

## 1. Identidade

Projeto: Wake Prospector
Empresa: Wake Studio
Finalidade: uso interno para prospecção comercial.

## 2. Objetivo

Transformar uma instrução como:

> "Encontre 30 veterinárias em Niterói"

em uma fila de empresas potencialmente interessantes para prospecção, contendo evidências suficientes para que um humano possa revisar e iniciar contato.

## 3. Filosofia operacional

O agente deve pesquisar como um analista, não como um scraper.

Ele deve:

- formular buscas;
- cruzar fontes;
- verificar contradições;
- decidir o que ainda falta descobrir;
- aprofundar apenas quando isso aumenta a qualidade;
- registrar evidências;
- declarar incerteza;
- nunca preencher lacunas com invenção.

## 4. O que define um bom resultado

Um bom resultado não é a maior quantidade de empresas.

É:

> **lead correto + empresa correta + ausência de site razoavelmente verificada + responsável corretamente identificado quando possível + contato adequado + evidências + hipótese de oportunidade explicável.**

## 5. Separação fato/inferência

Cada afirmação relevante deve ser classificada mentalmente como:

FACT — diretamente sustentada por fonte.
INFERENCE — conclusão razoável derivada de fatos.
UNCERTAINTY — informação não confirmada.
CONFLICT — fontes discordam.

O resultado final deve deixar isso claro.

## 6. Responsável

Prioridade:

1. proprietário/sócio;
2. administrador;
3. responsável pela unidade;
4. responsável comercial;
5. responsável pelo atendimento.

Não assumir que o nome de alguém é o proprietário sem evidência.

## 7. Contato

O sistema busca o melhor número profissional/publicamente associado ao responsável.

Não procurar, inferir ou expor dados privados desnecessários.

Se não houver número individual verificável, usar o melhor contato comercial da empresa.

## 8. Oportunidade

O sistema não tenta prever compra.

Ele estima a força da **evidência de oportunidade digital**.

Sinais possíveis:

- atividade comercial;
- catálogo/produtos/serviços;
- agendamento;
- pedidos/orçamentos;
- delivery;
- WhatsApp;
- presença digital ativa;
- informações dispersas;
- ausência de site próprio;
- múltiplas necessidades de apresentação.

## 9. Controle humano

A V1 não envia mensagens automaticamente.

O agente prepara a ficha e a mensagem. O usuário revisa e envia.

Quando houver interesse real, o agente entrega a conversa ao usuário.

## 10. Restrições

Não construir na V1:

- API oficial de WhatsApp;
- disparador em massa;
- VPS;
- SaaS multiusuário;
- banco remoto obrigatório;
- IA local;
- automações agressivas;
- scraping rígido como mecanismo principal.

## 11. Critério de implementação

Antes de adicionar qualquer componente, perguntar:

> Isso melhora a capacidade de pesquisa/organização sem substituir o raciocínio contextual do agente?

Se não, não entra na V1.
