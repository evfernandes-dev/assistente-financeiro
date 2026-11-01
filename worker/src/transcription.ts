import type { Env } from "./index";

export interface AudioInput {
  data: ArrayBuffer;
  mimeType?: string;
  fileName?: string;
}

interface GroqTranscriptionResponse {
  text?: string;
}

const MAX_AUDIO_BYTES = 25 * 1024 * 1024;
const GROQ_TIMEOUT_MS = 60_000;

export async function transcribeAudio(audio: AudioInput, env: Env): Promise<string> {
  if (audio.data.byteLength === 0) {
    throw new Error("Áudio vazio");
  }

  if (audio.data.byteLength > MAX_AUDIO_BYTES) {
    throw new Error("Áudio acima do limite de 25 MB");
  }

  const form = new FormData();
  const mimeType = (audio.mimeType ?? "audio/ogg").replace(/^audio\/oga$/i, "audio/ogg");
  const fileName = (audio.fileName ?? "audio.ogg").replace(/\.oga$/i, ".ogg");

  form.append(
    "file",
    new Blob([audio.data], { type: mimeType }),
    fileName,
  );
  form.append("model", env.GROQ_TRANSCRIPTION_MODEL ?? "whisper-large-v3-turbo");
  form.append("language", "pt");
  form.append("response_format", "json");
  form.append("temperature", "0");

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), GROQ_TIMEOUT_MS);

  try {
    const response = await fetch("https://api.groq.com/openai/v1/audio/transcriptions", {
      method: "POST",
      headers: {
        authorization: `Bearer ${env.GROQ_API_KEY}`,
      },
      body: form,
      signal: controller.signal,
    });

    if (!response.ok) {
      const detail = (await response.text()).slice(0, 300);
      throw new Error(`Transcrição Groq falhou: ${response.status} ${detail}`);
    }

    const data = (await response.json()) as GroqTranscriptionResponse;

    if (typeof data.text !== "string" || !data.text.trim()) {
      throw new Error("Transcrição vazia");
    }

    return data.text.trim();
  } finally {
    clearTimeout(timeout);
  }
}
