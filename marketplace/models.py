"""Modelli dati del Marketplace — tabelle `esperienze` e `prenotazioni`.

**SQLModel puro** (come il CDP; non `reflex.Model`, deprecato): il data-layer resta
disaccoppiato dalla UI Reflex. Vivono sullo STESSO Neon del CDP, che resta la fonte di
verità degli operatori (`strutture`). Il legame è SOFT: `Esperienza.struttura_slug`
punta a `strutture.slug` quando l'operatore è un venue registrato nel CDP (es. Sextantio);
resta "" per gli operatori-esperienza non-venue (guide, bike, ecc.), che il marketplace
può vendere anche se non sono ancora nel CRM. Nessuna FK cross-DB → niente accoppiamento
tra le due metadata SQLModel.
"""

from datetime import datetime, timezone
from typing import Optional

import sqlalchemy as sa
from sqlmodel import Field, SQLModel

# categorie esperienza (asse del catalogo turista)
CATEGORIE_EXP = ("outdoor", "wellness", "food", "culture", "family")
# stati prenotazione
STATI_PREN = ("confermata", "annullata", "completata")
COMMISSIONE = 0.11  # 11% piattaforma (vs 15–25% OTA)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Esperienza(SQLModel, table=True):
    """Prodotto vendibile del marketplace. `struttura_slug` = soft-link al CDP (o "")."""

    __tablename__ = "esperienze"

    id: Optional[int] = Field(default=None, primary_key=True)     # PK interna DB
    slug: str = Field(unique=True, index=True)                    # id di business (usato nella UI)
    categoria: str = "outdoor"                                    # vedi CATEGORIE_EXP

    titolo: str = ""
    area: str = ""
    comune: str = ""

    # --- Operatore: inline + soft-link opzionale al CDP ---
    operatore_nome: str = ""
    struttura_slug: str = ""            # -> strutture.slug nel CDP; "" se operatore non-venue
    partner: bool = False               # True se verificato/collegato a un venue CDP

    # --- Offerta ---
    prezzo: int = 0                     # € interi, prezzo "da" per persona
    durata: str = ""
    gruppo: str = ""
    rating: float = 0.0
    recensioni: int = 0
    descrizione: str = ""
    inclusi: list = Field(default_factory=list, sa_type=sa.JSON)   # ["Guida...", ...]
    percorso: list = Field(default_factory=list, sa_type=sa.JSON)  # ["Volo", "TUA4Fly → ...", ...]

    pubblicato: bool = True

    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now, sa_column_kwargs={"onupdate": _now})


class Prenotazione(SQLModel, table=True):
    """La transazione. Netto operatore = lordo − commissione 11%."""

    __tablename__ = "prenotazioni"

    id: Optional[int] = Field(default=None, primary_key=True)
    codice_voucher: str = Field(unique=True, index=True)

    esperienza_id: int = Field(foreign_key="esperienze.id", index=True)
    esperienza_slug: str = ""           # denormalizzato (comodo per le dashboard)

    cliente_nome: str = ""
    cliente_email: str = ""
    data_esperienza: str = ""           # ISO "YYYY-MM-DD" o etichetta breve
    pax: int = 1

    importo_lordo: int = 0
    commissione: int = 0
    importo_netto: int = 0
    con_navetta: bool = False           # navetta TUA4Fly aggiunta al checkout
    stato: str = "confermata"           # vedi STATI_PREN

    created_at: datetime = Field(default_factory=_now)
