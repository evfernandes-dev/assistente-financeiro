import { describe, expect, it, vi } from "vitest";
import type { Env } from "../src/index";

vi.mock("../src/telegram", () => ({
  handleTelegramUpdate: vi.fn(async () => undefined),
}));

import worker from "../src/index";
import { handleTelegramUpdate } from "../src/telegram";

const env: Env = {
  TELEGRAM_BOT_TOKEN: "test-token",
  TELEGRAM_WEBHOOK_SECRET: "test-secret",
  DATABASE_URL: "postgresql://test:test@localhost/test",
  GROQ_API_KEY: "test-groq-key",
  GROQ_MODEL: "test-model",
  GROQ_TRANSCRIPTION_MODEL: "test-whisper",
};

const handler = worker as unknown as {
  fetch: (
    request: Request,
    env: Env,
    ctx: ExecutionContext,
  ) => Promise<Response>;
};

function createContext(): ExecutionContext {
  return {
    waitUntil: vi.fn(),
    passThroughOnException: vi.fn(),
  } as unknown as ExecutionContext;
}

function webhookRequest(
  body: string,
  secret?: string,
): Request {
  const headers = new Headers({ "content-type": "application/json" });

  if (secret) {
    headers.set("X-Telegram-Bot-Api-Secret-Token", secret);
  }

  return new Request("https://worker.test/telegram/webhook", {
    method: "POST",
    headers,
    body,
  });
}

describe("worker HTTP", () => {
  it("responde ao health check", async () => {
    const response = await handler.fetch(
      new Request("https://worker.test/health"),
      env,
      createContext(),
    );

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toMatchObject({
      ok: true,
      service: "assistente-financeiro",
    });
  });

  it("rejeita webhook sem segredo", async () => {
    const response = await handler.fetch(
      webhookRequest(JSON.stringify({ update_id: 1 })),
      env,
      createContext(),
    );

    expect(response.status).toBe(401);
  });

  it("rejeita webhook com segredo incorreto", async () => {
    const response = await handler.fetch(
      webhookRequest(JSON.stringify({ update_id: 1 }), "segredo-errado"),
      env,
      createContext(),
    );

    expect(response.status).toBe(401);
  });

  it("rejeita JSON inválido", async () => {
    const response = await handler.fetch(
      webhookRequest("{", "test-secret"),
      env,
      createContext(),
    );

    expect(response.status).toBe(400);
  });

  it("rejeita update sem update_id", async () => {
    const response = await handler.fetch(
      webhookRequest("{}", "test-secret"),
      env,
      createContext(),
    );

    expect(response.status).toBe(400);
  });

  it("enfileira o update válido e responde ok", async () => {
    const ctx = createContext();
    const response = await handler.fetch(
      webhookRequest(JSON.stringify({ update_id: 7 }), "test-secret"),
      env,
      ctx,
    );

    expect(response.status).toBe(200);
    await expect(response.text()).resolves.toBe("ok");
    expect(ctx.waitUntil).toHaveBeenCalledTimes(1);
    expect(handleTelegramUpdate).toHaveBeenCalledWith({ update_id: 7 }, env);
  });
});
