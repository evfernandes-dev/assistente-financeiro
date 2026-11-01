import type { Env } from "./index";
import expenseExtractionPrompt from "../../prompts/expense-extraction.md";
import financialAgentPrompt from "../../prompts/financial-agent.md";
import {
  CATEGORY_NAMES,
  createTransaction,
  deleteTransaction,
  getLatestTransaction,
  getMonthlySummary,
  listTransactions,
  updateTransaction,
  type User,
} from "./expenses";
import { brl, formatConfirmation, formatMonthlyReport, formatTransactionList } from "./reports";

interface ChatMessage {
  role: "system" | "user" | "assistant";
  content: string;
}

interface GroqChatResponse {
  choices: Array<{
    message: {
      content: string;
    };
  }>;
}

export type Intent =
  | "create_expense"
  | "create_income"
  | "query"
  | "report"
  | "correct"
  | "delete"
  | "unknown";

type CorrectionField = "amount" | "description" | "category" | "date";

interface ExtractionResult {
  intent: Intent;
  transaction?: {
    kind?: "expense" | "income";
    amount?: number;
    description?: string;
    category?: string;
    occurred_at?: string;
  };
  correction?: {
    reference?: string;
    field?: CorrectionField;
    new_value?: string;
  };
  query?: {
    period?: string;
    category?: string;
  };
  confidence?: number;
  missing?: string[];
  reply_if_unclear?: string;
}

const VALID_INTENTS = new Set<Intent>([
  "create_expense",
  "create_income",
  "query",
  "report",
  "correct",
  "delete",
  "unknown",
]);

const VALID_PERIODS = new Set(["today", "yesterday", "current_month", "last_month", "this_year"]);
const VALID_CORRECTION_FIELDS = new Set<CorrectionField>(["amount", "description", "category", "date"]);
const MAX_TEXT_LENGTH = 4000;
const MAX_DESCRIPTION_LENGTH = 200;
const MAX_AMOUNT = 20_000_000;
const GROQ_TIMEOUT_MS = 25_000;

function asRecord(value: unknown): Record<string, unknown> | undefined {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : undefined;
}

function stringValue(value: unknown, maxLength: number): string | undefined {
  return typeof value === "string" && value.trim()
    ? value.trim().slice(0, maxLength)
    : undefined;
}

export function parseAmount(value: unknown): number | null {
  if (typeof value === "number") {
    return Number.isFinite(value) ? value : null;
  }

  if (typeof value !== "string") {
    return null;
  }

  const cleaned = value
    .replace(/[^\d,.]/g, "")
    .replace(/\.(?=\d{3}(?:\D|$))/g, "")
    .replace(",", ".");

  if (!cleaned) {
    return null;
  }

  const parsed = Number(cleaned);
  return Number.isFinite(parsed) ? parsed : null;
}

export function parseDate(value: unknown): string | null {
  if (typeof value !== "string") {
    return null;
  }

  const trimmed = value.trim();

  if (!/^\d{4}-\d{2}-\d{2}$/.test(trimmed)) {
    return null;
  }

  const parsed = new Date(`${trimmed}T00:00:00Z`);

  if (Number.isNaN(parsed.getTime())) {
    return null;
  }

  return parsed.toISOString().slice(0, 10) === trimmed ? trimmed : null;
}

function normaliseDate(value: unknown, fallback: string): string {
  return parseDate(value) ?? fallback;
}

export function normaliseCategory(value: unknown): string | undefined {
  if (typeof value !== "string") {
    return undefined;
  }

  const target = value.trim().toLowerCase();
  return CATEGORY_NAMES.find((name) => name.toLowerCase() === target);
}

export function todayInTimezone(timezone: string): string {
  return new Intl.DateTimeFormat("sv-SE", {
    timeZone: timezone,
    dateStyle: "short",
  }).format(new Date());
}

export function resolvePeriod(period: string | undefined, today: string): { from: string; to: string } {
  const [year, month, day] = today.split("-").map(Number);

  switch (period) {
    case "today":
      return { from: today, to: today };

    case "yesterday": {
      const iso = new Date(Date.UTC(year, month - 1, day - 1)).toISOString().slice(0, 10);
      return { from: iso, to: iso };
    }

    case "last_month": {
      const from = new Date(Date.UTC(year, month - 2, 1)).toISOString().slice(0, 10);
      const to = new Date(Date.UTC(year, month - 1, 0)).toISOString().slice(0, 10);
      return { from, to };
    }

    case "this_year":
      return { from: `${year}-01-01`, to: today };

    default:
      return { from: `${today.slice(0, 7)}-01`, to: today };
  }
}

