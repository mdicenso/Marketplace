"""Contratto e client di autenticazione dell'area personale.

L'identità NON è del Marketplace: è del CDP (sistema di verità, come `strutture` e
`contatti_turisti`). Deciso il 29-07-2026: il CDP possiede la tabella `utenti` ed espone
`/api/v1/auth`; il Marketplace NON autentica in locale, chiama quell'API.

Questo modulo isola quel contratto in UN SOLO punto: oggi `login()` gira su uno STUB
locale (utenti finti in memoria) così l'area personale si sviluppa e si testa senza che
l'endpoint del CDP esista ancora. Domani si sostituisce il CORPO di `login()` con la POST
HTTP al CDP — la firma e il modello `AuthUser` restano identici, il resto dell'app non
cambia di una riga.

--- CONTRATTO ATTESO dal CDP `/api/v1/auth` (da concordare con la chat CDP) ---
  POST /api/v1/auth/login
    req : {"email": str, "password": str}
    200 : {"ok": true, "token": str, "user": {
             "email": str, "nome": str,
             "ruolo": "turista" | "operatore" | "admin",
             "struttura_slug": str        # valorizzato per operatore-venue, "" altrimenti
          }}
    401 : {"ok": false}
  GET /api/v1/auth/me   (header Authorization: Bearer <token>)  ->  stesso oggetto "user"

La chiave di join contatto↔utente è l'EMAIL (già chiave di dedup di `contatti_turisti`
e di `prenotazioni.cliente_email`). `struttura_slug` è il soft-link all'operatore-venue
(vedi models.Esperienza.struttura_slug).
"""

from typing import Optional

from pydantic import BaseModel

RUOLI = ("turista", "operatore", "admin")


class AuthUser(BaseModel):
    """Utente autenticato — stessa forma dell'oggetto `user` di /api/v1/auth."""

    email: str = ""
    nome: str = ""
    ruolo: str = ""            # "" = non autenticato; altrimenti uno di RUOLI
    struttura_slug: str = ""   # valorizzato solo per operatore-venue
    token: str = ""


# ------------------------------------------------------------------ STUB locale
# Utenti finti finché il CDP non espone /api/v1/auth. Password in chiaro SOLO perché è
# uno stub di sviluppo: hashing, sessione e persistenza sono responsabilità del CDP.
# NB (GDPR): con l'auth vera servirà il titolare del trattamento definito — blocca il go-live.
_PW = "demo"
_STUB: dict[str, AuthUser] = {
    "mario.rossi@email.it": AuthUser(
        email="mario.rossi@email.it", nome="Mario Rossi", ruolo="turista"),
    "sextantio@demo.it": AuthUser(
        email="sextantio@demo.it", nome="Sextantio Albergo Diffuso",
        ruolo="operatore", struttura_slug="sextantio-santo-stefano"),
    "admin@demo.it": AuthUser(
        email="admin@demo.it", nome="Staff AEM", ruolo="admin"),
}


def login(email: str, password: str) -> Optional[AuthUser]:
    """Verifica le credenziali e ritorna l'utente, o None se non valide.

    OGGI: stub locale.  DOMANI (una volta pronto il CDP), sostituire il corpo con:

        import httpx
        r = httpx.post(f"{CDP_URL}/api/v1/auth/login",
                       json={"email": email, "password": password}, timeout=8)
        if r.status_code == 200 and r.json().get("ok"):
            d = r.json()
            return AuthUser(**d["user"], token=d["token"])
        return None
    """
    email = (email or "").strip().lower()
    user = _STUB.get(email)
    if user is None or password != _PW:
        return None
    out = user.model_copy()
    out.token = f"stub-{email}"   # token finto; il vero token lo emette il CDP
    return out
