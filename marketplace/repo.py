"""Data-access del marketplace: DB (SQLModel) ↔ modelli UI (pydantic in data.py).

Tiene la UI Reflex del tutto ignara del DB: lo State chiama queste funzioni e riceve gli
stessi modelli `Experience`/`Booking` che già usava con i dati fittizi.
"""

from sqlmodel import select

from . import data
from .contatti_bridge import upsert_contatto_da_prenotazione
from .database import get_session
from .models import COMMISSIONE, Esperienza, Prenotazione


# --------------------------------------------------------------- mapping DB→UI
def _to_ui_exp(row: Esperienza) -> data.Experience:
    # data._exp ricalcola cat_label / cat_color / grad / route_str
    return data._exp(
        id=row.slug, cat=row.categoria, title=row.titolo, area=row.area, town=row.comune,
        op=row.operatore_nome, partner=row.partner, struttura_slug=row.struttura_slug,
        price=row.prezzo, dur=row.durata, group=row.gruppo, rating=row.rating,
        rev=row.recensioni, lead=row.descrizione, inc=list(row.inclusi or []),
        route=list(row.percorso or []),
    )


def _to_ui_booking(pren: Prenotazione, exp: Esperienza | None, fresh: bool = False) -> data.Booking:
    return data.Booking(
        exp_id=pren.esperienza_slug,
        exp_title=exp.titolo if exp else pren.esperienza_slug,
        exp_town=exp.comune if exp else "",
        exp_op=exp.operatore_nome if exp else "",
        exp_cat=exp.categoria if exp else "",
        exp_area=exp.area if exp else "",
        price=exp.prezzo if exp else 0,
        name=pren.cliente_nome, pax=pren.pax, date=pren.data_esperienza, fresh=fresh,
    )


# ---------------------------------------------------------------------- letture
def load_experiences() -> list[data.Experience]:
    with get_session() as s:
        rows = s.exec(
            select(Esperienza).where(Esperienza.pubblicato == True).order_by(Esperienza.id)  # noqa: E712
        ).all()
        return [_to_ui_exp(r) for r in rows]


def load_bookings() -> list[data.Booking]:
    """Prenotazioni + join all'esperienza (per titolo/comune/operatore delle dashboard)."""
    with get_session() as s:
        prens = s.exec(select(Prenotazione).order_by(Prenotazione.id.desc())).all()
        exps = {e.id: e for e in s.exec(select(Esperienza)).all()}
        return [_to_ui_booking(p, exps.get(p.esperienza_id)) for p in prens]


# --------------------------------------------------------------------- scritture
def create_prenotazione(exp_slug: str, nome: str, email: str, pax: int,
                        con_navetta: bool, data_esp: str) -> "tuple[data.Booking, str]":
    """Persiste una prenotazione su Neon; ritorna (Booking UI fresh=True, codice_voucher)."""
    with get_session() as s:
        exp = s.exec(select(Esperienza).where(Esperienza.slug == exp_slug)).first()
        if exp is None:
            raise ValueError(f"Esperienza '{exp_slug}' non trovata")

        lordo = exp.prezzo * pax + (9 * pax if con_navetta else 0)
        commissione = round(lordo * COMMISSIONE)
        netto = lordo - commissione

        pren = Prenotazione(
            codice_voucher="TMP", esperienza_id=exp.id, esperienza_slug=exp.slug,
            cliente_nome=nome or "Ospite", cliente_email=email,
            data_esperienza=data_esp, pax=pax,
            importo_lordo=lordo, commissione=commissione, importo_netto=netto,
            con_navetta=con_navetta, stato="confermata",
        )
        s.add(pren)
        s.flush()  # assegna pren.id
        pren.codice_voucher = f"AEM-{pren.id:05d}"
        s.add(pren)
        s.commit()
        s.refresh(pren)

        # Ponte -> CDP: l'acquirente diventa/aggiorna un contatto turista
        # (capture_point=marketplace, stato=cliente). Upsert best-effort su una connessione
        # separata (engine.begin()): la prenotazione e' gia' committata e non puo' essere
        # annullata da un eventuale errore del ponte.
        upsert_contatto_da_prenotazione(email=email, nome=nome)

        return _to_ui_booking(pren, exp, fresh=True), pren.codice_voucher
