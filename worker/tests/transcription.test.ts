import { describe, expect, it, vi } from "vitest";
import type { Env } from "../src/index";
import { transcribeAudio } from "../src/transcription";

const env: Env = {
  TELEGRAM_BOT_TOKEN: "test-token",
  TELEGRAM_WEBHOOK_SECRET: "test-secret",
  DATABASE_URL: "postgresql://test:test@localhost/test",
  GROQ_API_KEY: "test-groq-key",
  GROQ_MODEL: "test-model",
  GROQ_TRANSCRIPTION_MODEL: "test-whisper",
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("transcribeAudio", () => {
  it("envia o arquivo correto e devolve o texto", async () => {
    const fetchMock = vi.fn(async () => jsonResponse({ text: "  mercado 87,50  " }));
    vi.stubGlobal("fetch", fetchMock);

    const text = await transcribeAudio(
      {
        data: new Uint8Array([1, 2, 3]).buffer,
        mimeType: "audio/ogg",
        fileName: "audio.oga",
      },
      env,
    );

    expect(text).toBe("mercado 87,50");
    expect(fetchMock).toHaveBeenCalledTimes(1);

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];

    expect(url).toBe("https://api.groq.com/openai/v1/audio/transcriptions");
    expect(new Headers(init.headers).get("authorization")).toBe("Bearer test-groq-key");

    const form = init.body as FormData;
    const file = form.get("file") as File;

    expect(form.get("model")).toBe("test-whisper");
    expect(form.get("language")).toBe("pt");
    expect(file.name).toBe("audio.ogg");
    expect(file.type).toBe("audio/ogg");
  });

  it("rejeita transcrição vazia", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse({ text: "   " })));

    await expect(
      transcribeAudio({ data: new Uint8Array([1]).buffer }, env),
    ).rejects.toThrow("Transcrição vazia");
  });

  it("rejeita resposta sem texto", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse({})));

    await expect(
      transcribeAudio({ data: new Uint8Array([1]).buffer }, env),
    ).rejects.toThrow("Transcrição vazia");
  });

  it("propaga erro HTTP da Groq", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("indisponível", { status: 503 })),
    );

    await expect(
      transcribeAudio({ data: new Uint8Array([1]).buffer }, env),
    ).rejects.toThrow(/503/);
  });

  it("bloqueia áudio acima de 25 MB sem chamar a API", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      transcribeAudio({ data: new ArrayBuffer(25 * 1024 * 1024 + 1) }, env),
    ).rejects.toThrow("25 MB");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("bloqueia áudio vazio", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      transcribeAudio({ data: new ArrayBuffer(0) }, env),
    ).rejects.toThrow("Áudio vazio");
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
