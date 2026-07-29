"""Contratto e client di autenticazione dell'area personale.

L'identità NON è del Marketplace: è del CDP (sistema di verità, come `strutture` e
`contatti_turisti`). Deciso il 29-07-2026: il CDP possiede la tabella `utenti` ed espone
`/api/v1/auth`; il Marketplace NON autentica in locale, chiama quell'API.

Questo modulo isola quel contratto in UN SOLO punto: `login()` chiama l'endpoint del CDP
`POST /api/v1/auth/login`; se il CDP è IRRAGGIUNGIBILE (offline/proxy) ripiega su uno STUB
locale (utenti finti = specchio del seed CDP). La firma e il modello `AuthUser` restano
identici per il resto dell'app. L'auth del CDP è LIVE dal 29-07-2026.

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

import os
from typing import Optional

import httpx
from pydantic import BaseModel

RUOLI = ("turista", "operatore", "admin")

# --- config CDP (auth vera) -------------------------------------------------
# Il Marketplace autentica SERVER-SIDE contro il CDP. CDP_URL override via env; default =
# backend fly.dev del CDP (verificato live). httpx rispetta HTTP(S)_PROXY dall'ambiente.
CDP_URL = os.getenv("CDP_URL", "https://73befaa1-08e6-4e6d-9677-205485b02d4b.fly.dev")
# TLS: sul PC Indra il proxy può intercettare i certificati → CDP_INSECURE=1 SOLO in
# sviluppo locale (MAI in produzione) per saltare la verifica.
_VERIFY = os.getenv("CDP_INSECURE") != "1"


class AuthUser(BaseModel):
    """Utente autenticato — stessa forma dell'oggetto `user` di /api/v1/auth."""

    email: str = ""
    nome: str = ""
    ruolo: str = ""            # "" = non autenticato; altrimenti uno di RUOLI
    struttura_slug: str = ""   # valorizzato solo per operatore-venue
    token: str = ""


def login(email: str, password: str) -> Optional[AuthUser]:
    """Autentica contro il CDP `POST /api/v1/auth/login`; ritorna l'utente o None.

    Fallback: se il CDP è IRRAGGIUNGIBILE (offline/proxy) ripiega sullo STUB locale. Su un
    401 (credenziali errate) NON ripiega e ritorna None — altrimenti lo stub accetterebbe
    ciò che il CDP ha rifiutato.
    """
    email = (email or "").strip().lower()
    url = f"{CDP_URL.rstrip('/')}/api/v1/auth/login"
    try:
        r = httpx.post(url, json={"email": email, "password": password},
                       timeout=8, verify=_VERIFY)
    except httpx.RequestError as e:            # connect/timeout/transport → CDP giù
        print(f"[auth] CDP non raggiungibile ({e}); uso lo stub locale")
        return _login_stub(email, password)
    if r.status_code == 200:
        d = r.json()
        if d.get("ok"):
            u = d.get("user") or {}
            return AuthUser(
                email=u.get("email", ""), nome=u.get("nome", ""),
                ruolo=u.get("ruolo", ""), struttura_slug=u.get("struttura_slug", ""),
                token=d.get("token", ""),
            )
    return None                                # 401 o payload inatteso


# ------------------------------------------------------------------ STUB locale
# Fallback di sviluppo quando il CDP è irraggiungibile. Utenti finti = SPECCHIO del seed CDP
# (`python -m crm_strutture.seed_utenti`), così il comportamento resta coerente offline.
# NB (GDPR): con utenti reali serve il titolare del trattamento definito — blocca il go-live.
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


def _login_stub(email: str, password: str) -> Optional[AuthUser]:
    """Verifica locale (fallback). Non emette un token reale — solo `stub-<email>`."""
    user = _STUB.get(email)
    if user is None or password != _PW:
        return None
    out = user.model_copy()
    out.token = f"stub-{email}"
    return out
