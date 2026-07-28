"""Ponte Marketplace -> CDP: ogni acquirente diventa un contatto turista.

Il Marketplace e il CDP condividono lo STESSO database Neon ma hanno metadata SQLModel
distinti: la tabella `contatti_turisti` (anagrafica DOMANDA/B2C) e' di proprieta' del CDP.
Qui NON la ridefiniamo come modello locale (eviterebbe accoppiamento e rischi di
`create_all` incrociati): facciamo un upsert idempotente in SQL grezzo sull'engine
condiviso, con `ON CONFLICT (email)`.

Semantica (allineata a `crm_strutture.contatti.upsert_contatto` della Fase B):
- dedup per email, normalizzata lowercase;
- `capture_point = 'marketplace'` SOLO in inserimento (first-touch: NON sovrascrive un
  eventuale 'quiz' preesistente, cosi' l'attribuzione della prima fonte resta);
- `stato_engagement -> 'cliente'` sempre (un acquisto e' il segnale piu' forte);
- `consenso_marketing` MAI toccato (una transazione non e' consenso marketing);
- riattiva un eventuale soft-delete (`cancellato_il = NULL`).

Non deve MAI far fallire la prenotazione: ogni errore e' catturato e loggato.
"""

import re

from sqlalchemy import text

from .database import engine

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# created_at/updated_at sono NOT NULL senza server_default -> li valorizziamo noi in UTC
# (timezone('utc', now()) = timestamp senza tz in UTC, coerente con datetime.now(utc) del CDP).
# Le altre colonne mancanti usano i server_default della migrazione (lingua='it',
# profilo='{}', consenso_marketing=false, ecc.). capture_point NON e' aggiornato in
# conflitto: resta la fonte di primo contatto.
_UPSERT = text(
    """
    INSERT INTO contatti_turisti
        (email, nome, capture_point, stato_engagement, created_at, updated_at)
    VALUES
        (:email, :nome, 'marketplace', 'cliente',
         timezone('utc', now()), timezone('utc', now()))
    ON CONFLICT (email) DO UPDATE SET
        nome = COALESCE(NULLIF(EXCLUDED.nome, ''), contatti_turisti.nome),
        stato_engagement = 'cliente',
        cancellato_il = NULL,
        updated_at = timezone('utc', now())
    """
)


def upsert_contatto_da_prenotazione(email: str, nome: str = "") -> bool:
    """Upsert idempotente dell'acquirente in `contatti_turisti`.

    Ritorna True se il contatto e' stato scritto/aggiornato, False se l'email non e'
    valida o se la scrittura fallisce (sempre non bloccante per la prenotazione).
    """
    email = (email or "").strip().lower()
    nome = (nome or "").strip()
    if not _EMAIL_RE.match(email):
        return False
    try:
        with engine.begin() as conn:
            conn.execute(_UPSERT, {"email": email, "nome": nome})
        return True
    except Exception as e:  # noqa: BLE001  best-effort: non deve rompere il checkout
        print(f"[contatti_bridge] upsert contatto fallito per {email!r}: {e}")
        return False
