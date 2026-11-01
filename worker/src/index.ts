import { handleTelegramUpdate, type TelegramUpdate } from "./telegram";

export interface Env {
  TELEGRAM_BOT_TOKEN: string;
  TELEGRAM_WEBHOOK_SECRET: string;
  DATABASE_URL: string;
  GROQ_API_KEY: string;
  GROQ_MODEL?: string;
  GROQ_TRANSCRIPTION_MODEL?: string;
}

async function safeEqual(left: string, right: string): Promise<boolean> {
  const encoder = new TextEncoder();
  const [leftDigest, rightDigest] = await Promise.all([
    crypto.subtle.digest("SHA-256", encoder.encode(left)),
    crypto.subtle.digest("SHA-256", encoder.encode(right)),
  ]);

  const leftBytes = new Uint8Array(leftDigest);
  const rightBytes = new Uint8Array(rightDigest);
  let difference = leftBytes.length ^ rightBytes.length;

  for (let index = 0; index < leftBytes.length; index += 1) {
    difference |= leftBytes[index] ^ rightBytes[index];
  }

  return difference === 0;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const { pathname } = new URL(request.url);

    if (request.method === "GET" && pathname === "/health") {
      return Response.json({
        ok: true,
        service: "assistente-financeiro",
        timestamp: new Date().toISOString(),
      });
    }

    if (request.method === "POST" && pathname === "/telegram/webhook") {
      const secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token");

      if (!secret || !env.TELEGRAM_WEBHOOK_SECRET || !(await safeEqual(secret, env.TELEGRAM_WEBHOOK_SECRET))) {
        return new Response("unauthorized", { status: 401 });
      }

      let update: TelegramUpdate;

      try {
        update = await request.json<TelegramUpdate>();
      } catch {
        return Response.json({ ok: false, error: "invalid json" }, { status: 400 });
      }

      if (!update || typeof update.update_id !== "number") {
        return Response.json({ ok: false, error: "invalid update" }, { status: 400 });
      }

      ctx.waitUntil(handleTelegramUpdate(update, env));

      return new Response("ok");
    }

    return new Response("not found", { status: 404 });
  },
} satisfies ExportedHandler<Env>;
