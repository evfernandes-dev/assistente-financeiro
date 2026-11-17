from app.db import normalise_database_url


def test_remove_channel_binding_do_dsn() -> None:
    url = (
        "postgresql://user:pass@ep-test-pooler.us-east-2.aws.neon.tech/neondb"
        "?sslmode=require&channel_binding=require"
    )

    assert normalise_database_url(url) == (
        "postgresql://user:pass@ep-test-pooler.us-east-2.aws.neon.tech/neondb?sslmode=require"
    )


def test_mantem_dsn_sem_query() -> None:
    url = "postgresql://user:pass@localhost:5432/test"
    assert normalise_database_url(url) == url


def test_remove_channel_binding_sem_alterar_outros_parametros() -> None:
    url = "postgresql://user:pass@host/db?channel_binding=require&application_name=bot"

    assert normalise_database_url(url) == "postgresql://user:pass@host/db?application_name=bot"
