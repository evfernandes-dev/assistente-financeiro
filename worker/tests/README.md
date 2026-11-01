# Testes

Suíte automatizada do assistente financeiro, executada em `worker/`.

## Como rodar

```powershell
cd worker
npm test
npm run typecheck
npx wrangler deploy --dry-run
```

## Estrutura

| Arquivo | Cobertura |
| --- | --- |
| `finance-utils.test.ts` | Valores em reais, datas ISO, categorias, períodos e sanitização do JSON da IA. |
| `integration.test.ts` | Schema real em PGlite, despesas e receitas, consultas, relatórios, correção, exclusão, isolamento por usuário, auditoria e fluxo de áudio. |
| `transcription.test.ts` | Transcrição Groq, MIME, nome do arquivo, erros HTTP, resposta vazia e limite de 25 MB. |
| `audio.test.ts` | Metadados do Telegram, download, erros e limite de 20 MB. |
| `reports.test.ts` | Formatação de confirmação, lista, saldo e relatório mensal. |
| `webhook.test.ts` | Health check, segredo do webhook, JSON inválido e enfileiramento de updates. |

## Ambiente de teste

- Vitest em Node 24, sem rede externa.
- PGlite executa o mesmo `database/schema.sql` usado no Neon, incluindo `plpgsql`, trigger de `updated_at`, índices e auditoria.
- O driver `@neondatabase/serverless` é substituído por um adaptador que envia as mesmas queries parametrizadas ao PGlite.
- `fetch` é simulado para Groq, Telegram e download de áudio; nenhuma chave real é usada.
- Os testes não alteram o banco do Neon.

## Resultado atual

6 arquivos de teste, 44 testes passando.

## Testes reais em produção

- Texto: despesa, receita, consulta, relatório, correção e exclusão aprovados.
- Áudio: transcrição e lançamento com `source=audio` aprovados.
- Banco: centavos, `user_id`, soft delete e `audit_log` com before/after verificados.

## Pendente

- Testes do painel web, quando implementado.
- Testes de falha forçada de Groq/Neon em produção.
