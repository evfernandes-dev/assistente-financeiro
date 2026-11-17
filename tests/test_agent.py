import logging

import pytest

from app.ai import handle_financial_message, today_in_timezone
from tests.fakes import FakeGroq, InMemoryRepository


async def _create_user(repo: InMemoryRepository, telegram_id: int = 1):
    return await repo.ensure_user(telegram_id, first_name="Teste", username=f"teste{telegram_id}")


async def test_cria_despesa_por_texto() -> None:
    repo = InMemoryRepository()
    user = await _create_user(repo)
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

    reply = await handle_financial_message(
        user=user,
        text="mercado 87,50",
        source="text",
        repo=repo,
        groq=groq,
    )

    assert "Gasto registrado: Mercado" in reply
    assert "💸" in reply
    assert len(repo.transactions) == 1
    transaction = repo.transactions[0]
    assert transaction.kind == "expense"
    assert transaction.amount_cents == 8750
    assert transaction.category_name == "Alimentação"
    assert transaction.status == "confirmed"
    assert groq.chat_calls[0]["json_mode"] is True


async def test_cria_receita_e_corrige_data_invalida() -> None:
    repo = InMemoryRepository()
    user = await _create_user(repo)
    groq = FakeGroq(
        {
            "intent": "create_income",
            "transaction": {
                "kind": "expense",
                "amount": "3500",
                "description": "Salário",
                "category": "Salário",
                "occurred_at": "2026-02-31",
            },
        }
    )

    reply = await handle_financial_message(
        user=user,
        text="recebi 3500 de salário",
        source="text",
        repo=repo,
        groq=groq,
    )

    assert "Receita registrada: Salário" in reply
    assert "💰" in reply
    transaction = repo.transactions[0]
    assert transaction.kind == "income"
    assert transaction.amount_cents == 350000
    assert transaction.occurred_at == today_in_timezone(user.timezone)


async def test_nao_grava_quando_extracao_e_invalida(caplog: pytest.LogCaptureFixture) -> None:
    repo = InMemoryRepository()
    user = await _create_user(repo)
    groq = FakeGroq("não é json")

    with caplog.at_level(logging.ERROR):
        reply = await handle_financial_message(
            user=user,
            text="mercado 87,50",
            source="text",
            repo=repo,
            groq=groq,
        )

    assert "Não consegui interpretar" in reply
    assert "⚠️" in reply
    assert repo.transactions == []
    assert "extract_intent falhou" in caplog.text


async def test_pede_esclarecimento_quando_falta_valor() -> None:
    repo = InMemoryRepository()
    user = await _create_user(repo)
    groq = FakeGroq(
        {
            "intent": "create_expense",
            "transaction": {"description": "Mercado"},
            "reply_if_unclear": "Qual foi o valor?",
        }
    )

    reply = await handle_financial_message(
        user=user,
        text="mercado",
        source="text",
        repo=repo,
        groq=groq,
    )

    assert reply == "Qual foi o valor?"
    assert repo.transactions == []


async def test_consulta_apenas_dados_do_usuario() -> None:
    repo = InMemoryRepository()
    alice = await _create_user(repo, 1)
    bob = await _create_user(repo, 2)
    today = today_in_timezone(alice.timezone)

    await repo.create_transaction(
        user_id=alice.id,
        kind="expense",
        amount=100,
        description="Mercado",
        category="Alimentação",
        occurred_at=today,
        source="text",
    )
    await repo.create_transaction(
        user_id=alice.id,
        kind="expense",
        amount=50,
        description="Uber",
        category="Transporte",
        occurred_at=today,
        source="text",
    )
    await repo.create_transaction(
        user_id=alice.id,
        kind="income",
        amount=1000,
        description="Freela",
        category="Outras receitas",
        occurred_at=today,
        source="text",
    )
    await repo.create_transaction(
        user_id=bob.id,
        kind="expense",
        amount=999,
        description="Item do Bob",
        category="Outros",
        occurred_at=today,
        source="text",
    )

    groq = FakeGroq({"intent": "query", "query": {"period": "current_month"}})
    reply = await handle_financial_message(
        user=alice,
        text="quanto gastei esse mês?",
        source="text",
        repo=repo,
        groq=groq,
    )

    assert "Mercado" in reply
    assert "Uber" in reply
    assert "Item do Bob" not in reply
    assert "Saldo do período" in reply
    assert "📋" in reply
    assert "⚖️" in reply


