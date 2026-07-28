"""Engine e sessioni DB (SQLModel puro) — pattern identico al CDP.

Unico punto d'accesso al database. Legge `DATABASE_URL` da .env (Neon Postgres CONDIVISO
col CDP, schema psycopg3); fallback sqlite locale. Disaccoppiato da Reflex: usabile da app,
script e seed.
"""

import os
from contextlib import contextmanager
from typing import Iterator

from dotenv import load_dotenv
from sqlmodel import Session, SQLModel, create_engine

load_dotenv()

DB_URL = os.getenv("DATABASE_URL", "sqlite:///marketplace_local.db")

_connect_args = {"check_same_thread": False} if DB_URL.startswith("sqlite") else {}
engine = create_engine(DB_URL, echo=False, connect_args=_connect_args)


def init_db() -> None:
    """Crea SOLO le tabelle del marketplace (esperienze, prenotazioni).

    Importa i modelli locali così da registrare esse tabelle in SQLModel.metadata SENZA
    toccare `strutture` (di proprietà del CDP): `create_all` crea solo ciò che manca.
    """
    import marketplace.models  # noqa: F401  registra esperienze/prenotazioni

    SQLModel.metadata.create_all(engine)


@contextmanager
def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
