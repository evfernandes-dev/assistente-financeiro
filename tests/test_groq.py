import json

import httpx
import pytest
import respx

from app.groq import MAX_AUDIO_BYTES, GroqClient, GroqError
from app.models import AudioInput

CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
TRANSCRIPTION_URL = "https://api.groq.com/openai/v1/audio/transcriptions"


@respx.mock
async def test_transcreve_audio_e_envia_formulario_correto(settings) -> None:
    route = respx.post(TRANSCRIPTION_URL).mock(
        return_value=httpx.Response(200, json={"text": "  mercado 87,50  "})
    )

    client = GroqClient(settings)
    text = await client.transcribe(
        AudioInput(data=b"\x01\x02\x03", mime_type="audio/oga", file_name="audio.oga")
    )

    assert text == "mercado 87,50"
    request = route.calls.last.request
    assert request.headers["authorization"] == "Bearer test-groq-key"
    body = request.content
    assert b'name="model"' in body
    assert b"test-whisper" in body
    assert b'name="language"' in body
    assert b"audio.ogg" in body
    assert b"audio/ogg" in body


@respx.mock
async def test_rejeita_transcricao_vazia(settings) -> None:
    respx.post(TRANSCRIPTION_URL).mock(return_value=httpx.Response(200, json={"text": "   "}))

    with pytest.raises(GroqError, match="Transcrição vazia"):
        await GroqClient(settings).transcribe(AudioInput(data=b"\x01"))


@respx.mock
async def test_rejeita_resposta_sem_texto(settings) -> None:
    respx.post(TRANSCRIPTION_URL).mock(return_value=httpx.Response(200, json={}))

    with pytest.raises(GroqError, match="Transcrição vazia"):
        await GroqClient(settings).transcribe(AudioInput(data=b"\x01"))


@respx.mock
async def test_propaga_erro_http_da_groq(settings) -> None:
    respx.post(TRANSCRIPTION_URL).mock(return_value=httpx.Response(503, text="indisponível"))

    with pytest.raises(GroqError, match="503"):
        await GroqClient(settings).transcribe(AudioInput(data=b"\x01"))


async def test_bloqueia_audio_acima_de_25mb_sem_chamar_api(settings) -> None:
    with respx.mock(assert_all_called=False) as mock:
        with pytest.raises(GroqError, match="25 MB"):
            await GroqClient(settings).transcribe(AudioInput(data=b"\x00" * (MAX_AUDIO_BYTES + 1)))

        assert len(mock.calls) == 0


async def test_bloqueia_audio_vazio(settings) -> None:
    with respx.mock(assert_all_called=False) as mock:
        with pytest.raises(GroqError, match="Áudio vazio"):
            await GroqClient(settings).transcribe(AudioInput(data=b""))

        assert len(mock.calls) == 0


@respx.mock
async def test_chat_envia_payload_e_modo_json(settings) -> None:
    route = respx.post(CHAT_URL).mock(
        return_value=httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"intent":"unknown"}'}}]},
        )
    )

    content = await GroqClient(settings).chat(
        [{"role": "user", "content": "oi"}],
        json_mode=True,
    )

    assert content == '{"intent":"unknown"}'
    request = route.calls.last.request
    assert request.headers["authorization"] == "Bearer test-groq-key"
    payload = json.loads(request.content)
    assert payload["model"] == "test-model"
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["messages"] == [{"role": "user", "content": "oi"}]


@respx.mock
async def test_chat_rejeita_resposta_vazia(settings) -> None:
    respx.post(CHAT_URL).mock(
        return_value=httpx.Response(
            200,
            json={"choices": [{"message": {"content": "   "}}]},
        )
    )

    with pytest.raises(GroqError, match="resposta vazia"):
        await GroqClient(settings).chat([{"role": "user", "content": "oi"}])


@respx.mock
async def test_chat_propaga_erro_http(settings) -> None:
    respx.post(CHAT_URL).mock(return_value=httpx.Response(429, text="rate limit"))

    with pytest.raises(GroqError, match="429"):
        await GroqClient(settings).chat([{"role": "user", "content": "oi"}])
