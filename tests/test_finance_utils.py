import json

import pytest

from app.ai import (
    normalise_category,
    parse_amount,
    parse_date,
    resolve_period,
    sanitise_extraction,
    today_in_timezone,
)


def test_parse_amount_interpreta_formatos_brasileiros() -> None:
    assert parse_amount(87.5) == 87.5
    assert parse_amount("87,50") == 87.5
    assert parse_amount("R$ 1.200,50") == 1200.5
    assert parse_amount("1.200") == 1200
    assert parse_amount("90 reais") == 90


def test_parse_amount_rejeita_valores_invalidos() -> None:
    assert parse_amount("") is None
    assert parse_amount("abc") is None
    assert parse_amount(None) is None
    assert parse_amount(float("nan")) is None
    assert parse_amount(float("inf")) is None
    assert parse_amount(True) is None


def test_parse_date_aceita_apenas_datas_iso_validas() -> None:
    assert parse_date("2026-10-31") == "2026-10-31"
    assert parse_date("2024-02-29") == "2024-02-29"
    assert parse_date("2026-02-29") is None
    assert parse_date("2026-13-01") is None
    assert parse_date("31/10/2026") is None
    assert parse_date(None) is None


def test_normalise_category_sem_diferenciar_maiusculas() -> None:
    assert normalise_category("alimentação") == "Alimentação"
    assert normalise_category("SALÁRIO") == "Salário"
    assert normalise_category(" outras receitas ") == "Outras receitas"


def test_normalise_category_descarta_invalidas() -> None:
    assert normalise_category("Categoria Inventada") is None
    assert normalise_category(None) is None


def test_resolve_period_suporta_todos_os_periodos() -> None:
    today = "2026-10-31"
    assert resolve_period("today", today) == (today, today)
    assert resolve_period("yesterday", today) == ("2026-10-30", "2026-10-30")
    assert resolve_period("current_month", today) == ("2026-10-01", today)
    assert resolve_period("last_month", today) == ("2026-09-01", "2026-09-30")
    assert resolve_period("this_year", today) == ("2026-01-01", today)


def test_resolve_period_usa_mes_atual_como_padrao() -> None:
    today = "2026-10-31"
    assert resolve_period(None, today) == ("2026-10-01", today)
    assert resolve_period("periodo_invalido", today) == ("2026-10-01", today)


def test_sanitise_extraction_remove_cercas_e_texto_ao_redor() -> None:
    raw = "\n".join(
        [
            "Segue o resultado:",
            "```json",
            json.dumps(
                {
                    "intent": "create_expense",
                    "transaction": {
                        "amount": "87,50",
                        "description": " Mercado ",
                        "category": "alimentação",
                        "occurred_at": "2026-02-31",
                    },
                    "confidence": 1.4,
                }
            ),
            "```",
        ]
    )

    result = sanitise_extraction(raw, "2026-10-31")

    assert result.intent == "create_expense"
    assert result.transaction is not None
    assert result.transaction.amount == 87.5
    assert result.transaction.description == "Mercado"
    assert result.transaction.category == "Alimentação"
    assert result.transaction.occurred_at == "2026-10-31"
    assert result.confidence == 1.0


def test_sanitise_extraction_rebaixa_intencao_desconhecida() -> None:
    result = sanitise_extraction(
        json.dumps({"intent": "executar_comando", "reply_if_unclear": "Repita"}),
        "2026-10-31",
    )

    assert result.intent == "unknown"
    assert result.reply_if_unclear == "Repita"


def test_sanitise_extraction_descarta_campos_invalidos() -> None:
    result = sanitise_extraction(
        json.dumps(
            {
                "intent": "correct",
                "transaction": {
                    "amount": 10,
                    "description": "Teste",
                    "category": "Inventada",
                },
                "correction": {"field": "campo_invalido", "new_value": "x"},
                "query": {"period": "sempre", "category": "Inventada"},
            }
        ),
        "2026-10-31",
    )

    assert result.transaction is not None
    assert result.transaction.category is None
    assert result.correction is not None
    assert result.correction.field is None
    assert result.query is not None
    assert result.query.period is None
    assert result.query.category is None


def test_sanitise_extraction_trunca_texto_de_esclarecimento() -> None:
    result = sanitise_extraction(
        json.dumps({"intent": "unknown", "reply_if_unclear": "a" * 500}),
        "2026-10-31",
    )

    assert result.reply_if_unclear is not None
    assert len(result.reply_if_unclear) == 300


def test_sanitise_extraction_rejeita_json_invalido() -> None:
    with pytest.raises(ValueError):
        sanitise_extraction("não é json", "2026-10-31")

    with pytest.raises(ValueError):
        sanitise_extraction("{ quebrado", "2026-10-31")


def test_today_in_timezone_retorna_data_iso() -> None:
    assert len(today_in_timezone("America/Recife")) == 10
    assert len(today_in_timezone("UTC")) == 10