async function groqChat(messages: ChatMessage[], env: Env, jsonMode = false): Promise<string> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), GROQ_TIMEOUT_MS);

  try {
    const response = await fetch("https://api.groq.com/openai/v1/chat/completions", {
      method: "POST",
      headers: {
        authorization: `Bearer ${env.GROQ_API_KEY}`,
        "content-type": "application/json",
      },
      body: JSON.stringify({
        model: env.GROQ_MODEL ?? "qwen/qwen3.8-27b",
        temperature: 0.2,
        max_tokens: 800,
        messages,
        ...(jsonMode ? { response_format: { type: "json_object" } } : {}),
      }),
      signal: controller.signal,
    });

    if (!response.ok) {
      const detail = (await response.text()).slice(0, 300);
      throw new Error(`Groq chat falhou: ${response.status} ${detail}`);
    }

    const data = (await response.json()) as GroqChatResponse;
    const content = data.choices?.[0]?.message?.content;

    if (typeof content !== "string" || !content.trim()) {
      throw new Error("Groq retornou resposta vazia");
    }

    return content.trim();
  } finally {
    clearTimeout(timeout);
  }
}

export function sanitiseExtraction(raw: string, today: string): ExtractionResult {
  const withoutFence = raw.replace(/^```(?:json)?/i, "").replace(/```$/, "").trim();
  const start = withoutFence.indexOf("{");
  const end = withoutFence.lastIndexOf("}");

  if (start === -1 || end === -1 || end <= start) {
    throw new Error("Resposta da IA sem JSON");
  }

  const parsed = JSON.parse(withoutFence.slice(start, end + 1)) as Record<string, unknown>;
  const intentValue = typeof parsed.intent === "string" ? parsed.intent.trim().toLowerCase() : "";
  const intent = VALID_INTENTS.has(intentValue as Intent) ? (intentValue as Intent) : "unknown";

  const result: ExtractionResult = {
    intent,
    reply_if_unclear: stringValue(parsed.reply_if_unclear, 300),
  };

  const transaction = asRecord(parsed.transaction);

  if (transaction) {
    result.transaction = {
      kind: transaction.kind === "income" ? "income" : "expense",
      amount: parseAmount(transaction.amount) ?? undefined,
      description: stringValue(transaction.description, MAX_DESCRIPTION_LENGTH),
      category: normaliseCategory(transaction.category),
      occurred_at: normaliseDate(transaction.occurred_at, today),
    };
  }

  const correction = asRecord(parsed.correction);

  if (correction) {
    const fieldValue =
      typeof correction.field === "string" ? correction.field.trim().toLowerCase() : "";

    result.correction = {
      reference: stringValue(correction.reference, 60),
      field: VALID_CORRECTION_FIELDS.has(fieldValue as CorrectionField)
        ? (fieldValue as CorrectionField)
        : undefined,
      new_value: stringValue(correction.new_value, MAX_DESCRIPTION_LENGTH),
    };
  }

  const query = asRecord(parsed.query);

  if (query) {
    const periodValue = typeof query.period === "string" ? query.period.trim().toLowerCase() : "";

    result.query = {
      period: VALID_PERIODS.has(periodValue) ? periodValue : undefined,
      category: normaliseCategory(query.category),
    };
  }

  if (typeof parsed.confidence === "number" && Number.isFinite(parsed.confidence)) {
    result.confidence = Math.min(Math.max(parsed.confidence, 0), 1);
  }

  if (Array.isArray(parsed.missing)) {
    result.missing = parsed.missing
      .filter((item): item is string => typeof item === "string")
      .slice(0, 5)
      .map((item) => item.slice(0, 120));
  }

  return result;
}

async function extractIntent(text: string, user: User, env: Env): Promise<ExtractionResult> {
  const today = todayInTimezone(user.timezone);
  const content = [
    expenseExtractionPrompt,
    "",
    `Data atual: ${today}`,
    `Moeda: ${user.currency}`,
    "",
    `Mensagem do usuário: """${text}"""`,
  ].join("\n");

  const raw = await groqChat(
    [
      { role: "system", content: financialAgentPrompt },
      { role: "user", content },
    ],
    env,
    true,
  );

  return sanitiseExtraction(raw, today);
}

