from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from tests.fakes import FakeGroq, FakeTelegram, InMemoryRepository

WEBHOOK_HEADERS = {"X-Telegram-Bot-Api-Secret-Token": "test-secret"}


def _valid_update() -> dict:
    return {
        "update_id": 7,
        "message": {
            "message_id": 1,
            "from": {"id": 123, "first_name": "Teste"},
            "chat": {"id": 123, "type": "private"},
            "date": 1,
            "text": "mercado 87,50",
        },
    }


def test_health_check(settings: Settings) -> None:
    app = create_app(
        settings=settings,
        repo=InMemoryRepository(),
        groq=FakeGroq(),
        telegram=FakeTelegram(),
    )

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["service"] == "assistente-financeiro"
    assert response.json()["timestamp"].endswith("Z")


def test_rejeita_webhook_sem_segredo(settings: Settings) -> None:
    app = create_app(
        settings=settings,
        repo=InMemoryRepository(),
        groq=FakeGroq(),
        telegram=FakeTelegram(),
    )

    with TestClient(app) as client:
        response = client.post("/telegram/webhook", json=_valid_update())

    assert response.status_code == 401


def test_rejeita_webhook_com_segredo_incorreto(settings: Settings) -> None:
    app = create_app(
        settings=settings,
        repo=InMemoryRepository(),
        groq=FakeGroq(),
        telegram=FakeTelegram(),
    )

    with TestClient(app) as client:
        response = client.post(
            "/telegram/webhook",
            json=_valid_update(),
            headers={"X-Telegram-Bot-Api-Secret-Token": "segredo-errado"},
        )

    assert response.status_code == 401


def test_rejeita_webhook_sem_segredo_configurado(settings: Settings) -> None:
    settings_without_secret = Settings(
        _env_file=None,
        telegram_bot_token=settings.telegram_bot_token,
        telegram_webhook_secret="",
        database_url=settings.database_url,
        groq_api_key=settings.groq_api_key,
    )
    app = create_app(
        settings=settings_without_secret,
        repo=InMemoryRepository(),
        groq=FakeGroq(),
        telegram=FakeTelegram(),
    )

    with TestClient(app) as client:
        response = client.post("/telegram/webhook", json=_valid_update(), headers=WEBHOOK_HEADERS)

    assert response.status_code == 401


def test_rejeita_json_invalido(settings: Settings) -> None:
    app = create_app(
        settings=settings,
        repo=InMemoryRepository(),
        groq=FakeGroq(),
        telegram=FakeTelegram(),
    )

    with TestClient(app) as client:
        response = client.post(
            "/telegram/webhook",
            content="{",
            headers={**WEBHOOK_HEADERS, "content-type": "application/json"},
        )

    assert response.status_code == 400


def test_rejeita_update_sem_update_id(settings: Settings) -> None:
    app = create_app(
        settings=settings,
        repo=InMemoryRepository(),
        groq=FakeGroq(),
        telegram=FakeTelegram(),
    )

    with TestClient(app) as client:
        response = client.post("/telegram/webhook", json={}, headers=WEBHOOK_HEADERS)

    assert response.status_code == 400


def test_enfileira_update_valido_e_responde_ok(settings: Settings) -> None:
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
    app = create_app(settings=settings, repo=repo, groq=groq, telegram=telegram)

    with TestClient(app) as client:
        response = client.post("/telegram/webhook", json=_valid_update(), headers=WEBHOOK_HEADERS)

    assert response.status_code == 200
    assert response.text == "ok"
    assert len(repo.transactions) == 1
    assert telegram.messages
    assert "Gasto registrado: Mercado" in telegram.messages[0][1]


def test_webhook_de_update_sem_mensagem_apenas_responde_ok(settings: Settings) -> None:
    app = create_app(
        settings=settings,
        repo=InMemoryRepository(),
        groq=FakeGroq(),
        telegram=FakeTelegram(),
    )

    with TestClient(app) as client:
        response = client.post(
            "/telegram/webhook",
            json={"update_id": 9},
            headers=WEBHOOK_HEADERS,
        )

    assert response.status_code == 200
    assert response.text == "ok"
