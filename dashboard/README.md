# Painel web

Painel para visualizar lançamentos e relatórios do assistente financeiro. Ainda não implementado; este documento define a estrutura proposta.

## Estado atual

- Existe apenas esta documentação.
- O Worker expõe somente `/health` e `/telegram/webhook`.
- As funções de consulta já existem em `worker/src/expenses.ts` e podem ser reutilizadas pelas rotas do painel.

## Arquitetura proposta

- Front-end estático em TypeScript, hospedado no Cloudflare Pages.
- API no mesmo Worker, sob `/api/dashboard/*`.
- Autenticação por sessão em cookie `HttpOnly`, `Secure` e `SameSite=Strict`, assinado com HMAC no Worker.
- Sem token em `localStorage`; sem CORS amplo.
- Dados sempre filtrados pelo usuário autenticado.

## Estrutura de arquivos

```text
dashboard/
├── index.html
├── src/
│   ├── main.ts
│   ├── api/
│   │   └── client.ts
│   ├── auth/
│   │   └── session.ts
│   ├── components/
│   │   ├── summary-cards.ts
│   │   ├── category-chart.ts
│   │   ├── transaction-table.ts
│   │   └── filters.ts
│   └── styles/
│       └── main.css
├── public/
│   └── favicon.svg
├── package.json
├── tsconfig.json
└── README.md
```

## Rotas previstas no Worker

| Rota | Método | Uso |
| --- | --- | --- |
| `/api/auth/login` | POST | Cria a sessão assinada |
| `/api/auth/logout` | POST | Encerra a sessão |
| `/api/dashboard/summary?from=&to=` | GET | Totais, saldo e despesas por categoria |
| `/api/dashboard/transactions?from=&to=&category=` | GET | Lista paginada |
| `/api/dashboard/transactions` | POST | Cria lançamento manual |
| `/api/dashboard/transactions/:id` | PATCH | Corrige lançamento |
| `/api/dashboard/transactions/:id` | DELETE | Soft delete |

Todas as rotas exigem sessão válida e retornam apenas dados do usuário autenticado.

## Autenticação

1. Adicionar `DASHBOARD_PASSWORD_HASH` e `DASHBOARD_SESSION_SECRET` como secrets do Worker.
2. `POST /api/auth/login` compara a senha com o hash e cria um cookie assinado.
3. O cookie contém apenas um identificador de sessão e expiração.
4. Mapear a sessão para um `user_id` existente (o dono do bot) ou criar uma tabela `dashboard_sessions` em uma migration futura.
5. Aplicar limite de tentativas e invalidação de sessão no logout.

## Etapas de implementação

1. Layout estático com dados fictícios e estados de carregamento/erro.
2. Rotas de leitura no Worker + autenticação por sessão.
3. Filtros de período/categoria e gráfico de despesas.
4. Edição e exclusão com confirmação, reutilizando as regras de auditoria.
5. Testes das rotas com Vitest e testes de fumaça do front-end.
6. Deploy no Cloudflare Pages apontando para o Worker.

## Decisões em aberto

- Biblioteca de gráficos: SVG próprio, Chart.js ou Recharts.
- Framework do front-end: TypeScript puro ou React/Vite.
- Modelo de sessão: tabela dedicada ou token assinado stateless.
- Necessidade de múltiplos usuários no painel ou apenas o dono do bot.
