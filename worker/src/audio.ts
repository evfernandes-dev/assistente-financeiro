import type { Env } from "./index";

export interface TelegramAudioFileInput {
  file_id: string;
  mime_type?: string;
  file_size?: number;
}

export interface TelegramAudio {
  data: ArrayBuffer;
  mimeType: string;
  fileName: string;
}

interface TelegramFileInfo {
  ok: boolean;
  result: {
    file_id: string;
    file_path: string;
    file_size?: number;
  };
}

export const MAX_TELEGRAM_AUDIO_BYTES = 20 * 1024 * 1024;

export async function downloadTelegramAudio(
  file: TelegramAudioFileInput,
  env: Env,
): Promise<TelegramAudio> {
  if (file.file_size && file.file_size > MAX_TELEGRAM_AUDIO_BYTES) {
    throw new Error("Áudio acima do limite de 20 MB do Telegram");
  }

  const infoResponse = await fetch(
    `https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/getFile?file_id=${encodeURIComponent(file.file_id)}`,
  );

  if (!infoResponse.ok) {
    throw new Error(`Falha ao obter arquivo do Telegram: ${infoResponse.status}`);
  }

  const info = (await infoResponse.json()) as TelegramFileInfo;

  if (!info.ok || !info.result.file_path) {
    throw new Error("Telegram não retornou o caminho do arquivo");
  }

  if (info.result.file_size && info.result.file_size > MAX_TELEGRAM_AUDIO_BYTES) {
    throw new Error("Áudio acima do limite de 20 MB do Telegram");
  }

  const fileResponse = await fetch(
    `https://api.telegram.org/file/bot${env.TELEGRAM_BOT_TOKEN}/${info.result.file_path}`,
  );

  if (!fileResponse.ok) {
    throw new Error(`Falha ao baixar áudio do Telegram: ${fileResponse.status}`);
  }

  const extensionMatch = info.result.file_path.match(/\.([a-z0-9]+)$/i);
  const rawExtension = extensionMatch?.[1]?.toLowerCase() ?? "ogg";
  const extension = rawExtension === "oga" ? "ogg" : rawExtension;
  const mimeType = file.mime_type === "audio/oga" ? "audio/ogg" : file.mime_type ?? "audio/ogg";

  return {
    data: await fileResponse.arrayBuffer(),
    mimeType,
    fileName: `audio.${extension}`,
  };
}
