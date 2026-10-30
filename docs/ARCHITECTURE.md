# ARCHITECTURE

## 1. Modelo

Antigravity = agente/orquestrador/pesquisador.
Local project = memória e infraestrutura.
User = aprovação e fechamento.

## 2. Componentes

### Rules
Regras permanentes do projeto.

### Skills
Procedimentos especializados que o agente pode executar.

### Workflows
Sequências operacionais reproduzíveis.

### Data
Persistência local de leads, pesquisas, conversas e logs.

### Docs
Contexto, decisões e contratos.

### src
Código determinístico. Não deve conter regras comerciais rígidas que prejudiquem pesquisa contextual.

## 3. Persistência

Preferência V1: SQLite local.

Alternativa temporária: JSON estruturado.

Não introduzir banco remoto apenas por conveniência.

## 4. Princípio de deterministicidade

Código deve cuidar de:

- IDs;
- normalização;
- deduplicação;
- armazenamento;
- atualização de status;
- timestamps;
- histórico;
- validação estrutural.

Agente deve cuidar de:

- busca;
- interpretação;
- seleção de fontes;
- investigação;
- síntese;
- análise de oportunidade;
- identificação de responsáveis;
- redação contextual.

## 5. Deduplicação

Chaves de forte evidência:

1. telefone normalizado;
2. domínio do site;
3. combinação nome + cidade;
4. endereço + nome;
5. outras evidências cruzadas.

Nunca excluir automaticamente apenas por similaridade textual fraca.

## 6. Evidências

Toda informação relevante deve apontar para uma fonte e, quando possível, data de verificação.

## 7. Pesquisa adaptativa

Não usar um número fixo de buscas para todas as empresas.

Fluxo:

1. descoberta;
2. identificar lacunas;
3. pesquisar lacunas;
4. validar;
5. aprofundar se necessário;
6. parar quando a confiança for suficiente ou a informação permanecer incerta.

## 8. Falha segura

Se não houver evidência:

- não inventar;
- registrar como UNKNOWN/UNCERTAIN;
- explicar o que faltou.

## 9. Segurança operacional

Nenhuma credencial, token ou dado secreto deve ser colocado em arquivos de leads.

Nunca colocar credenciais em frontend, JSON público ou Git.

## 10. Evolução futura

Possíveis V2:

- painel local;
- automações auxiliares;
- CRM;
- métricas de conversão;
- aprendizagem baseada em resultados reais;
- integrações.

Nenhuma dessas extensões deve bloquear a V1.
