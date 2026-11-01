import type { Env } from "./index";
import { handleFinancialMessage } from "./ai";
import { downloadTelegramAudio, MAX_TELEGRAM_AUDIO_BYTES } from "./audio";
import { ensureUser } from "./expenses";
import { transcribeAudio } from "./transcription";

export interface TelegramFile {
  file_id: string;
  file_unique_id: string;
  duration?: number;
  mime_type?: string;
  file_size?: number;
}

export interface TelegramMessage {
  message_id: number;
  from?: {
    id: number;
    first_name?: string;
    username?: string;
    language_code?: string;
  };
  chat: {
    id: number;
    type: string;
  };
  date: number;
  text?: string;
  voice?: TelegramFile;
  audio?: TelegramFile;
}

export interface TelegramUpdate {
  update_id: number;
  message?: TelegramMessage;
}

interface TelegramApiResponse<T> {
  ok: boolean;
  result: T;
  description?: string;
}

export async function callTelegramApi<T>(
  method: string,
  payload: Record<string, unknown>,
  env: Env,
): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15_000);

  try {
    const response = await fetch(
      `https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/${method}`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(payload),
        signal: controller.signal,
      },
    );

    const data = (await response.json()) as TelegramApiResponse<T>;

    if (!response.ok || !data.ok) {
      throw new Error(`Telegram ${method} falhou: ${data.description ?? response.status}`);
    }

    return data.result;
  } finally {
    clearTimeout(timeout);
  }
}

export async function sendMessage(env: Env, chatId: number, text: string): Promise<void> {
  const chunks = splitMessage(text, 4000);

  for (const chunk of chunks) {
    try {
      await callTelegramApi(
        "sendMessage",
        {
          chat_id: chatId,
          text: chunk,
          parse_mode: "Markdown",
          disable_web_page_preview: true,
        },
        env,
      );
    } catch {
      await callTelegramApi(
        "sendMessage",
        {
          chat_id: chatId,
          text: chunk,
          disable_web_page_preview: true,
        },
        env,
      );
    }
  }
}

function splitMessage(text: string, maxLength: number): string[] {
  if (text.length <= maxLength) {
    return [text];
  }

  const chunks: string[] = [];
  let current = "";

  for (const line of text.split("\n")) {
    if ((current + line).length > maxLength) {
      if (current) {
        chunks.push(current);
      }
      current = line;
    } else {
      current = current ? `${current}\n${line}` : line;
    }
  }

  if (current) {
    chunks.push(current);
  }

  return chunks;
}

export async function handleTelegramUpdate(update: TelegramUpdate, env: Env): Promise<void> {
  const message = update.message;

  if (!message || message.chat.type !== "private") {
    return;
  }

  const chatId = message.chat.id;

  try {
    let text = message.text?.trim() ?? "";
    let source: "text" | "audio" = "text";

    const audioFile = message.voice ?? message.audio;

    if (!text && audioFile) {
      if (audioFile.file_size && audioFile.file_size > MAX_TELEGRAM_AUDIO_BYTES) {
        await sendMessage(env, chatId, "⚠️ Áudio muito grande. Envie um áudio de até 20 MB.");
        return;
      }

      const audio = await downloadTelegramAudio(audioFile, env);
      text = await transcribeAudio(audio, env);
      source = "audio";
    }

    if (!text) {
      await sendMessage(
        env,
        chatId,
        "🎤 Envie um texto ou um áudio para eu registrar ou consultar seus gastos.",
      );
      return;
    }

    const user = await ensureUser(message.from, env);
    const reply = await handleFinancialMessage({ user, text, source, env });
    await sendMessage(env, chatId, reply);
  } catch (error) {
    console.error("handleTelegramUpdate", error);
    await sendMessage(
      env,
      chatId,
      "⚠️ Não consegui processar sua mensagem agora. Tente novamente em instantes.",
    );
  }
}
