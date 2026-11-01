import { afterAll, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import type { PGlite } from "@electric-sql/pglite";
import {
  createTestDatabase,
  resetTestDatabase,
  type TestDatabase,
} from "./helpers/test-db";
import type { Env } from "../src/index";

const state = vi.hoisted(() => ({
  query: null as null | ((
    strings: TemplateStringsArray,
    ...values: unknown[]
  ) => Promise<unknown[]>),
}));

vi.mock("@neondatabase/serverless", () => ({
  neon: () => {
    return (strings: TemplateStringsArray, ...values: unknown[]) => {
      if (!state.query) {
        throw new Error("Test database not initialized");
      }

      return state.query(strings, ...values);
    };
  },
}));

import { handleFinancialMessage } from "../src/ai";
import {
  createTransaction,
  deleteTransaction,
  ensureUser,
  getLatestTransaction,
  getMonthlySummary,
  listTransactions,
  updateTransaction,
  type User,
} from "../src/expenses";
import { handleTelegramUpdate } from "../src/telegram";

const env: Env = {
  TELEGRAM_BOT_TOKEN: "test-token",
  TELEGRAM_WEBHOOK_SECRET: "test-secret",
  DATABASE_URL: "postgresql://test:test@localhost/test",
  GROQ_API_KEY: "test-groq-key",
  GROQ_MODEL: "test-model",
  GROQ_TRANSCRIPTION_MODEL: "test-whisper",
};

let testDb: TestDatabase;
let nextTelegramId = 9000;

beforeAll(async () => {
  testDb = await createTestDatabase();
  state.query = testDb.sql;
});

beforeEach(async () => {
  await resetTestDatabase(testDb.db);
});

afterAll(async () => {
  await testDb.db.close();
});

function today(): string {
  return new Intl.DateTimeFormat("sv-SE", {
    timeZone: "America/Recife",
    dateStyle: "short",
  }).format(new Date());
}

function monthStart(): string {
  return `${today().slice(0, 7)}-01`;
}

async function createUser(): Promise<{ user: User; telegramId: number }> {
  nextTelegramId += 1;
  const user = await ensureUser(
    {
      id: nextTelegramId,
      first_name: "Teste",
      username: `teste${nextTelegramId}`,
    },
    env,
  );

  return { user, telegramId: nextTelegramId };
}

async function createEntry(
  user: User,
  overrides: Partial<Parameters<typeof createTransaction>[0]> = {},
) {
  return createTransaction(
    {
      userId: user.id,
      kind: "expense",
      amount: 100,
      description: "Teste",
      category: "Outros",
      occurredAt: today(),
      source: "text",
      ...overrides,
    },
    env,
  );
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function mockGroq(content: unknown) {
  const fetchMock = vi.fn(async () =>
    jsonResponse({
      choices: [
        {
          message: {
            content:
              typeof content === "string" ? content : JSON.stringify(content),
          },
        },
      ],
    }),
  );

  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("persistência e auditoria", () => {
  it("cria despesa e receita e registra auditoria", async () => {
    const { user } = await createUser();

    const categories = await testDb.db.query<{ count: number }>(
      "select count(*)::int as count from categories where user_id = $1",
      [user.id],
    );
    expect(categories.rows[0].count).toBe(10);

    const expense = await createEntry(user, {
      amount: 87.5,
      description: "Mercado",
      category: "Alimentação",
    });

    expect(expense.kind).toBe("expense");
    expect(expense.amount_cents).toBe(8750);
    expect(expense.category_name).toBe("Alimentação");
    expect(expense.status).toBe("confirmed");
    expect(expense.occurred_at).toBe(today());

    const income = await createEntry(user, {
      kind: "income",
      amount: 3500,
      description: "Salário",
      category: "Salário",
    });

    expect(income.kind).toBe("income");
    expect(income.amount_cents).toBe(350000);
    expect(income.category_name).toBe("Salário");

    const audits = await testDb.db.query<{
      action: string;
      transaction_id: string;
      after_amount: string;
    }>(
      "select action, transaction_id, after->>'amount_cents' as after_amount from audit_log order by id",
    );

    expect(audits.rows.map((row) => row.action)).toEqual(["create", "create"]);
    expect(audits.rows[0].transaction_id).toBe(expense.id);
    expect(audits.rows[0].after_amount).toBe("8750");
  });

  it("lista, resume e filtra dados sem misturar usuários", async () => {
    const { user: alice } = await createUser();
    const { user: bob } = await createUser();

    await createEntry(alice, {
      amount: 100,
      description: "Mercado",
      category: "Alimentação",
    });
    await createEntry(alice, {
      amount: 50,
      description: "Uber",
      category: "Transporte",
    });
    await createEntry(alice, {
      kind: "income",
      amount: 2000,
      description: "Salário",
      category: "Salário",
    });
    await createEntry(bob, {
      amount: 999,
      description: "Item do Bob",
      category: "Alimentação",
    });

    const entries = await listTransactions(
      { userId: alice.id, from: monthStart(), to: today(), limit: 20 },
      env,
    );

    expect(entries).toHaveLength(3);
    expect(entries.map((entry) => entry.description)).not.toContain("Item do Bob");

    const summary = await getMonthlySummary(
      { userId: alice.id, from: monthStart(), to: today() },
      env,
    );

    expect(summary.totals).toEqual({
      expense_cents: 15000,
      income_cents: 200000,
      transaction_count: 3,
    });

    const byCategory = Object.fromEntries(
      summary.byCategory.map((row) => [row.category, row.total_cents]),
    );
    expect(byCategory["Alimentação"]).toBe(10000);
    expect(byCategory["Transporte"]).toBe(5000);

    const filtered = await getMonthlySummary(
      {
        userId: alice.id,
        from: monthStart(),
        to: today(),
        category: "Transporte",
      },
      env,
    );

    expect(filtered.totals.expense_cents).toBe(5000);
    expect(filtered.totals.transaction_count).toBe(1);

    const bobEntries = await listTransactions(
      { userId: bob.id, from: monthStart(), to: today() },
      env,
    );
    expect(bobEntries.map((entry) => entry.description)).toEqual(["Item do Bob"]);
  });

  it("isola updates e deletes por usuário e aplica soft delete", async () => {
    const { user: alice } = await createUser();
    const { user: bob } = await createUser();

    const expense = await createEntry(alice, {
      amount: 100,
      description: "Mercado",
    });

    const wrongUpdate = await updateTransaction(
      { userId: bob.id, id: expense.id, amount: 999 },
      env,
    );
    expect(wrongUpdate).toBeNull();

    const wrongDelete = await deleteTransaction(
      { userId: bob.id, id: expense.id },
      env,
    );
    expect(wrongDelete).toBeNull();

    const untouched = await testDb.db.query<{
      amount_cents: number;
      status: string;
    }>("select amount_cents, status from transactions where id = $1", [
      expense.id,
    ]);
    expect(untouched.rows[0]).toEqual({
      amount_cents: 10000,
      status: "confirmed",
    });

    const auditAfterFailures = await testDb.db.query<{ count: number }>(
      "select count(*)::int as count from audit_log where action in ('correct', 'delete')",
    );
    expect(auditAfterFailures.rows[0].count).toBe(0);

    const updated = await updateTransaction(
      {
        userId: alice.id,
        id: expense.id,
        amount: 90,
        description: "Mercado novo",
        categoryName: "Transporte",
        occurredAt: monthStart(),
      },
      env,
    );

    expect(updated?.amount_cents).toBe(9000);
    expect(updated?.description).toBe("Mercado novo");
    expect(updated?.category_name).toBe("Transporte");
    expect(updated?.status).toBe("corrected");

    const latestForAlice = await getLatestTransaction(alice.id, env);
    expect(latestForAlice?.id).toBe(expense.id);

    const deleted = await deleteTransaction(
      { userId: alice.id, id: expense.id },
      env,
    );

    expect(deleted?.status).toBe("deleted");

    const remaining = await listTransactions(
      { userId: alice.id, from: monthStart(), to: today() },
      env,
    );
    expect(remaining).toHaveLength(0);

    const latestAfterDelete = await getLatestTransaction(alice.id, env);
    expect(latestAfterDelete).toBeNull();
  });

  it("grava before/after na auditoria de correção e exclusão", async () => {
    const { user } = await createUser();
    const expense = await createEntry(user, {
      amount: 87.5,
      description: "Mercado",
      category: "Alimentação",
    });

    const updated = await updateTransaction(
      { userId: user.id, id: expense.id, amount: 90, description: "Mercado novo" },
      env,
    );
    expect(updated?.status).toBe("corrected");

    await deleteTransaction({ userId: user.id, id: expense.id }, env);

    const audits = await testDb.db.query<{
      action: string;
      before_amount: string | null;
      after_amount: string | null;
      after_status: string | null;
    }>(
      "select action, before->>'amount_cents' as before_amount, after->>'amount_cents' as after_amount, after->>'status' as after_status from audit_log where user_id = $1 order by id",
      [user.id],
    );

    expect(audits.rows.map((row) => row.action)).toEqual([
      "create",
      "correct",
      "delete",
    ]);
    expect(audits.rows[1].before_amount).toBe("8750");
    expect(audits.rows[1].after_amount).toBe("9000");
    expect(audits.rows[2].after_status).toBe("deleted");
  });
});

describe("fluxos do agente", () => {
  it("cria despesa e receita por texto com extração validada", async () => {
    const { user } = await createUser();

    mockGroq({
      intent: "create_expense",
      transaction: {
        amount: 87.5,
        description: "Mercado",
        category: "Alimentação",
      },
    });

    const expenseReply = await handleFinancialMessage({
      user,
      text: "mercado 87,50",
      source: "text",
      env,
    });

    expect(expenseReply).toContain("Gasto registrado: Mercado");

    mockGroq({
      intent: "create_income",
      transaction: {
        kind: "expense",
        amount: "3500",
        description: "Salário",
        category: "Salário",
        occurred_at: "2026-02-31",
      },
    });

    const incomeReply = await handleFinancialMessage({
      user,
      text: "recebi 3500 de salário",
      source: "text",
      env,
    });

    expect(incomeReply).toContain("Receita registrada: Salário");

    const rows = await testDb.db.query<{
      kind: string;
      amount_cents: number;
      occurred_at: string;
      category_name: string | null;
    }>(
      "select t.kind, t.amount_cents, to_char(t.occurred_at, 'YYYY-MM-DD') as occurred_at, c.name as category_name from transactions t left join categories c on c.id = t.category_id where t.user_id = $1 order by t.created_at",
      [user.id],
    );

    expect(rows.rows).toHaveLength(2);
    expect(rows.rows[0].kind).toBe("expense");
    expect(rows.rows[0].amount_cents).toBe(8750);
    expect(rows.rows[1].kind).toBe("income");
    expect(rows.rows[1].amount_cents).toBe(350000);
    expect(rows.rows[1].occurred_at).toBe(today());

    const audits = await testDb.db.query<{ count: number }>(
      "select count(*)::int as count from audit_log where action = 'create'",
    );
    expect(audits.rows[0].count).toBe(2);
  });

  it("não grava lançamento quando a extração é inválida", async () => {
    const { user } = await createUser();
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);
    mockGroq("não é json");

    const reply = await handleFinancialMessage({
      user,
      text: "mercado 87,50",
      source: "text",
      env,
    });

    expect(reply).toContain("Não consegui interpretar");
    expect(consoleError).toHaveBeenCalled();

    const rows = await testDb.db.query<{ count: number }>(
      "select count(*)::int as count from transactions",
    );
    expect(rows.rows[0].count).toBe(0);
  });

  it("responde consultas e relatórios com dados apenas do usuário", async () => {
    const { user: alice } = await createUser();
    const { user: bob } = await createUser();

    await createEntry(alice, {
      amount: 100,
      description: "Mercado",
      category: "Alimentação",
    });
    await createEntry(alice, {
      amount: 50,
      description: "Uber",
      category: "Transporte",
    });
    await createEntry(alice, {
      kind: "income",
      amount: 1000,
      description: "Freela",
      category: "Outras receitas",
    });
    await createEntry(bob, {
      amount: 999,
      description: "Item do Bob",
    });

    mockGroq({ intent: "query", query: { period: "current_month" } });

    const queryReply = await handleFinancialMessage({
      user: alice,
      text: "quanto gastei esse mês?",
      source: "text",
      env,
    });

    expect(queryReply).toContain("Mercado");
    expect(queryReply).toContain("Uber");
    expect(queryReply).not.toContain("Item do Bob");
    expect(queryReply).toContain("Saldo do período");

    mockGroq({ intent: "report", query: { period: "current_month" } });

    const reportReply = await handleFinancialMessage({
      user: alice,
      text: "relatório do mês",
      source: "text",
      env,
    });

    expect(reportReply).toContain("Relatório de");
    expect(reportReply).toContain("Receitas");
    expect(reportReply).toContain("Despesas");
    expect(reportReply).toContain("Alimentação");
    expect(reportReply).not.toContain("Item do Bob");
  });

  it("corrige e exclui o último lançamento via agente", async () => {
    const { user } = await createUser();
    const expense = await createEntry(user, {
      amount: 100,
      description: "Mercado",
    });

    mockGroq({
      intent: "correct",
      correction: { field: "amount", new_value: "90" },
    });

    const correctReply = await handleFinancialMessage({
      user,
      text: "corrige o último lançamento para 90",
      source: "text",
      env,
    });

    expect(correctReply).toContain("Corrigi");

    const corrected = await testDb.db.query<{
      amount_cents: number;
      status: string;
    }>("select amount_cents, status from transactions where id = $1", [
      expense.id,
    ]);
    expect(corrected.rows[0]).toEqual({
      amount_cents: 9000,
      status: "corrected",
    });

    mockGroq({ intent: "delete" });

    const deleteReply = await handleFinancialMessage({
      user,
      text: "apaga o último gasto",
      source: "text",
      env,
    });

    expect(deleteReply).toContain("Excluí");

    const deleted = await testDb.db.query<{ status: string }>(
      "select status from transactions where id = $1",
      [expense.id],
    );
    expect(deleted.rows[0].status).toBe("deleted");

    const audits = await testDb.db.query<{ action: string }>(
      "select action from audit_log where user_id = $1 order by id",
      [user.id],
    );
    expect(audits.rows.map((row) => row.action)).toEqual([
      "create",
      "correct",
      "delete",
    ]);
  });

  it("processa áudio até criar o lançamento e responder no Telegram", async () => {
    const { telegramId } = await createUser();
    let sentText = "";

    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);

        if (url.includes("/getFile")) {
          return jsonResponse({
            ok: true,
            result: {
              file_id: "audio-1",
              file_path: "voice/file_1.oga",
              file_size: 3,
            },
          });
        }

        if (url.includes("/file/bot")) {
          return new Response(new Uint8Array([1, 2, 3]), { status: 200 });
        }

        if (url.includes("/audio/transcriptions")) {
          return jsonResponse({ text: "mercado 87,50" });
        }

        if (url.includes("/chat/completions")) {
          return jsonResponse({
            choices: [
              {
                message: {
                  content: JSON.stringify({
                    intent: "create_expense",
                    transaction: {
                      amount: 87.5,
                      description: "Mercado",
                      category: "Alimentação",
                    },
                  }),
                },
              },
            ],
          });
        }

        if (url.includes("/sendMessage")) {
          const body = JSON.parse(String(init?.body ?? "{}")) as {
            text?: string;
          };
          sentText = body.text ?? "";
          return jsonResponse({ ok: true, result: { message_id: 1 } });
        }

        throw new Error(`URL inesperada no teste: ${url}`);
      },
    );

    vi.stubGlobal("fetch", fetchMock);

    await handleTelegramUpdate(
      {
        update_id: 1,
        message: {
          message_id: 1,
          from: { id: telegramId, first_name: "Teste" },
          chat: { id: 12345, type: "private" },
          date: Math.floor(Date.now() / 1000),
          voice: {
            file_id: "audio-1",
            file_unique_id: "audio-1",
            mime_type: "audio/ogg",
            file_size: 3,
          },
        },
      },
      env,
    );

    expect(sentText).toContain("Gasto registrado: Mercado");
    expect(
      fetchMock.mock.calls.some(([url]) =>
        String(url).includes("/audio/transcriptions"),
      ),
    ).toBe(true);

    const rows = await testDb.db.query<{
      source: string;
      description: string;
      amount_cents: number;
    }>("select source, description, amount_cents from transactions where user_id = (select id from users where telegram_id = $1)", [
      String(telegramId),
    ]);

    expect(rows.rows).toHaveLength(1);
    expect(rows.rows[0]).toEqual({
      source: "audio",
      description: "Mercado",
      amount_cents: 8750,
    });
  });
});
