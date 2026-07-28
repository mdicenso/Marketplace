"""Seed idempotente delle tabelle marketplace su Neon.

Popola `esperienze` (dalle 8 seed di data.py) e alcune `prenotazioni` iniziali SOLO se le
tabelle sono vuote. Verifica che gli eventuali `struttura_slug` esistano davvero nel CDP
(`strutture`), così il link operatore→venue è reale e non un riferimento morto.

Uso:  python -m marketplace.seed
"""

from sqlalchemy import text
from sqlmodel import select

from . import data
from .database import engine, get_session, init_db
from .models import COMMISSIONE, Esperienza, Prenotazione


def _cdp_slugs() -> set[str]:
    """Slug esistenti nel CRM del CDP (per validare i soft-link)."""
    with engine.connect() as c:
        return {r[0] for r in c.execute(text("select slug from strutture"))}


def run() -> None:
    init_db()
    cdp = _cdp_slugs()
    print(f"CDP: {len(cdp)} strutture note")

    with get_session() as s:
        # ---- esperienze ----
        n_exp = len(s.exec(select(Esperienza)).all())
        if n_exp == 0:
            for e in data.EXPERIENCES:
                link = e.struttura_slug
                if link and link not in cdp:
                    print(f"  ! {e.id}: struttura_slug '{link}' NON in CDP → azzero il link")
                    link = ""
                s.add(Esperienza(
                    slug=e.id, categoria=e.cat, titolo=e.title, area=e.area, comune=e.town,
                    operatore_nome=e.op, struttura_slug=link, partner=e.partner,
                    prezzo=e.price, durata=e.dur, gruppo=e.group, rating=e.rating,
                    recensioni=e.rev, descrizione=e.lead, inclusi=e.inc, percorso=e.route,
                    pubblicato=True,
                ))
            s.commit()
            print(f"Esperienze inserite: {len(data.EXPERIENCES)}")
        else:
            print(f"Esperienze già presenti ({n_exp}) → skip")

        # ---- prenotazioni iniziali ----
        n_pren = len(s.exec(select(Prenotazione)).all())
        if n_pren == 0:
            exps = {e.slug: e for e in s.exec(select(Esperienza)).all()}
            for slug, nome, pax, giorno in data.SEED_BOOKINGS_RAW:
                exp = exps.get(slug)
                if not exp:
                    continue
                lordo = exp.prezzo * pax
                fee = round(lordo * COMMISSIONE)
                p = Prenotazione(
                    codice_voucher="TMP", esperienza_id=exp.id, esperienza_slug=slug,
                    cliente_nome=nome, cliente_email="", data_esperienza=giorno, pax=pax,
                    importo_lordo=lordo, commissione=fee, importo_netto=lordo - fee,
                    con_navetta=False, stato="confermata",
                )
                s.add(p)
                s.flush()
                p.codice_voucher = f"AEM-{p.id:05d}"
            s.commit()
            print(f"Prenotazioni iniziali inserite: {len(data.SEED_BOOKINGS_RAW)}")
        else:
            print(f"Prenotazioni già presenti ({n_pren}) → skip")

    # ---- link operatore→CDP effettivi ----
    with get_session() as s:
        linked = s.exec(select(Esperienza).where(Esperienza.struttura_slug != "")).all()
        print("Esperienze collegate a un venue CDP:",
              [(e.slug, e.struttura_slug) for e in linked])
    print("SEED OK")


if __name__ == "__main__":
    run()
