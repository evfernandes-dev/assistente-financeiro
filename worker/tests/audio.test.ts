import { describe, expect, it, vi } from "vitest";
import type { Env } from "../src/index";
import { downloadTelegramAudio, MAX_TELEGRAM_AUDIO_BYTES } from "../src/audio";

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

describe("downloadTelegramAudio", () => {
  it("obtém metadados e baixa o áudio", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse({
          ok: true,
          result: {
            file_id: "audio-1",
            file_path: "voice/file_1.oga",
            file_size: 3,
          },
        }),
      )
      .mockResolvedValueOnce(
        new Response(new Uint8Array([1, 2, 3]), { status: 200 }),
      );
    vi.stubGlobal("fetch", fetchMock);

    const audio = await downloadTelegramAudio(
      { file_id: "audio-1", mime_type: "audio/ogg", file_size: 3 },
      env,
    );

    expect(audio.data.byteLength).toBe(3);
    expect(audio.fileName).toBe("audio.ogg");
    expect(audio.mimeType).toBe("audio/ogg");
    expect(String(fetchMock.mock.calls[0][0])).toContain("/getFile?file_id=audio-1");
    expect(String(fetchMock.mock.calls[1][0])).toContain("/file/bot");
    expect(String(fetchMock.mock.calls[1][0])).toContain("voice/file_1.oga");
  });

  it("bloqueia áudio acima de 20 MB antes de baixar", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      downloadTelegramAudio(
        {
          file_id: "audio-1",
          file_size: MAX_TELEGRAM_AUDIO_BYTES + 1,
        },
        env,
      ),
    ).rejects.toThrow("20 MB");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("propaga erro ao obter metadados", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("erro", { status: 500 })),
    );

    await expect(
      downloadTelegramAudio({ file_id: "audio-1" }, env),
    ).rejects.toThrow(/500/);
  });

  it("bloqueia quando o Telegram informa tamanho acima do limite", async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse({
        ok: true,
        result: {
          file_id: "audio-1",
          file_path: "voice/file_1.oga",
          file_size: MAX_TELEGRAM_AUDIO_BYTES + 1,
        },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      downloadTelegramAudio({ file_id: "audio-1" }, env),
    ).rejects.toThrow("20 MB");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("propaga erro no download do arquivo", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse({
          ok: true,
          result: { file_id: "audio-1", file_path: "voice/file_1.oga" },
        }),
      )
      .mockResolvedValueOnce(new Response("erro", { status: 404 }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      downloadTelegramAudio({ file_id: "audio-1" }, env),
    ).rejects.toThrow(/404/);
  });
});
