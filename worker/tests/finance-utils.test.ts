import { describe, expect, it } from "vitest";
import {
  normaliseCategory,
  parseAmount,
  parseDate,
  resolvePeriod,
  sanitiseExtraction,
  todayInTimezone,
} from "../src/ai";

describe("parseAmount", () => {
  it("interpreta números e formatos brasileiros", () => {
    expect(parseAmount(87.5)).toBe(87.5);
    expect(parseAmount("87,50")).toBe(87.5);
    expect(parseAmount("R$ 1.200,50")).toBe(1200.5);
    expect(parseAmount("1.200")).toBe(1200);
    expect(parseAmount("90 reais")).toBe(90);
  });

  it("rejeita valores inválidos", () => {
    expect(parseAmount("")).toBeNull();
    expect(parseAmount("abc")).toBeNull();
    expect(parseAmount(null)).toBeNull();
    expect(parseAmount(Number.NaN)).toBeNull();
    expect(parseAmount(Number.POSITIVE_INFINITY)).toBeNull();
  });
});

describe("parseDate", () => {
  it("aceita apenas datas ISO válidas", () => {
    expect(parseDate("2026-10-31")).toBe("2026-10-31");
    expect(parseDate("2024-02-29")).toBe("2024-02-29");
    expect(parseDate("2026-02-29")).toBeNull();
    expect(parseDate("2026-13-01")).toBeNull();
    expect(parseDate("31/10/2026")).toBeNull();
    expect(parseDate(undefined)).toBeNull();
  });
});

describe("normaliseCategory", () => {
  it("normaliza nomes válidos sem diferenciar maiúsculas", () => {
    expect(normaliseCategory("alimentação")).toBe("Alimentação");
    expect(normaliseCategory("SALÁRIO")).toBe("Salário");
    expect(normaliseCategory(" outras receitas ")).toBe("Outras receitas");
  });

  it("descarta categorias fora da lista", () => {
    expect(normaliseCategory("Categoria Inventada")).toBeUndefined();
    expect(normaliseCategory(undefined)).toBeUndefined();
  });
});

describe("resolvePeriod", () => {
  const today = "2026-10-31";

  it("resolve os períodos suportados", () => {
    expect(resolvePeriod("today", today)).toEqual({ from: today, to: today });
    expect(resolvePeriod("yesterday", today)).toEqual({
      from: "2026-10-30",
      to: "2026-10-30",
    });
    expect(resolvePeriod("current_month", today)).toEqual({
      from: "2026-10-01",
      to: today,
    });
    expect(resolvePeriod("last_month", today)).toEqual({
      from: "2026-09-01",
      to: "2026-09-30",
    });
    expect(resolvePeriod("this_year", today)).toEqual({
      from: "2026-01-01",
      to: today,
    });
  });

  it("usa o mês atual como padrão", () => {
    expect(resolvePeriod(undefined, today)).toEqual({
      from: "2026-10-01",
      to: today,
    });
    expect(resolvePeriod("periodo_invalido", today)).toEqual({
      from: "2026-10-01",
      to: today,
    });
  });
});

describe("sanitiseExtraction", () => {
  const today = "2026-10-31";

  it("remove cercas markdown e texto ao redor do JSON", () => {
    const raw = [
      "Segue o resultado:",
      "```json",
      JSON.stringify({
        intent: "create_expense",
        transaction: {
          amount: "87,50",
          description: " Mercado ",
          category: "alimentação",
          occurred_at: "2026-02-31",
        },
        confidence: 1.4,
      }),
      "```",
    ].join("\n");

    const result = sanitiseExtraction(raw, today);

    expect(result.intent).toBe("create_expense");
    expect(result.transaction?.amount).toBe(87.5);
    expect(result.transaction?.description).toBe("Mercado");
    expect(result.transaction?.category).toBe("Alimentação");
    expect(result.transaction?.occurred_at).toBe(today);
    expect(result.confidence).toBe(1);
  });

  it("rebaixa intenções desconhecidas para unknown", () => {
    const result = sanitiseExtraction(
      JSON.stringify({ intent: "executar_comando", reply_if_unclear: "Repita" }),
      today,
    );

    expect(result.intent).toBe("unknown");
    expect(result.reply_if_unclear).toBe("Repita");
  });

  it("descarta categorias e campos de correção inválidos", () => {
    const result = sanitiseExtraction(
      JSON.stringify({
        intent: "correct",
        transaction: {
          amount: 10,
          description: "Teste",
          category: "Inventada",
        },
        correction: {
          field: "campo_invalido",
          new_value: "x",
        },
        query: {
          period: "sempre",
          category: "Inventada",
        },
      }),
      today,
    );

    expect(result.transaction?.category).toBeUndefined();
    expect(result.correction?.field).toBeUndefined();
    expect(result.query?.period).toBeUndefined();
    expect(result.query?.category).toBeUndefined();
  });

  it("trunca respostas longas de esclarecimento", () => {
    const result = sanitiseExtraction(
      JSON.stringify({ intent: "unknown", reply_if_unclear: "a".repeat(500) }),
      today,
    );

    expect(result.reply_if_unclear).toHaveLength(300);
  });

  it("rejeita respostas sem JSON válido", () => {
    expect(() => sanitiseExtraction("não é json", today)).toThrow();
    expect(() => sanitiseExtraction("{ quebrado", today)).toThrow();
  });
});

describe("todayInTimezone", () => {
  it("retorna uma data ISO", () => {
    expect(todayInTimezone("America/Recife")).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(todayInTimezone("UTC")).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });
});