export async function handleFinancialMessage(input: {
  user: User;
  text: string;
  source: "text" | "audio";
  env: Env;
}): Promise<string> {
  const { user, source, env } = input;
  const text = input.text.trim().slice(0, MAX_TEXT_LENGTH);
  const today = todayInTimezone(user.timezone);

  let extraction: ExtractionResult;

  try {
    extraction = await extractIntent(text, user, env);
  } catch (error) {
    console.error("extractIntent", error);
    return "Não consegui interpretar sua mensagem agora. Tente novamente em instantes.";
  }

  switch (extraction.intent) {
    case "create_expense":
    case "create_income": {
      const transaction = extraction.transaction;
      const amount = parseAmount(transaction?.amount);
      const description = transaction?.description?.trim();

      if (!transaction || !description || amount === null || amount <= 0 || amount > MAX_AMOUNT) {
        return (
          extraction.reply_if_unclear ??
          "Não entendi o valor ou a descrição. Pode repetir? Exemplo: mercado 87,50."
        );
      }

      const created = await createTransaction(
        {
          userId: user.id,
          kind: extraction.intent === "create_income" ? "income" : "expense",
          amount,
          description,
          category: transaction.category,
          occurredAt: normaliseDate(transaction.occurred_at, today),
          source,
          rawText: text,
        },
        env,
      );

      return formatConfirmation(created);
    }

    case "query": {
      const { from, to } = resolvePeriod(extraction.query?.period, today);
      const category = extraction.query?.category;

      const [transactions, summary] = await Promise.all([
        listTransactions({ userId: user.id, from, to, limit: 20, category }, env),
        getMonthlySummary({ userId: user.id, from, to, category }, env),
      ]);

      const balance = summary.totals.income_cents - summary.totals.expense_cents;
      return formatTransactionList(transactions, from, to, balance);
    }

    case "report": {
      const { from, to } = resolvePeriod(extraction.query?.period ?? "current_month", today);
      const summary = await getMonthlySummary(
        { userId: user.id, from, to, category: extraction.query?.category },
        env,
      );

      return formatMonthlyReport(summary.totals, summary.byCategory, from, to);
    }

    case "correct": {
      const latest = await getLatestTransaction(user.id, env);

      if (!latest) {
        return "Não encontrei nenhum lançamento para corrigir.";
      }

      const field = extraction.correction?.field;
      const newValue = extraction.correction?.new_value;
      const transaction = extraction.transaction;
      const changes: {
        amount?: number;
        description?: string;
        categoryName?: string;
        occurredAt?: string;
      } = {};

      const amount = field === "amount" ? parseAmount(newValue) : parseAmount(transaction?.amount);

      if (amount !== null && amount > 0 && amount <= MAX_AMOUNT) {
        changes.amount = amount;
      }

      if (field === "description" && newValue) {
        changes.description = newValue;
      } else if (transaction?.description) {
        changes.description = transaction.description;
      }

      if (field === "category") {
        const category = normaliseCategory(newValue);

        if (category) {
          changes.categoryName = category;
        }
      } else if (transaction?.category) {
        changes.categoryName = transaction.category;
      }

      if (field === "date" && newValue) {
        const date = parseDate(newValue);

        if (date) {
          changes.occurredAt = date;
        }
      }

      if (Object.keys(changes).length === 0) {
        return "Não entendi o que devo corrigir. Diga o campo e o novo valor.";
      }

      const updated = await updateTransaction(
        {
          userId: user.id,
          id: latest.id,
          ...changes,
        },
        env,
      );

      if (!updated) {
        return "Não encontrei esse lançamento para corrigir.";
      }

      return `Corrigi o lançamento: ${updated.description} — ${brl(updated.amount_cents)}.`;
    }

    case "delete": {
      const latest = await getLatestTransaction(user.id, env);

      if (!latest) {
        return "Não encontrei nenhum lançamento para excluir.";
      }

      const deleted = await deleteTransaction({ userId: user.id, id: latest.id }, env);

      if (!deleted) {
        return "Não encontrei esse lançamento para excluir.";
      }

      return `Excluí o lançamento: ${deleted.description} — ${brl(deleted.amount_cents)}.`;
    }

    default:
      return (
        extraction.reply_if_unclear ??
        'Não entendi. Você pode registrar ("mercado 87,50"), consultar ("gastos de hoje") ou pedir um relatório ("relatório do mês").'
      );
  }
}
