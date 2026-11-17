import httpx
import pytest
import respx

from app.audio import MAX_TELEGRAM_AUDIO_BYTES, TelegramAudioError, download_telegram_audio
from app.models import TelegramAudioFile


@respx.mock
async def test_baixa_audio_do_telegram(settings) -> None:
    info_route = respx.get(
        f"https://api.telegram.org/bot{settings.telegram_bot_token}/getFile",
        params={"file_id": "audio-1"},
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "ok": True,
                "result": {
                    "file_id": "audio-1",
                    "file_path": "voice/file_1.oga",
                    "file_size": 3,
                },
            },
        )
    )
    file_route = respx.get(
        f"https://api.telegram.org/file/bot{settings.telegram_bot_token}/voice/file_1.oga"
    ).mock(return_value=httpx.Response(200, content=b"\x01\x02\x03"))

    audio = await download_telegram_audio(
        TelegramAudioFile(file_id="audio-1", mime_type="audio/oga", file_size=3),
        settings,
    )

    assert audio.data == b"\x01\x02\x03"
    assert audio.file_name == "audio.ogg"
    assert audio.mime_type == "audio/ogg"
    assert info_route.called
    assert file_route.called


async def test_bloqueia_audio_acima_de_20mb_antes_de_baixar(settings) -> None:
    with respx.mock(assert_all_called=False) as mock:
        with pytest.raises(TelegramAudioError, match="20 MB"):
            await download_telegram_audio(
                TelegramAudioFile(
                    file_id="audio-1",
                    file_size=MAX_TELEGRAM_AUDIO_BYTES + 1,
                ),
                settings,
            )

        assert len(mock.calls) == 0


@respx.mock
async def test_propaga_erro_ao_obter_metadados(settings) -> None:
    respx.get(
        f"https://api.telegram.org/bot{settings.telegram_bot_token}/getFile",
        params={"file_id": "audio-1"},
    ).mock(return_value=httpx.Response(500, text="erro"))

    with pytest.raises(TelegramAudioError, match="500"):
        await download_telegram_audio(TelegramAudioFile(file_id="audio-1"), settings)


@respx.mock
async def test_bloqueia_quando_telegram_informa_tamanho_acima_do_limite(settings) -> None:
    route = respx.get(
        f"https://api.telegram.org/bot{settings.telegram_bot_token}/getFile",
        params={"file_id": "audio-1"},
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "ok": True,
                "result": {
                    "file_id": "audio-1",
                    "file_path": "voice/file_1.oga",
                    "file_size": MAX_TELEGRAM_AUDIO_BYTES + 1,
                },
            },
        )
    )

    with pytest.raises(TelegramAudioError, match="20 MB"):
        await download_telegram_audio(TelegramAudioFile(file_id="audio-1"), settings)

    assert route.called


@respx.mock
async def test_propaga_erro_no_download_do_arquivo(settings) -> None:
    respx.get(
        f"https://api.telegram.org/bot{settings.telegram_bot_token}/getFile",
        params={"file_id": "audio-1"},
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "ok": True,
                "result": {"file_id": "audio-1", "file_path": "voice/file_1.oga"},
            },
        )
    )
    respx.get(
        f"https://api.telegram.org/file/bot{settings.telegram_bot_token}/voice/file_1.oga"
    ).mock(return_value=httpx.Response(404, text="erro"))

    with pytest.raises(TelegramAudioError, match="404"):
        await download_telegram_audio(TelegramAudioFile(file_id="audio-1"), settings)
