from app.models import TelegramAudioFile
from app.telegram import handle_telegram_update, split_message
from tests.fakes import FakeGroq, FakeTelegram, InMemoryRepository


def _text_update(text: str, telegram_id: int = 123) -> dict:
    return {
        "update_id": 1,
        "message": {
            "message_id": 1,
            "from": {"id": telegram_id, "first_name": "Teste", "username": "teste"},
            "chat": {"id": telegram_id, "type": "private"},
            "date": 1,
            "text": text,
        },
    }


def _voice_update(file_size: int = 3, telegram_id: int = 123) -> dict:
    return {
        "update_id": 2,
        "message": {
            "message_id": 2,
            "from": {"id": telegram_id, "first_name": "Teste"},
            "chat": {"id": telegram_id, "type": "private"},
            "date": 1,
            "voice": {
                "file_id": "audio-1",
                "file_unique_id": "audio-1",
                "mime_type": "audio/ogg",
                "file_size": file_size,
            },
        },
    }


async def test_processa_mensagem_de_texto() -> None:
    repo = InMemoryRepository()
    telegram = FakeTelegram()
    groq = FakeGroq(
        {
            "intent": "create_expense",
            "transaction": {
                "amount": 87.5,
                "description": "Mercado",
                "category": "Alimentação",
            },
        }
    )

    await handle_telegram_update(
        _text_update("mercado 87,50"),
        repo=repo,
        groq=groq,
        telegram=telegram,
    )

    assert len(telegram.messages) == 1
    chat_id, reply = telegram.messages[0]
    assert chat_id == 123
    assert "Gasto registrado: Mercado" in reply
    assert len(repo.transactions) == 1
    assert repo.transactions[0].user_id == repo.users[0].id


async def test_processa_audio_ate_criar_lancamento() -> None:
    repo = InMemoryRepository()
    telegram = FakeTelegram()
    groq = FakeGroq(
        {
            "intent": "create_expense",
            "transaction": {
                "amount": 87.5,
                "description": "Mercado",
                "category": "Alimentação",
            },
        }
    )

    await handle_telegram_update(
        _voice_update(),
        repo=repo,
        groq=groq,
        telegram=telegram,
    )

    assert telegram.downloaded == [
        TelegramAudioFile(
            file_id="audio-1",
            mime_type="audio/ogg",
            file_size=3,
        )
    ]
    assert len(groq.audio_calls) == 1
    assert "Gasto registrado: Mercado" in telegram.messages[0][1]
    assert repo.audit[0]["source"] == "audio"
    assert repo.transactions[0].amount_cents == 8750


async def test_avisa_audio_grande_sem_baixar() -> None:
    repo = InMemoryRepository()
    telegram = FakeTelegram()
    groq = FakeGroq()

    await handle_telegram_update(
        _voice_update(file_size=20 * 1024 * 1024 + 1),
        repo=repo,
        groq=groq,
        telegram=telegram,
    )

    assert telegram.downloaded == []
    assert groq.audio_calls == []
    assert telegram.messages == [(123, "⚠️ Áudio muito grande. Envie um áudio de até 20 MB.")]


async def test_pede_texto_ou_audio_quando_mensagem_vazia() -> None:
    repo = InMemoryRepository()
    telegram = FakeTelegram()
    groq = FakeGroq()
    update = _text_update("   ")

    await handle_telegram_update(update, repo=repo, groq=groq, telegram=telegram)

    assert telegram.messages
    assert "Envie um texto ou um áudio" in telegram.messages[0][1]


async def test_ignora_chat_que_nao_e_privado() -> None:
    repo = InMemoryRepository()
    telegram = FakeTelegram()
    groq = FakeGroq()
    update = _text_update("mercado 87,50")
    update["message"]["chat"]["type"] = "group"

    await handle_telegram_update(update, repo=repo, groq=groq, telegram=telegram)

    assert telegram.messages == []
    assert repo.transactions == []


async def test_envia_mensagem_generica_quando_transcricao_falha() -> None:
    repo = InMemoryRepository()
    telegram = FakeTelegram()
    groq = FakeGroq()
    groq.transcription_error = RuntimeError("falha na Groq")

    await handle_telegram_update(
        _voice_update(),
        repo=repo,
        groq=groq,
        telegram=telegram,
    )

    assert len(telegram.messages) == 1
    assert "Não consegui processar sua mensagem" in telegram.messages[0][1]


def test_split_message_respeita_limite_e_preserva_conteudo() -> None:
    text = "a" * 3000 + "\n" + "b" * 3000
    chunks = split_message(text, 4000)

    assert len(chunks) == 2
    assert all(len(chunk) <= 4000 for chunk in chunks)
    assert "".join(chunks).replace("\n", "") == text.replace("\n", "")


def test_split_message_mantem_texto_curto() -> None:
    assert split_message("oi", 4000) == ["oi"]
