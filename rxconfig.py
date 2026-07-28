import os

import reflex as rx
from dotenv import load_dotenv

# Carica le variabili da .env (NON committato). Vedi .env.example.
load_dotenv()

# DB: Neon Postgres CONDIVISO col CDP via DATABASE_URL (schema psycopg3); fallback sqlite
# locale se le credenziali non ci sono. Il CDP resta fonte di verità operatori (`strutture`);
# qui aggiungiamo `esperienze` + `prenotazioni`.
DB_URL = os.getenv("DATABASE_URL", "sqlite:///marketplace_local.db")

# MP_LOCAL: settato SOLO in locale (dal launcher, NON nel .env → il deploy non lo eredita).
# Sul PC Indra le porte basse sono occupate (→ pagina bianca) e il proxy blocca l'upgrade
# WebSocket (→ serve polling). Sul cloud (MP_LOCAL assente) non si applica nulla.
_LOCAL = bool(os.getenv("MP_LOCAL"))

_cfg = dict(
    app_name="marketplace",
    db_url=DB_URL,
    plugins=[
        rx.plugins.SitemapPlugin(),
        rx.plugins.TailwindV4Plugin(),
        rx.plugins.RadixThemesPlugin(  # tema qui (App(theme=) deprecato in 0.9, rimosso in 1.0)
            theme=rx.theme(
                accent_color="green",
                gray_color="sage",
                radius="large",
                panel_background="solid",
            ),
        ),
    ],
)
if _LOCAL:
    _cfg.update(
        frontend_port=3002,
        backend_port=8004,
        api_url="http://localhost:8004",
        transport="polling",
    )

config = rx.Config(**_cfg)
