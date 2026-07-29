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
    # porte override-abili via env (default 3002/8004): utile quando un socket resta
    # orfano dopo un kill del worker multiprocessing e la porta non si libera subito.
    _fp = int(os.getenv("MP_FRONTEND_PORT", "3002"))
    _bp = int(os.getenv("MP_BACKEND_PORT", "8004"))
    _cfg.update(
        frontend_port=_fp,
        backend_port=_bp,
        api_url=f"http://localhost:{_bp}",
        transport="polling",
    )

config = rx.Config(**_cfg)