async def test_consulta_filtra_por_categoria() -> None:
    repo = InMemoryRepository()
    user = await _create_user(repo)
    today = today_in_timezone(user.timezone)

    await repo.create_transaction(
        user_id=user.id,
        kind="expense",
        amount=100,
        description="Mercado",
        category="Alimentação",
        occurred_at=today,
        source="text",
    )
    await repo.create_transaction(
        user_id=user.id,
        kind="expense",
        amount=50,
        description="Uber",
        category="Transporte",
        occurred_at=today,
        source="text",
    )

    groq = FakeGroq(
        {
            "intent": "query",
            "query": {"period": "current_month", "category": "Transporte"},
        }
    )
    reply = await handle_financial_message(
        user=user,
        text="meus gastos com transporte",
        source="text",
        repo=repo,
        groq=groq,
    )

    assert "Uber" in reply
    assert "Mercado" not in reply


async def test_relatorio_mensal() -> None:
    repo = InMemoryRepository()
    user = await _create_user(repo)
    today = today_in_timezone(user.timezone)

    await repo.create_transaction(
        user_id=user.id,
        kind="expense",
        amount=100,
        description="Mercado",
        category="Alimentação",
        occurred_at=today,
        source="text",
    )
    await repo.create_transaction(
        user_id=user.id,
        kind="expense",
        amount=50,
        description="Uber",
        category="Transporte",
        occurred_at=today,
        source="text",
    )
    await repo.create_transaction(
        user_id=user.id,
        kind="income",
        amount=1000,
        description="Freela",
        category="Outras receitas",
        occurred_at=today,
        source="text",
    )

    groq = FakeGroq({"intent": "report", "query": {"period": "current_month"}})
    reply = await handle_financial_message(
        user=user,
        text="relatório do mês",
        source="text",
        repo=repo,
        groq=groq,
    )

    assert "Relatório de" in reply
    assert "Receitas" in reply
    assert "Despesas" in reply
    assert "Alimentação" in reply
    assert "Transporte" in reply
    assert "📊" in reply


async def test_corrige_e_exclui_ultimo_lancamento() -> None:
    repo = InMemoryRepository()
    user = await _create_user(repo)
    today = today_in_timezone(user.timezone)

    created = await repo.create_transaction(
        user_id=user.id,
        kind="expense",
        amount=100,
        description="Mercado",
        category="Outros",
        occurred_at=today,
        source="text",
    )

    correct_groq = FakeGroq(
        {"intent": "correct", "correction": {"field": "amount", "new_value": "90"}}
    )
    correct_reply = await handle_financial_message(
        user=user,
        text="corrige o último lançamento para 90",
        source="text",
        repo=repo,
        groq=correct_groq,
    )

    assert "Corrigi" in correct_reply
    assert "✏️" in correct_reply
    corrected = repo.transactions[0]
    assert corrected.amount_cents == 9000
    assert corrected.status == "corrected"

    delete_groq = FakeGroq({"intent": "delete"})
    delete_reply = await handle_financial_message(
        user=user,
        text="apaga o último gasto",
        source="text",
        repo=repo,
        groq=delete_groq,
    )

    assert "Excluí" in delete_reply
    assert "🗑️" in delete_reply
    assert repo.transactions[0].status == "deleted"
    assert [entry["action"] for entry in repo.audit] == ["create", "correct", "delete"]
    assert created.id == repo.transactions[0].id


async def test_corrige_sem_lancamentos() -> None:
    repo = InMemoryRepository()
    user = await _create_user(repo)
    groq = FakeGroq({"intent": "correct", "correction": {"field": "amount", "new_value": "90"}})

    reply = await handle_financial_message(
        user=user,
        text="corrige o último",
        source="text",
        repo=repo,
        groq=groq,
    )

    assert "Não encontrei nenhum lançamento" in reply


async def test_exclui_sem_lancamentos() -> None:
    repo = InMemoryRepository()
    user = await _create_user(repo)
    groq = FakeGroq({"intent": "delete"})

    reply = await handle_financial_message(
        user=user,
        text="apaga o último",
        source="text",
        repo=repo,
        groq=groq,
    )

    assert "Não encontrei nenhum lançamento" in reply


async def test_intencao_desconhecida_usa_resposta_padrao() -> None:
    repo = InMemoryRepository()
    user = await _create_user(repo)
    groq = FakeGroq({"intent": "unknown"})

    reply = await handle_financial_message(
        user=user,
        text="olá",
        source="text",
        repo=repo,
        groq=groq,
    )

    assert "Não entendi" in reply
    assert "mercado 87,50" in reply
