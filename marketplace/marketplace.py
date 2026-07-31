"""Abruzzo Experience Market — POC marketplace di esperienze (Reflex).

Porting della demo HTML a 3 ruoli con stato condiviso reattivo:
  Turista  → catalogo / dettaglio / checkout / voucher
  Operatore→ dashboard prenotazioni (netto 89%, commissione 11%)
  Regione  → insight predittivi TDH → "spingi esperienza" che boosta il catalogo

Dati su Neon (Postgres) CONDIVISO col CDP: repo.py legge esperienze/prenotazioni, lo
State le carica in on_load. Deploy su Reflex Cloud (SSR). Pagina esperienza dedicata =
route statica /esperienza?e=<slug> (le route dinamiche [slug] non sono servite bene in
produzione da Reflex 0.9.7/RR7).
"""

import reflex as rx
from pydantic import BaseModel

from . import auth, repo
from .data import (
    ACCENT,
    BRAND,
    CATS,
    COMMISSION,
    INSIGHTS,
    OP_ID,
    Booking,
    Experience,
    Insight,
    Voucher,
)


# ---------------------------------------------------------------- modelli UI
class Cat(BaseModel):
    key: str
    label: str
    color: str
    count: int


class OpRow(BaseModel):
    title: str
    town: str
    name: str
    date: str
    pax: int
    gross: int
    fee: int
    net: int
    fresh: bool


class Split(BaseModel):
    area: str
    amount: int
    pct: int
    color: str


_BLANK = Experience(
    id="", cat="outdoor", title="", area="", town="", op="",
    price=0, dur="", group="", rating=0.0, rev=0, lead="",
)

# Credenziali stub per gli ingressi demo "Accedi come…" del login (specchio di auth._STUB).
DEMO_CREDS = {
    "turista": "mario.rossi@email.it",
    "operatore": "sextantio@demo.it",
    "admin": "admin@demo.it",
}


# ---------------------------------------------------------------------- State
class State(rx.State):
    role: str = "turista"
    active_filter: str = "all"

    experiences: list[Experience] = []       # caricate dal DB in on_load
    insights: list[Insight] = INSIGHTS
    bookings: list[Booking] = []             # caricate dal DB in on_load
    boosted: list[str] = []

    def on_load(self):
        """Carica esperienze e prenotazioni da Neon all'apertura della pagina."""
        self.experiences = repo.load_experiences()
        self.bookings = repo.load_bookings()

    @rx.var
    def cat_chips(self) -> list[Cat]:
        chips = [Cat(key="all", label="Tutte", color="#8a7f72", count=len(self.experiences))]
        for key, (label, color) in CATS.items():
            n = len([e for e in self.experiences if e.cat == key])
            chips.append(Cat(key=key, label=label, color=color, count=n))
        return chips

    # dialog / flusso prenotazione
    dialog_open: bool = False
    dialog_step: str = "detail"  # detail | checkout | confirm
    selected_id: str = ""
    voucher_code: str = ""
    loaded: bool = False  # False finché on_load non ha caricato i dati (evita flash "non trovata")

    # campi checkout
    ck_pax: str = "2"
    ck_name: str = "Mario Rossi"
    ck_email: str = "mario.rossi@email.it"
    ck_date: str = "2026-08-16"
    add_tua: bool = True

    # ---- catalogo -------------------------------------------------------
    @rx.var
    def filtered_experiences(self) -> list[Experience]:
        lst = [
            e for e in self.experiences
            if self.active_filter == "all" or e.cat == self.active_filter
        ]
        # esperienze spinte dalla Regione in cima
        return sorted(lst, key=lambda e: e.id not in self.boosted)

    @rx.var
    def catalog_title(self) -> str:
        if self.active_filter == "all":
            return "Esperienze in evidenza"
        return CATS[self.active_filter][0]

    @rx.var
    def catalog_sub(self) -> str:
        n = len(self.filtered_experiences)
        word = "esperienza" if n == 1 else "esperienze"
        return f"{n} {word} · dai borghi del Gran Sasso alla Costa dei Trabocchi"

    @rx.var
    def selected_exp(self) -> Experience:
        for e in self.experiences:
            if e.id == self.selected_id:
                return e
        return _BLANK

    # ---- checkout math --------------------------------------------------
    @rx.var
    def _pax_int(self) -> int:
        try:
            return int(self.ck_pax)
        except ValueError:
            return 1

    @rx.var
    def ck_sub(self) -> int:
        return self.selected_exp.price * self._pax_int

    @rx.var
    def ck_tua(self) -> int:
        return 9 * self._pax_int if self.add_tua else 0

    @rx.var
    def ck_tot(self) -> int:
        return self.ck_sub + self.ck_tua

    @rx.var
    def ck_fee(self) -> int:
        return round(self.ck_tot * COMMISSION)

    @rx.var
    def ck_net(self) -> int:
        return self.ck_tot - self.ck_fee

    # ---- KPI operatore --------------------------------------------------
    @rx.var
    def op_rows(self) -> list[OpRow]:
        rows = []
        for b in self.bookings:
            if b.exp_op != OP_ID:
                continue
            gross = b.price * b.pax
            fee = round(gross * COMMISSION)
            rows.append(OpRow(
                title=b.exp_title, town=b.exp_town, name=b.name, date=b.date,
                pax=b.pax, gross=gross, fee=fee, net=gross - fee, fresh=b.fresh,
            ))
        return rows

    @rx.var
    def op_count(self) -> int:
        return len(self.op_rows)

    @rx.var
    def op_gross(self) -> int:
        return sum(r.gross for r in self.op_rows)

    @rx.var
    def op_net(self) -> int:
        return round(self.op_gross * (1 - COMMISSION))

    @rx.var
    def op_fee(self) -> int:
        return round(self.op_gross * COMMISSION)

    @rx.var
    def op_pax(self) -> int:
        return sum(r.pax for r in self.op_rows)

    # ---- KPI regione ----------------------------------------------------
    @rx.var
    def reg_gmv(self) -> int:
        return sum(b.price * b.pax for b in self.bookings)

    @rx.var
    def reg_fee(self) -> int:
        return round(self.reg_gmv * COMMISSION)

    @rx.var
    def reg_count(self) -> int:
        return len(self.bookings)

    @rx.var
    def boosted_count(self) -> int:
        return len(self.boosted)

    @rx.var
    def value_split(self) -> list[Split]:
        buckets = {"Costa": 0, "Borghi": 0, "Montagna": 0}
        for b in self.bookings:
            g = b.price * b.pax
            if b.exp_cat in ("food", "culture"):
                k = "Borghi"
            elif "Trabocchi" in b.exp_area:
                k = "Costa"
            else:
                k = "Montagna"
            buckets[k] += g
        mx = max(1, *buckets.values())
        colors = {"Costa": "#256E7E", "Borghi": "#b5705a", "Montagna": "#3d4a2e"}
        return [
            Split(area=k, amount=v, pct=round(v / mx * 100), color=colors[k])
            for k, v in buckets.items()
        ]

    # ---- setter (in 0.9.7 non sono più auto-generati) -------------------
    def set_ck_pax(self, v: str):
        self.ck_pax = v

    def set_ck_name(self, v: str):
        self.ck_name = v

    def set_ck_email(self, v: str):
        self.ck_email = v

    def set_ck_date(self, v: str):
        self.ck_date = v

    def set_add_tua(self, v: bool):
        self.add_tua = v

    def set_dialog_open(self, v: bool):
        self.dialog_open = v

    # ---- eventi ---------------------------------------------------------
    def set_role(self, r: str):
        self.role = r

    def set_filter(self, k: str):
        self.active_filter = k

    def open_detail(self, exp_id: str):
        self.selected_id = exp_id
        self.dialog_step = "detail"
        self.ck_pax = "2"
        self.add_tua = True
        self.dialog_open = True

    def go_checkout(self):
        self.dialog_step = "checkout"

    def back_to_detail(self):
        self.dialog_step = "detail"

    def confirm_booking(self):
        booking, voucher = repo.create_prenotazione(
            exp_slug=self.selected_id, nome=self.ck_name, email=self.ck_email,
            pax=self._pax_int, con_navetta=self.add_tua, data_esp="16 ago",
        )
        for b in self.bookings:
            b.fresh = False
        self.bookings.insert(0, booking)
        self.voucher_code = voucher
        self.dialog_step = "confirm"
        return rx.toast.success("Prenotazione salvata su Neon — operatore e Regione aggiornati")

    def close_dialog(self):
        self.dialog_open = False

    def do_boost(self, target: str):
        if target not in self.boosted:
            self.boosted.append(target)
        e = next((x for x in self.experiences if x.id == target), None)
        title = e.title if e else "Esperienza"
        return rx.toast.success(f"“{title}” ora in evidenza sul marketplace + navetta attivata")

    # ---- pagina esperienza dedicata (/esperienza/<slug>) ----------------
    def load_experience_page(self):
        """on_load della route /esperienza/[slug]: carica dati e fissa l'esperienza."""
        self.loaded = False
        if not self.experiences:
            self.experiences = repo.load_experiences()
        self.bookings = repo.load_bookings()
        # slug via query param ?e=<slug> (route statica /esperienza: robusta in produzione,
        # le route dinamiche [slug] non vengono servite correttamente da Reflex 0.9.7 in RR7)
        self.selected_id = self.router.url.query_parameters.get("e", "")
        self.dialog_open = False
        self.dialog_step = "detail"
        self.loaded = True

    def start_checkout(self):
        """Apre il checkout direttamente (usato dal 'Prenota' della pagina dedicata)."""
        self.ck_pax = "2"
        self.add_tua = True
        self.dialog_step = "checkout"
        self.dialog_open = True

    @rx.var
    def exp_found(self) -> bool:
        return self.selected_exp.id != ""

    # ---------------------------------------------------- AREA PERSONALE (auth)
    # L'identità è del CDP; auth.py isola il contratto /api/v1/auth (oggi stub).
    # NB: distinto dal role-switcher DEMO (self.role) della top-bar, che NON è un login.
    li_email: str = ""
    li_password: str = ""
    auth_error: str = ""
    auth_ruolo: str = ""          # "" = non loggato; "turista" | "operatore" | "admin"
    auth_nome: str = ""
    auth_email: str = ""
    auth_struttura: str = ""
    auth_token: str = ""
    my_vouchers: list[Voucher] = []
    my_experiences: list[Experience] = []

    @rx.var
    def is_auth(self) -> bool:
        return self.auth_ruolo in ("turista", "operatore", "admin")

    @rx.var
    def auth_ruolo_label(self) -> str:
        return {"turista": "Turista", "operatore": "Operatore",
                "admin": "Admin"}.get(self.auth_ruolo, "")

    def set_li_email(self, v: str):
        self.li_email = v

    def set_li_password(self, v: str):
        self.li_password = v

    def do_login(self):
        user = auth.login(self.li_email, self.li_password)
        if user is None:
            self.auth_error = "Credenziali non valide."
            return
        self.auth_error = ""
        self.auth_ruolo = user.ruolo
        self.auth_nome = user.nome
        self.auth_email = user.email
        self.auth_struttura = user.struttura_slug
        self.auth_token = user.token
        self.li_password = ""
        self._load_personal_area()
        return rx.toast.success(f"Bentornato, {user.nome}")

    # Ingresso demo esplicito "Accedi come…": pre-riempie le credenziali dell'utente
    # stub del ruolo scelto e passa dal login vero (do_login → auth.login → CDP/stub).
    # Convenienza da POC; il login email/password resta la porta principale.
    def demo_login(self, ruolo: str):
        self.li_email = DEMO_CREDS.get(ruolo, "")
        self.li_password = "demo"
        return self.do_login()

    def do_logout(self):
        self.auth_ruolo = ""
        self.auth_nome = ""
        self.auth_email = ""
        self.auth_struttura = ""
        self.auth_token = ""
        self.li_password = ""
        self.my_vouchers = []
        self.my_experiences = []

    def load_area(self):
        """on_load /area: assicura il catalogo (serve all'operatore) e i dati personali."""
        if not self.experiences:
            self.experiences = repo.load_experiences()
        if self.is_auth:
            self._load_personal_area()

    def _load_personal_area(self):
        if self.auth_ruolo == "turista":
            self.my_vouchers = repo.load_vouchers_by_email(self.auth_email)
        elif self.auth_ruolo == "operatore":
            self.my_experiences = repo.load_experiences_by_operatore(
                self.auth_struttura, self.auth_nome)

    # ---- CRUD esperienze (area operatore): la tabella `esperienze` è nostra ----
    crud_open: bool = False
    crud_editing_slug: str = ""      # "" = creazione ; altrimenti modifica
    crud_error: str = ""
    f_titolo: str = ""
    f_categoria: str = "outdoor"
    f_area: str = ""
    f_comune: str = ""
    f_prezzo: str = ""
    f_durata: str = ""
    f_gruppo: str = ""
    f_descrizione: str = ""
    f_inclusi: str = ""              # una voce per riga
    f_percorso: str = ""            # una tappa per riga

    def set_crud_open(self, v: bool):
        self.crud_open = v

    def close_crud(self):
        self.crud_open = False

    def set_f_titolo(self, v: str): self.f_titolo = v
    def set_f_categoria(self, v: str): self.f_categoria = v
    def set_f_area(self, v: str): self.f_area = v
    def set_f_comune(self, v: str): self.f_comune = v
    def set_f_prezzo(self, v: str): self.f_prezzo = v
    def set_f_durata(self, v: str): self.f_durata = v
    def set_f_gruppo(self, v: str): self.f_gruppo = v
    def set_f_descrizione(self, v: str): self.f_descrizione = v
    def set_f_inclusi(self, v: str): self.f_inclusi = v
    def set_f_percorso(self, v: str): self.f_percorso = v

    def open_new_esperienza(self):
        self.crud_editing_slug = ""
        self.f_titolo = self.f_area = self.f_comune = self.f_prezzo = ""
        self.f_durata = self.f_gruppo = self.f_descrizione = ""
        self.f_inclusi = self.f_percorso = ""
        self.f_categoria = "outdoor"
        self.crud_error = ""
        self.crud_open = True

    def open_edit_esperienza(self, slug: str):
        e = next((x for x in self.my_experiences if x.id == slug), None)
        if e is None:
            return
        self.crud_editing_slug = slug
        self.f_titolo, self.f_categoria = e.title, e.cat
        self.f_area, self.f_comune = e.area, e.town
        self.f_prezzo = str(e.price)
        self.f_durata, self.f_gruppo = e.dur, e.group
        self.f_descrizione = e.lead
        self.f_inclusi = "\n".join(e.inc)
        self.f_percorso = "\n".join(e.route)
        self.crud_error = ""
        self.crud_open = True

    def save_esperienza(self):
        if not self.f_titolo.strip():
            self.crud_error = "Il titolo è obbligatorio."
            return
        try:
            prezzo = int(self.f_prezzo or 0)
        except ValueError:
            self.crud_error = "Prezzo non valido (usa un numero intero)."
            return
        inclusi = [x.strip() for x in self.f_inclusi.splitlines() if x.strip()]
        percorso = [x.strip() for x in self.f_percorso.splitlines() if x.strip()]
        campi = dict(
            titolo=self.f_titolo.strip(), categoria=self.f_categoria,
            area=self.f_area.strip(), comune=self.f_comune.strip(), prezzo=prezzo,
            durata=self.f_durata.strip(), gruppo=self.f_gruppo.strip(),
            descrizione=self.f_descrizione.strip(), inclusi=inclusi, percorso=percorso,
        )
        if self.crud_editing_slug:
            repo.update_esperienza(self.crud_editing_slug, **campi)
            msg = "Esperienza aggiornata"
        else:
            repo.create_esperienza(
                **campi, operatore_nome=self.auth_nome, struttura_slug=self.auth_struttura)
            msg = "Esperienza creata"
        self.crud_open = False
        self._load_personal_area()
        self.experiences = repo.load_experiences()   # rinfresca anche il catalogo pubblico
        return rx.toast.success(f"{msg} su Neon")

    def toggle_pubblicato(self, slug: str):
        e = next((x for x in self.my_experiences if x.id == slug), None)
        nuovo = not (e.pubblicato if e else True)
        repo.set_pubblicato(slug, nuovo)
        self._load_personal_area()
        self.experiences = repo.load_experiences()


# ------------------------------------------------------------- UI: primitivi
# token Radix theme-aware (validi in f-string, si adattano da soli a light/dark)
SURFACE = "var(--color-panel-solid)"
BORDER = "var(--gray-a6)"


def eyebrow(text: str, **kw) -> rx.Component:
    style = {"letterSpacing": "0.12em", "textTransform": "uppercase"}
    style.update(kw.pop("style", {}))
    return rx.text(text, size="1", weight="bold", style=style,
                   color_scheme="gray", **kw)


def money(value, prefix: str = "€") -> rx.Component:
    return rx.text(prefix, value.to_string(), style={"fontVariantNumeric": "tabular-nums"})


def kpi_card(label: str, value: rx.Component, delta: str, color: str, pulse=False) -> rx.Component:
    return rx.box(
        rx.hstack(
            rx.text(label, size="2", color_scheme="gray", weight="medium"),
            rx.box(width="10px", height="10px", border_radius="3px",
                   style={"background": color}),
            justify="between", align="center", width="100%",
        ),
        rx.heading(value, size="7", margin_top="0.5rem"),
        rx.text(delta, size="1", color_scheme="brown", margin_top="0.2rem"),
        style={
            "background": SURFACE, "border": f"1px solid {BORDER}",
            "borderRadius": "14px", "padding": "18px 19px",
            "boxShadow": rx.cond(pulse, f"0 0 0 2px {ACCENT}", "0 1px 3px rgba(0,0,0,.06)"),
        },
        flex="1", min_width="180px",
    )


# ----------------------------------------------------------------- top bar
def login_role_button(icon: str, title: str, sub: str, ruolo: str) -> rx.Component:
    """Ingresso esplicito 'Accedi come…' del login: un click entra nel ruolo scelto."""
    return rx.button(
        rx.hstack(
            rx.text(icon, style={"fontSize": "1.5rem"}),
            rx.vstack(
                rx.text(title, weight="bold", size="3"),
                rx.text(sub, size="1", color_scheme="gray"),
                spacing="0", align="start",
            ),
            rx.spacer(),
            rx.text("→", style={"fontSize": "1.2rem", "opacity": "0.55"}),
            align="center", width="100%", spacing="3",
        ),
        on_click=State.demo_login(ruolo),
        variant="surface", color_scheme="brown", size="4",
        width="100%", cursor="pointer",
        style={"height": "auto", "padding": "13px 16px", "textAlign": "left"},
    )


def top_bar() -> rx.Component:
    return rx.box(
        rx.hstack(
            rx.hstack(
                rx.html(
                    '<svg viewBox="0 0 64 64" fill="currentColor" style="width:32px;height:32px;color:#cc8e7a">'
                    '<path d="M32 37c-9 0-15 6-15 12 0 5 5 8 15 8s15-3 15-8c0-6-6-12-15-12z"/>'
                    '<ellipse cx="15" cy="29" rx="5" ry="7"/><ellipse cx="26" cy="21" rx="5" ry="7.5"/>'
                    '<ellipse cx="38" cy="21" rx="5" ry="7.5"/><ellipse cx="49" cy="29" rx="5" ry="7"/></svg>'
                ),
                rx.vstack(
                    rx.text("Bottega", style={"fontFamily": "'Cormorant Garamond',serif",
                            "fontStyle": "italic", "fontWeight": "600", "fontSize": "1.3rem", "lineHeight": "1"}),
                    rx.hstack(
                        rx.text("Wild", style={"fontFamily": "'Sacramento',cursive",
                                "fontSize": "1.1rem", "color": "#b5705a", "lineHeight": "0.7"}),
                        rx.text("& Authentic", style={"fontSize": "0.55rem", "letterSpacing": "0.14em",
                                "textTransform": "uppercase", "opacity": "0.75"}),
                        spacing="1", align="baseline",
                    ),
                    spacing="0", align="start",
                ),
                align="center", spacing="2",
            ),
            rx.spacer(),
            rx.link(
                rx.button(
                    rx.cond(State.is_auth, "👤 " + State.auth_nome, "Accedi"),
                    variant="soft", color_scheme="brown", size="2", cursor="pointer",
                ),
                href="/area", underline="none",
            ),
            rx.color_mode.button(),
            align="center", width="100%",
        ),
        style={
            "position": "sticky", "top": "0", "zIndex": "40",
            "backdropFilter": "blur(12px)",
            "background": rx.color_mode_cond(
                light="rgba(244,246,241,.86)", dark="rgba(14,19,16,.86)"),
            "borderBottom": f"1px solid {BORDER}",
            "padding": "12px 22px",
        },
    )


# ----------------------------------------------------------- vista TURISTA
def hero() -> rx.Component:
    def ph(src, extra):
        return rx.box(
            rx.image(src=src, style={"width": "100%", "height": "100%",
                                     "objectFit": "cover", "display": "block"}),
            style={**extra, "position": "absolute", "borderRadius": "16px",
                   "overflow": "hidden", "boxShadow": "0 10px 30px rgba(61,74,46,.16)"},
        )
    collage = rx.box(
        ph("/mp-outdoor.jpg", {"width": "60%", "height": "78%", "left": "0", "top": "11%", "zIndex": "2"}),
        ph("/mp-food.jpg",    {"width": "44%", "height": "52%", "right": "0", "top": "0", "zIndex": "3"}),
        ph("/mp-village.jpg", {"width": "46%", "height": "46%", "right": "6%", "bottom": "0", "zIndex": "1"}),
        style={"position": "relative", "height": "340px"},
        display=rx.breakpoints(initial="none", md="block"),
    )
    left = rx.box(
        eyebrow("Abruzzo Experience Market", style={"color": ACCENT}),
        rx.heading("Esperienze autentiche d'Abruzzo, prenotabili in due tap",
                   size="8", style={"fontWeight": "300", "lineHeight": "1.06",
                                    "marginBottom": "0.8rem", "maxWidth": "18ch"}),
        rx.text("Trekking, terme, borghi e cucina scelti con gli operatori del territorio. "
                "Prezzo chiaro, conferma immediata, voucher subito.",
                color_scheme="gray", size="4", style={"maxWidth": "46ch", "marginBottom": "1.2rem"}),
        rx.hstack(
            rx.input(placeholder="Cerca: trekking, terme, arrosticini, Scanno…",
                     variant="soft", size="3",
                     style={"flex": "1", "background": "transparent", "boxShadow": "none"}),
            rx.button("Cerca", size="3", color_scheme="brown", radius="full", cursor="pointer"),
            align="center", spacing="2",
            style={"background": "white", "border": f"1px solid {BORDER}", "borderRadius": "999px",
                   "padding": "5px 5px 5px 14px", "maxWidth": "520px",
                   "boxShadow": "0 8px 28px rgba(61,74,46,.10)"},
        ),
        rx.text("Commissione operatori 11% · trasporto incluso TUA4Fly · operatori verificati",
                color_scheme="gray", size="1", margin_top="0.9rem"),
    )
    return rx.box(
        rx.grid(left, collage, columns=rx.breakpoints(initial="1", md="2"),
                spacing="6", align="center", style={"maxWidth": "1180px", "margin": "0 auto"}),
        style={"padding": "40px 22px 26px", "borderBottom": f"1px solid {BORDER}"},
    )


def cat_chip(c: Cat) -> rx.Component:
    active = State.active_filter == c.key
    photo = rx.match(
        c.key,
        ("outdoor", "/mp-outdoor.jpg"), ("wellness", "/mp-wellness.jpg"),
        ("food", "/mp-food.jpg"), ("culture", "/mp-culture.jpg"),
        ("family", "/mp-family.jpg"), "/mp-village.jpg",   # default 'all' → borgo
    )
    return rx.box(
        rx.image(src=photo, style={"width": "100%", "height": "100%", "objectFit": "cover"}),
        rx.box(style={"position": "absolute", "inset": "0",
                      "background": "linear-gradient(to top, rgba(30,28,24,.76), rgba(30,28,24,.06) 62%)"}),
        rx.vstack(
            rx.text(c.label, weight="medium", style={"color": "white", "fontSize": "0.95rem", "lineHeight": "1.1"}),
            rx.text(c.count.to_string(), " esperienze",
                    style={"color": "rgba(255,255,255,.82)", "fontSize": "0.72rem"}),
            spacing="0", align="start",
            style={"position": "absolute", "left": "12px", "bottom": "9px", "zIndex": "2"},
        ),
        on_click=State.set_filter(c.key),
        style={
            "position": "relative", "height": "108px", "borderRadius": "14px", "overflow": "hidden",
            "cursor": "pointer", "boxShadow": "0 8px 28px rgba(61,74,46,.10)",
            "outline": rx.cond(active, "3px solid #b5705a", "1px solid rgba(0,0,0,0)"),
            "outlineOffset": "1px",
        },
    )


def exp_card(e: Experience) -> rx.Component:
    return rx.link(
        rx.box(
        # "immagine" = gradiente categoria con badge
        rx.box(
            rx.image(
                src=rx.match(
                    e.cat,
                    ("outdoor", "/mp-outdoor.jpg"), ("wellness", "/mp-wellness.jpg"),
                    ("food", "/mp-food.jpg"), ("culture", "/mp-culture.jpg"),
                    ("family", "/mp-family.jpg"), "/mp-outdoor.jpg",
                ),
                style={"position": "absolute", "inset": "0", "width": "100%",
                       "height": "100%", "objectFit": "cover"},
            ),
            rx.box(style={"position": "absolute", "inset": "0",
                          "background": "linear-gradient(to top, rgba(0,0,0,.30), transparent 55%)"}),
            rx.hstack(
                rx.cond(
                    State.boosted.contains(e.id),
                    rx.badge("⚡ Spinta dalla Regione", color_scheme="brown", variant="solid"),
                ),
                rx.cond(
                    e.partner,
                    rx.badge("★ Partner CDP", color_scheme="amber", variant="solid"),
                ),
                spacing="1", wrap="wrap", style={"position": "relative", "zIndex": "2"},
            ),
            rx.spacer(),
            rx.badge(e.cat_label, style={"background": "rgba(0,0,0,.42)", "color": "white",
                     "position": "relative", "zIndex": "2", "alignSelf": "flex-start"}),
            style={
                "position": "relative", "height": "160px", "borderRadius": "12px 12px 0 0",
                "padding": "12px", "display": "flex", "flexDirection": "column", "overflow": "hidden",
            },
        ),
        rx.vstack(
            rx.text("📍 ", e.area, " · ", e.town, size="1", weight="medium",
                    style={"color": e.cat_color}),
            rx.heading(e.title, size="4"),
            rx.text("di ", rx.text.strong(e.op), size="2", color_scheme="gray"),
            rx.box(
                rx.text("✈ ", e.route_str, "  · intermodale", size="1", weight="medium"),
                style={"background": rx.color_mode_cond(light="#f1e7dc", dark="#2a231a"),
                       "color": "#256E7E", "padding": "9px 10px", "borderRadius": "9px"},
                width="100%",
            ),
            rx.hstack(
                rx.vstack(
                    eyebrow("da"),
                    rx.text("€", e.price.to_string(), rx.text.span("/pers", size="1",
                            color_scheme="gray"), weight="bold", size="5",
                            style={"fontVariantNumeric": "tabular-nums"}),
                    spacing="0", align="start",
                ),
                rx.spacer(),
                rx.text("★ ", e.rating.to_string(), " (", e.rev.to_string(), ")",
                        size="2", color_scheme="gray", weight="medium"),
                width="100%", align="end",
                style={"borderTop": f"1px solid {BORDER}", "paddingTop": "12px", "marginTop": "auto"},
            ),
            align="start", spacing="2", padding="15px 16px", height="100%",
        ),
        style={
            "background": SURFACE, "border": f"1px solid {BORDER}", "borderRadius": "14px",
            "overflow": "hidden", "cursor": "pointer", "boxShadow": "0 1px 3px rgba(0,0,0,.06)",
            "transition": "transform .15s, box-shadow .15s", "display": "flex",
            "flexDirection": "column", "height": "100%",
            "_hover": {"transform": "translateY(-3px)", "boxShadow": "0 20px 45px rgba(0,0,0,.15)"},
        },
        ),
        href="/esperienza?e=" + e.id,
        underline="none",
        width="100%",
        style={"color": "inherit", "display": "block"},
    )


def turista_view() -> rx.Component:
    return rx.box(
        hero(),
        rx.box(
            rx.grid(rx.foreach(State.cat_chips, cat_chip),
                    columns=rx.breakpoints(initial="2", sm="3", lg="6"),
                    spacing="3", width="100%"),
            style={"maxWidth": "1180px", "margin": "0 auto", "padding": "18px 22px 6px"},
        ),
        rx.box(
            rx.vstack(
                rx.heading(State.catalog_title, size="6"),
                rx.text(State.catalog_sub, color_scheme="gray", size="2"),
                spacing="1", align="start", margin="1.6rem 0 1.2rem",
            ),
            rx.grid(
                rx.foreach(State.filtered_experiences, exp_card),
                columns=rx.breakpoints(initial="1", sm="2", lg="3"),
                spacing="4", width="100%", padding_bottom="3rem",
            ),
            style={"maxWidth": "1180px", "margin": "0 auto", "padding": "0 22px"},
        ),
    )


# --------------------------------------------------------------- dialog
def detail_content() -> rx.Component:
    e = State.selected_exp
    fact = lambda k, v: rx.box(
        eyebrow(k), rx.text(v, weight="bold", margin_top="0.2rem"),
        style={"background": rx.color_mode_cond(light="#efe7db", dark="#241f18"),
               "borderRadius": "11px", "padding": "12px 13px"}, flex="1", min_width="120px",
    )
    return rx.vstack(
        rx.box(
            rx.badge(e.cat_label, style={"background": "rgba(0,0,0,.32)", "color": "white"}),
            rx.heading(e.title, size="6", color="white", margin_top="0.5rem"),
            rx.text("di ", rx.text.strong(e.op), " · ", e.area,
                    color="rgba(255,255,255,.9)", size="2", margin_top="0.3rem"),
            style={"background": e.grad, "borderRadius": "14px", "padding": "20px",
                   "width": "100%"},
        ),
        rx.text(e.lead, color_scheme="gray", size="3", line_height="1.6"),
        rx.hstack(
            fact("Durata", e.dur), fact("Gruppo", e.group),
            fact("Giudizio", e.rating.to_string() + " · " + e.rev.to_string() + " rec."),
            fact("Dove", e.town),
            wrap="wrap", spacing="2", width="100%",
        ),
        rx.heading("Cosa è incluso", size="3", margin_top="0.4rem"),
        rx.vstack(
            rx.foreach(e.inc, lambda i: rx.hstack(
                rx.text("✓", color_scheme="brown", weight="bold"),
                rx.text(i, size="2", color_scheme="gray"), spacing="2", align="start")),
            spacing="1", align="start", width="100%",
        ),
        rx.box(
            rx.text("🚌 Come arrivare senza auto — mobilità integrata",
                    weight="bold", size="2", color="#256E7E"),
            rx.hstack(
                rx.foreach(e.route, lambda s: rx.badge(s, color_scheme="cyan", variant="soft")),
                wrap="wrap", spacing="2", margin_top="0.6rem",
            ),
            style={"background": rx.color_mode_cond(light="#f1e7dc", dark="#2a231a"),
                   "borderRadius": "12px", "padding": "15px 16px", "width": "100%"},
        ),
        rx.hstack(
            rx.vstack(eyebrow("da"),
                      rx.text("€", e.price.to_string(), rx.text.span(" /persona", size="1",
                              color_scheme="gray"), weight="bold", size="6"),
                      spacing="0", align="start"),
            rx.spacer(),
            rx.link(
                rx.button("Pagina ↗", variant="soft", color_scheme="gray",
                          size="3", cursor="pointer"),
                href="/esperienza?e=" + e.id,
            ),
            rx.button("Prenota ora →", on_click=State.go_checkout, size="3",
                      color_scheme="amber", cursor="pointer"),
            width="100%", align="center",
            style={"borderTop": f"1px solid {BORDER}", "paddingTop": "1rem"},
        ),
        spacing="3", align="start",
    )


def checkout_content() -> rx.Component:
    e = State.selected_exp
    summ_row = lambda k, v, strong=False: rx.hstack(
        rx.text(k, size="2", weight=rx.cond(strong, "bold", "regular"),
                color_scheme=rx.cond(strong, "gray", "gray")),
        rx.spacer(),
        rx.text(v, size="2", weight="bold", style={"fontVariantNumeric": "tabular-nums"}),
        width="100%",
    )
    return rx.vstack(
        rx.button("← Indietro", on_click=State.close_dialog, variant="soft",
                  color_scheme="gray", size="1", cursor="pointer"),
        eyebrow("Prenotazione · passo 2 di 3", style={"color": ACCENT}),
        rx.heading(e.title, size="5"),
        rx.grid(
            rx.vstack(rx.text("Data", size="1", weight="bold"),
                      rx.input(type="date", value=State.ck_date,
                               on_change=State.set_ck_date), spacing="1", align="start"),
            rx.vstack(rx.text("Partecipanti", size="1", weight="bold"),
                      rx.select(["1", "2", "3", "4", "5", "6"], value=State.ck_pax,
                                on_change=State.set_ck_pax), spacing="1", align="start"),
            rx.vstack(rx.text("Nome e cognome", size="1", weight="bold"),
                      rx.input(value=State.ck_name, on_change=State.set_ck_name),
                      spacing="1", align="start"),
            rx.vstack(rx.text("Email", size="1", weight="bold"),
                      rx.input(value=State.ck_email, on_change=State.set_ck_email),
                      spacing="1", align="start"),
            columns="2", spacing="3", width="100%",
        ),
        rx.hstack(
            rx.checkbox(checked=State.add_tua, on_change=State.set_add_tua),
            rx.text("Aggiungi navetta TUA4Fly sincronizzata col volo (+€9/pers)",
                    size="2", color_scheme="gray"),
            spacing="2", align="center",
        ),
        rx.box(
            summ_row("Subtotale esperienza", "€" + State.ck_sub.to_string()),
            rx.cond(State.add_tua,
                    summ_row("Navetta TUA4Fly", "€" + State.ck_tua.to_string())),
            rx.divider(),
            summ_row("Totale", "€" + State.ck_tot.to_string(), strong=True),
            rx.text("All'operatore (netto 89%): €", State.ck_net.to_string(),
                    size="1", color_scheme="brown", weight="bold"),
            rx.text("Commissione piattaforma 11% — reinvestita in Abruzzo: €",
                    State.ck_fee.to_string(), size="1", color_scheme="gray"),
            style={"background": rx.color_mode_cond(light="#efe7db", dark="#241f18"),
                   "borderRadius": "13px", "padding": "16px 17px", "width": "100%"},
        ),
        rx.callout("POC dimostrativa: il pagamento è simulato, nessun addebito reale.",
                   icon="info", color_scheme="amber", size="1"),
        rx.button("Conferma prenotazione (demo) →", on_click=State.confirm_booking,
                  size="3", color_scheme="amber", width="100%", cursor="pointer"),
        spacing="3", align="start",
    )


def confirm_content() -> rx.Component:
    e = State.selected_exp
    return rx.vstack(
        rx.box("✓", style={"background": rx.color_mode_cond(light="#f2eadd", dark="#231c12"),
                           "color": "#5a6b3f", "width": "72px", "height": "72px",
                           "borderRadius": "50%", "display": "grid", "placeItems": "center",
                           "fontSize": "36px"}),
        rx.heading("Prenotazione confermata", size="6"),
        rx.text("Abbiamo inviato il voucher a ", rx.text.strong(State.ck_name), ".",
                color_scheme="gray", size="2", text_align="center"),
        rx.box(
            eyebrow("Voucher digitale"),
            rx.text(State.voucher_code, weight="bold", size="4",
                    style={"fontFamily": "monospace", "letterSpacing": "0.04em"}),
            rx.text("Mostra il QR all'operatore · navetta TUA4Fly inclusa",
                    size="1", color_scheme="gray"),
            style={"background": rx.color_mode_cond(light="#efe7db", dark="#241f18"),
                   "border": f"1.5px dashed {BORDER}", "borderRadius": "15px",
                   "padding": "18px 20px", "width": "100%", "textAlign": "center"},
        ),
        rx.hstack(
            rx.button("Continua a esplorare", on_click=State.close_dialog,
                      variant="soft", color_scheme="gray", cursor="pointer"),
            rx.button("Vai all'area operatore", on_click=[State.close_dialog,
                      rx.redirect("/area")], color_scheme="brown", cursor="pointer"),
            spacing="2",
        ),
        rx.text("La prenotazione è comparsa in tempo reale nella dashboard Operatore "
                "e nel cruscotto Regione.", size="1", color_scheme="gray", text_align="center"),
        spacing="3", align="center",
    )


def exp_dialog() -> rx.Component:
    return rx.dialog.root(
        rx.dialog.content(
            rx.cond(
                State.dialog_step == "detail", detail_content(),
                rx.cond(State.dialog_step == "checkout", checkout_content(),
                        confirm_content()),
            ),
            style={"maxWidth": "640px"},
        ),
        open=State.dialog_open,
        on_open_change=State.set_dialog_open,
    )


# ------------------------------------------------------------ vista OPERATORE
def persona(text: str, color: str) -> rx.Component:
    return rx.box(
        rx.text(text, size="2", weight="medium", style={"color": color}),
        style={"border": f"1px solid {BORDER}", "background": SURFACE,
               "borderRadius": "999px", "padding": "7px 14px", "width": "fit-content"},
    )


def dash_wrap(*children) -> rx.Component:
    return rx.box(*children, style={"maxWidth": "1180px", "margin": "0 auto",
                                    "padding": "30px 22px 60px"})


def operatore_view() -> rx.Component:
    return dash_wrap(
        persona("🏛 Wolf Trails Abruzzo · guida ambientale escursionistica", "#256E7E"),
        rx.heading("La tua vetrina, senza cedere il cliente.", size="7", margin="0.8rem 0 0.4rem"),
        rx.text("Le prenotazioni arrivano qui in tempo reale. Trattieni il rapporto col "
                "cliente, paghi l'11% invece del 15–25% delle OTA globali.",
                color_scheme="gray", size="3", style={"maxWidth": "60ch"}),
        rx.hstack(
            kpi_card("Prenotazioni", State.op_count.to_string(), "confermate", "#256E7E"),
            kpi_card("Incasso netto", "€" + State.op_net.to_string(), "89% trattenuto", "#5a6b3f"),
            kpi_card("Commissione", "€" + State.op_fee.to_string(), "solo 11%", "#B7791A"),
            kpi_card("Partecipanti", State.op_pax.to_string(), "questo mese", "#7B4B8A"),
            wrap="wrap", spacing="3", margin="1.4rem 0", width="100%",
        ),
        rx.box(
            rx.box(
                rx.heading("Prenotazioni ricevute", size="4"),
                rx.text("Incasso netto = prezzo − 11% commissione piattaforma",
                        size="1", color_scheme="gray"),
                style={"padding": "16px 19px", "borderBottom": f"1px solid {BORDER}"},
            ),
            rx.table.root(
                rx.table.header(
                    rx.table.row(
                        rx.table.column_header_cell("Esperienza"),
                        rx.table.column_header_cell("Cliente"),
                        rx.table.column_header_cell("Data"),
                        rx.table.column_header_cell("Pax"),
                        rx.table.column_header_cell("Lordo"),
                        rx.table.column_header_cell("Commissione"),
                        rx.table.column_header_cell("Netto operatore"),
                    ),
                ),
                rx.table.body(
                    rx.foreach(State.op_rows, op_table_row),
                ),
                variant="ghost",
            ),
            style={"background": SURFACE, "border": f"1px solid {BORDER}",
                   "borderRadius": "14px", "overflow": "hidden"},
        ),
    )


def op_table_row(r: OpRow) -> rx.Component:
    return rx.table.row(
        rx.table.cell(rx.vstack(rx.text(r.title, weight="bold", size="2"),
                                rx.text(r.town, size="1", color_scheme="gray"), spacing="0")),
        rx.table.cell(r.name),
        rx.table.cell(r.date),
        rx.table.cell(r.pax.to_string()),
        rx.table.cell(money(r.gross)),
        rx.table.cell(rx.text("−€", r.fee.to_string(), color_scheme="gray", size="1")),
        rx.table.cell(rx.hstack(
            rx.text("€", r.net.to_string(), color_scheme="brown", weight="bold"),
            rx.cond(r.fresh, rx.badge("nuova", color_scheme="amber")),
            spacing="2", align="center")),
        style=rx.cond(r.fresh, {"background": rx.color_mode_cond(
            light="#f2eadd", dark="#231c12")}, {}),
    )


# -------------------------------------------------------------- vista REGIONE
def insight_card(i: Insight) -> rx.Component:
    done = State.boosted.contains(i.target)
    return rx.box(
        rx.hstack(
            rx.box(rx.cond(i.sig == "hot", "🔥", "❄"),
                   style={"width": "38px", "height": "38px", "borderRadius": "11px",
                          "display": "grid", "placeItems": "center",
                          "background": rx.cond(i.sig == "hot", ACCENT, "#f1e7dc"),
                          "fontSize": "18px"}),
            rx.vstack(
                rx.heading(i.title, size="3"),
                rx.text(i.desc, size="2", color_scheme="gray"),
                spacing="1", align="start",
            ),
            spacing="3", align="start", width="100%",
        ),
        rx.hstack(
            rx.foreach(i.tags, lambda t: rx.badge(
                rx.cond(t.dir == "up", "▲ ", "▼ ") + t.label,
                color_scheme=rx.cond(t.dir == "up", "tomato", "cyan"), variant="soft")),
            wrap="wrap", spacing="2", margin_top="0.8rem",
        ),
        rx.hstack(
            rx.text("→ ", i.action, size="1", color_scheme="gray", style={"flex": "1"}),
            rx.cond(
                done,
                rx.text("✓ Attiva sul marketplace", color_scheme="brown",
                        weight="bold", size="2"),
                rx.button("⚡ " + i.cta, on_click=State.do_boost(i.target),
                          color_scheme="amber", size="2", cursor="pointer"),
            ),
            width="100%", align="center", wrap="wrap",
            style={"borderTop": f"1px dashed {BORDER}", "paddingTop": "0.8rem",
                   "marginTop": "0.8rem"},
        ),
        style={
            "border": "1px solid " + rx.cond(i.urgent & ~done, ACCENT, BORDER),
            "background": SURFACE, "borderRadius": "13px", "padding": "16px 17px",
            "width": "100%",
        },
    )


def split_bar(s: Split) -> rx.Component:
    return rx.box(
        rx.hstack(rx.text(s.area, size="2", weight="medium"), rx.spacer(),
                  money(s.amount), width="100%"),
        rx.box(
            rx.box(style={"height": "100%", "width": s.pct.to_string() + "%",
                          "background": s.color, "borderRadius": "5px"}),
            style={"height": "9px", "borderRadius": "5px", "marginTop": "6px",
                   "background": rx.color_mode_cond(light="#efe7db", dark="#241f18"),
                   "overflow": "hidden"},
        ),
        width="100%", margin_bottom="0.9rem",
    )


def panel(title: str, sub: str, body: rx.Component) -> rx.Component:
    return rx.box(
        rx.box(
            rx.heading(title, size="4"),
            rx.text(sub, size="1", color_scheme="gray"),
            style={"padding": "16px 19px", "borderBottom": f"1px solid {BORDER}"},
        ),
        body,
        style={"background": SURFACE, "border": f"1px solid {BORDER}",
               "borderRadius": "14px", "overflow": "hidden", "width": "100%"},
    )


def regione_view() -> rx.Component:
    return dash_wrap(
        persona("📊 Regione Abruzzo · Turism Data Hub — regia della domanda", "#B7791A"),
        rx.heading("Dal dato all'azione commerciale.", size="7", margin="0.8rem 0 0.4rem"),
        rx.text("Il TDH prevede dove e quando si forma la domanda. Il marketplace è il "
                "canale per agire: spingere l'esperienza giusta, attivare la navetta, "
                "riequilibrare i flussi tra costa e borghi.",
                color_scheme="gray", size="3", style={"maxWidth": "62ch"}),
        rx.hstack(
            kpi_card("GMV settimana", "€" + State.reg_gmv.to_string(),
                     "flussi intercettati", ACCENT),
            kpi_card("Margine in regione", "€" + State.reg_fee.to_string(),
                     "reinvestito", "#5a6b3f"),
            kpi_card("Prenotazioni", State.reg_count.to_string(),
                     "via marketplace", "#256E7E"),
            kpi_card("Esperienze spinte", State.boosted_count.to_string(),
                     "regia TDH attiva", "#7B4B8A"),
            wrap="wrap", spacing="3", margin="1.4rem 0", width="100%",
        ),
        rx.grid(
            panel("Segnali del Turism Data Hub", "Insight predittivi → azione in un clic",
                  rx.vstack(rx.foreach(State.insights, insight_card),
                            spacing="3", padding="19px", width="100%")),
            rx.vstack(
                panel("Dove va il valore", "Ripartizione del GMV della settimana",
                      rx.box(rx.foreach(State.value_split, split_bar), padding="18px",
                             width="100%")),
                rx.box(
                    rx.text("🔁 Il loop chiuso: dati pubblici (PDND/ISTAT) → previsione TDH "
                            "→ spinta sul marketplace → mobilità TUA4Fly → prenotazione → "
                            "margine che resta in Abruzzo.", size="2", color="white"),
                    style={"background": "#2c2318", "borderRadius": "14px",
                           "padding": "15px 19px", "width": "100%"},
                ),
                spacing="3", width="100%",
            ),
            columns=rx.breakpoints(initial="1", md="2"),
            spacing="4", width="100%", margin_top="0.5rem",
            style={"gridTemplateColumns": rx.breakpoints(initial="1fr", md="1.6fr 1fr")},
        ),
    )


# --------------------------------------------------------------------- pagina
def index() -> rx.Component:
    return rx.box(
        top_bar(),
        # La home pubblica della Bottega è SEMPRE la vetrina turista: si esplora
        # senza login. Operatore e Gestione vivono dietro l'accesso (/area).
        turista_view(),
        exp_dialog(),
        style={"minHeight": "100vh",
               "background": rx.color_mode_cond(light="#f7f1e8", dark="#16130f")},
    )


# ----------------------------------------------- pagina esperienza /slug
def page_header() -> rx.Component:
    """Header leggero per la pagina dedicata (brand → home + tema)."""
    return rx.box(
        rx.hstack(
            rx.link(
                rx.hstack(
                    rx.box("▲", style={
                        "background": f"linear-gradient(135deg,{BRAND},#3d4a2e)",
                        "color": ACCENT, "width": "30px", "height": "30px",
                        "borderRadius": "9px", "display": "grid", "placeItems": "center",
                        "fontSize": "13px", "fontWeight": "800"}),
                    rx.text("Abruzzo Experience Market", weight="bold", size="3"),
                    align="center", spacing="2",
                ),
                href="/", underline="none", color="inherit",
            ),
            rx.spacer(),
            rx.link(
                rx.button("👤 Area personale", variant="soft", color_scheme="brown",
                          size="2", cursor="pointer"),
                href="/area", underline="none",
            ),
            rx.color_mode.button(),
            align="center", width="100%",
        ),
        style={
            "position": "sticky", "top": "0", "zIndex": "40", "backdropFilter": "blur(12px)",
            "background": rx.color_mode_cond(
                light="rgba(244,246,241,.86)", dark="rgba(14,19,16,.86)"),
            "borderBottom": f"1px solid {BORDER}", "padding": "12px 22px",
        },
    )


def experience_page_body() -> rx.Component:
    e = State.selected_exp
    fact = lambda k, v: rx.box(
        eyebrow(k), rx.text(v, weight="bold", margin_top="0.2rem"),
        style={"background": rx.color_mode_cond(light="#efe7db", dark="#241f18"),
               "borderRadius": "11px", "padding": "12px 13px"}, flex="1", min_width="120px",
    )
    return rx.box(
        rx.link("← Torna al catalogo", href="/", color_scheme="gray", size="2"),
        rx.box(
            rx.hstack(
                rx.cond(State.boosted.contains(e.id),
                        rx.badge("⚡ Spinta dalla Regione", color_scheme="brown", variant="solid")),
                rx.cond(e.partner,
                        rx.badge("★ Partner CDP", color_scheme="amber", variant="solid")),
                spacing="1", wrap="wrap",
            ),
            rx.badge(e.cat_label, style={"background": "rgba(0,0,0,.32)", "color": "white"},
                     margin_top="0.6rem"),
            rx.heading(e.title, size="8", color="white", margin_top="0.5rem"),
            rx.text("di ", rx.text.strong(e.op), " · ", e.area, " · ", e.town,
                    color="rgba(255,255,255,.92)", size="3", margin_top="0.4rem"),
            style={"background": e.grad, "borderRadius": "18px", "padding": "32px",
                   "marginTop": "0.8rem"},
        ),
        rx.grid(
            rx.vstack(
                rx.text(e.lead, color_scheme="gray", size="4", line_height="1.6"),
                rx.hstack(
                    fact("Durata", e.dur), fact("Gruppo", e.group),
                    fact("Giudizio", e.rating.to_string() + " · " + e.rev.to_string() + " rec."),
                    fact("Dove", e.town), wrap="wrap", spacing="2", width="100%",
                ),
                rx.heading("Cosa è incluso", size="4", margin_top="0.4rem"),
                rx.vstack(
                    rx.foreach(e.inc, lambda i: rx.hstack(
                        rx.text("✓", color_scheme="brown", weight="bold"),
                        rx.text(i, size="3", color_scheme="gray"), spacing="2", align="start")),
                    spacing="1", align="start", width="100%",
                ),
                rx.box(
                    rx.text("🚌 Come arrivare senza auto — mobilità integrata",
                            weight="bold", size="2", color="#256E7E"),
                    rx.hstack(
                        rx.foreach(e.route, lambda s: rx.badge(s, color_scheme="cyan", variant="soft")),
                        wrap="wrap", spacing="2", margin_top="0.6rem"),
                    style={"background": rx.color_mode_cond(light="#f1e7dc", dark="#2a231a"),
                           "borderRadius": "12px", "padding": "15px 16px", "width": "100%"},
                ),
                spacing="4", align="start", width="100%",
            ),
            rx.box(
                rx.vstack(
                    eyebrow("da"),
                    rx.text("€", e.price.to_string(), rx.text.span(" /persona", size="2",
                            color_scheme="gray"), weight="bold", size="8"),
                    rx.hstack(rx.text("★ ", e.rating.to_string(), color_scheme="amber", weight="bold"),
                              rx.text("(", e.rev.to_string(), " recensioni)", color_scheme="gray",
                                      size="2"), spacing="1", align="center"),
                    rx.button("Prenota ora →", on_click=State.start_checkout, size="4",
                              color_scheme="amber", width="100%", cursor="pointer",
                              margin_top="0.4rem"),
                    rx.text("Trasporto TUA4Fly opzionale · pagamento simulato (POC)",
                            size="1", color_scheme="gray", text_align="center"),
                    spacing="2", align="start", width="100%",
                ),
                style={"background": SURFACE, "border": f"1px solid {BORDER}",
                       "borderRadius": "16px", "padding": "22px",
                       "position": "sticky", "top": "84px"},
            ),
            columns=rx.breakpoints(initial="1", md="2"),
            spacing="5", width="100%", margin_top="1.4rem",
            style={"gridTemplateColumns": rx.breakpoints(initial="1fr", md="1.7fr 1fr")},
        ),
        style={"maxWidth": "1000px", "margin": "0 auto", "padding": "20px 22px 60px"},
    )


def not_found_body() -> rx.Component:
    return rx.center(
        rx.vstack(
            rx.heading("Esperienza non trovata", size="6"),
            rx.text("Lo slug richiesto non corrisponde a nessuna esperienza pubblicata.",
                    color_scheme="gray"),
            rx.link(rx.button("← Vai al catalogo", color_scheme="brown"), href="/"),
            spacing="3", align="center",
        ),
        min_height="60vh",
    )


def loading_body() -> rx.Component:
    return rx.center(
        rx.vstack(rx.spinner(size="3"),
                  rx.text("Caricamento esperienza…", color_scheme="gray", size="2"),
                  spacing="3", align="center"),
        min_height="60vh",
    )


def experience_page() -> rx.Component:
    return rx.box(
        page_header(),
        rx.cond(
            State.loaded,
            rx.cond(State.exp_found, experience_page_body(), not_found_body()),
            loading_body(),
        ),
        exp_dialog(),
        style={"minHeight": "100vh",
               "background": rx.color_mode_cond(light="#f7f1e8", dark="#16130f")},
    )


# ----------------------------------------------------- pagina AREA PERSONALE
_AREA_BODY = {"maxWidth": "1000px", "margin": "0 auto", "padding": "10px 22px 60px"}


def empty_state(title: str, sub: str, cta: str, href: str) -> rx.Component:
    return rx.center(
        rx.vstack(
            rx.heading(title, size="4"),
            rx.text(sub, color_scheme="gray", size="2", text_align="center"),
            rx.link(rx.button(cta, color_scheme="brown", cursor="pointer"), href=href),
            spacing="3", align="center",
        ),
        style={"background": SURFACE, "border": f"1px dashed {BORDER}",
               "borderRadius": "14px", "padding": "40px 22px", "width": "100%"},
    )


def login_card() -> rx.Component:
    return rx.center(
        rx.box(
            eyebrow("Area personale", style={"color": ACCENT}),
            rx.heading("Come vuoi entrare?", size="6", margin="0.4rem 0 0.2rem"),
            rx.text("Scegli il tuo accesso. Il turista esplora la Bottega anche "
                    "senza account; l'area riservata richiede l'accesso.",
                    color_scheme="gray", size="2"),
            # --- 3 ingressi espliciti "Accedi come…" → 3 aree diverse ---
            rx.vstack(
                login_role_button("🧭", "Accedi come Turista",
                                  "Vetrina, prenotazioni e i tuoi voucher", "turista"),
                login_role_button("🏛️", "Accedi come Operatore",
                                  "Le tue esperienze, disponibilità e incassi", "operatore"),
                login_role_button("⚙️", "Accedi come Gestione",
                                  "Staff regionale: catalogo e supervisione", "admin"),
                spacing="2", width="100%", margin_top="1.1rem",
            ),
            rx.cond(
                State.auth_error != "",
                rx.callout(State.auth_error, icon="triangle_alert",
                           color_scheme="red", size="1", width="100%",
                           margin_top="0.8rem"),
            ),
            # --- oppure login reale email/password (CDP /api/v1/auth) ---
            rx.hstack(
                rx.divider(),
                rx.text("oppure con email", size="1", color_scheme="gray",
                        style={"whiteSpace": "nowrap"}),
                rx.divider(),
                align="center", spacing="3", margin="1.3rem 0 0.2rem",
            ),
            rx.vstack(
                rx.input(value=State.li_email, on_change=State.set_li_email,
                         placeholder="nome@email.it", type="email", width="100%"),
                rx.input(value=State.li_password, on_change=State.set_li_password,
                         placeholder="password", type="password", width="100%"),
                rx.button("Entra →", on_click=State.do_login, size="3",
                          color_scheme="brown", variant="soft", width="100%",
                          cursor="pointer"),
                spacing="2", align="start", width="100%", margin_top="0.7rem",
            ),
            rx.text("Demo (stub): la password per tutti è ‘demo’. L'identità è del CDP.",
                    size="1", color_scheme="gray", margin_top="0.9rem"),
            style={"background": SURFACE, "border": f"1px solid {BORDER}",
                   "borderRadius": "16px", "padding": "26px", "maxWidth": "430px",
                   "width": "100%"},
        ),
        min_height="72vh", padding="30px 22px",
    )


def area_topbar() -> rx.Component:
    return rx.box(
        rx.hstack(
            rx.vstack(
                eyebrow("Area personale · " + State.auth_ruolo_label,
                        style={"color": ACCENT}),
                rx.heading("Ciao, " + State.auth_nome, size="6"),
                spacing="0", align="start",
            ),
            rx.spacer(),
            rx.button("Esci", on_click=State.do_logout, variant="soft",
                      color_scheme="gray", size="2", cursor="pointer"),
            width="100%", align="center",
        ),
        style={"maxWidth": "1000px", "margin": "0 auto", "padding": "26px 22px 8px"},
    )


def voucher_card(v: Voucher) -> rx.Component:
    return rx.box(
        rx.hstack(
            rx.vstack(
                rx.heading(v.exp_title, size="3"),
                rx.text("📍 ", v.exp_town, " · ", v.date, " · ", v.pax.to_string(), " pax",
                        size="1", color_scheme="gray"),
                spacing="1", align="start",
            ),
            rx.spacer(),
            rx.vstack(
                rx.text(v.codice, weight="bold",
                        style={"fontFamily": "monospace", "letterSpacing": "0.04em"}),
                rx.badge(v.stato, color_scheme="brown", variant="soft"),
                spacing="1", align="end",
            ),
            width="100%", align="center", wrap="wrap",
        ),
        style={"background": SURFACE, "border": f"1px solid {BORDER}",
               "borderRadius": "13px", "padding": "16px 18px", "width": "100%"},
    )


def area_turista() -> rx.Component:
    return rx.box(
        rx.heading("I miei voucher", size="5", margin_bottom="0.2rem"),
        rx.text("Le esperienze che hai prenotato sul marketplace.",
                color_scheme="gray", size="2", margin_bottom="1rem"),
        rx.cond(
            State.my_vouchers.length() > 0,
            rx.vstack(rx.foreach(State.my_vouchers, voucher_card), spacing="3", width="100%"),
            empty_state("Nessun voucher ancora",
                        "Quando prenoti un'esperienza, il voucher compare qui.",
                        "Esplora il catalogo", "/"),
        ),
        style=_AREA_BODY,
    )


def op_exp_row(e: Experience) -> rx.Component:
    return rx.box(
        rx.hstack(
            rx.box(style={"background": e.grad, "width": "46px", "height": "46px",
                          "borderRadius": "10px", "flex": "0 0 auto"}),
            rx.vstack(
                rx.hstack(
                    rx.heading(e.title, size="3"),
                    rx.cond(
                        e.pubblicato,
                        rx.badge("Pubblicata", color_scheme="brown", variant="soft"),
                        rx.badge("Nascosta", color_scheme="gray", variant="soft"),
                    ),
                    spacing="2", align="center", wrap="wrap",
                ),
                rx.text(e.area, " · €", e.price.to_string(), "/pers · ★ ",
                        e.rating.to_string(), size="1", color_scheme="gray"),
                spacing="1", align="start",
            ),
            rx.spacer(),
            rx.hstack(
                rx.button(rx.cond(e.pubblicato, "Nascondi", "Pubblica"),
                          on_click=State.toggle_pubblicato(e.id), variant="soft",
                          color_scheme="gray", size="2", cursor="pointer"),
                rx.button("Modifica", on_click=State.open_edit_esperienza(e.id),
                          color_scheme="brown", size="2", cursor="pointer"),
                spacing="2",
            ),
            width="100%", align="center", wrap="wrap",
        ),
        style={"background": SURFACE, "border": f"1px solid {BORDER}",
               "borderRadius": "13px", "padding": "14px 16px", "width": "100%"},
    )


def _fld(label: str, control: rx.Component) -> rx.Component:
    return rx.vstack(rx.text(label, size="1", weight="bold"), control,
                     spacing="1", align="start", width="100%")


def crud_dialog() -> rx.Component:
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title(
                rx.cond(State.crud_editing_slug != "", "Modifica esperienza",
                        "Nuova esperienza")),
            rx.vstack(
                _fld("Titolo", rx.input(value=State.f_titolo,
                                        on_change=State.set_f_titolo, width="100%")),
                rx.grid(
                    _fld("Categoria", rx.select(
                        list(CATS.keys()), value=State.f_categoria,
                        on_change=State.set_f_categoria, width="100%")),
                    _fld("Prezzo € (a persona)", rx.input(
                        value=State.f_prezzo, on_change=State.set_f_prezzo,
                        type="number", width="100%")),
                    columns="2", spacing="3", width="100%",
                ),
                rx.grid(
                    _fld("Area", rx.input(value=State.f_area,
                                          on_change=State.set_f_area, width="100%")),
                    _fld("Comune", rx.input(value=State.f_comune,
                                            on_change=State.set_f_comune, width="100%")),
                    _fld("Durata", rx.input(value=State.f_durata,
                                            on_change=State.set_f_durata,
                                            placeholder="es. 1 giorno · 6h", width="100%")),
                    _fld("Gruppo", rx.input(value=State.f_gruppo,
                                            on_change=State.set_f_gruppo,
                                            placeholder="es. max 10", width="100%")),
                    columns="2", spacing="3", width="100%",
                ),
                _fld("Descrizione", rx.text_area(
                    value=State.f_descrizione, on_change=State.set_f_descrizione,
                    rows="3", width="100%")),
                _fld("Cosa è incluso (una voce per riga)", rx.text_area(
                    value=State.f_inclusi, on_change=State.set_f_inclusi,
                    rows="3", width="100%")),
                _fld("Come arrivare (una tappa per riga)", rx.text_area(
                    value=State.f_percorso, on_change=State.set_f_percorso,
                    rows="2", width="100%")),
                rx.cond(
                    State.crud_error != "",
                    rx.callout(State.crud_error, icon="triangle_alert",
                               color_scheme="red", size="1", width="100%"),
                ),
                rx.hstack(
                    rx.button("Annulla", on_click=State.close_crud, variant="soft",
                              color_scheme="gray", cursor="pointer"),
                    rx.spacer(),
                    rx.button("Salva", on_click=State.save_esperienza,
                              color_scheme="brown", cursor="pointer"),
                    width="100%",
                ),
                spacing="3", align="start", width="100%",
            ),
            style={"maxWidth": "640px"},
        ),
        open=State.crud_open,
        on_open_change=State.set_crud_open,
    )


def area_operatore() -> rx.Component:
    return rx.box(
        rx.hstack(
            rx.vstack(
                rx.heading("Le mie esperienze", size="5"),
                rx.text("Crea, modifica e pubblica le esperienze che vendi. "
                        "Le scritture vanno su Neon (tabella del Marketplace).",
                        color_scheme="gray", size="2"),
                spacing="0", align="start",
            ),
            rx.spacer(),
            rx.button("+ Nuova esperienza", on_click=State.open_new_esperienza,
                      color_scheme="brown", size="2", cursor="pointer"),
            width="100%", align="center", margin_bottom="1rem", wrap="wrap",
        ),
        rx.cond(
            State.my_experiences.length() > 0,
            rx.vstack(rx.foreach(State.my_experiences, op_exp_row), spacing="3", width="100%"),
            rx.center(
                rx.vstack(
                    rx.heading("Nessuna esperienza collegata", size="4"),
                    rx.text("Crea la tua prima esperienza: comparirà nel catalogo pubblico.",
                            color_scheme="gray", size="2", text_align="center"),
                    rx.button("+ Nuova esperienza", on_click=State.open_new_esperienza,
                              color_scheme="brown", cursor="pointer"),
                    spacing="3", align="center",
                ),
                style={"background": SURFACE, "border": f"1px dashed {BORDER}",
                       "borderRadius": "14px", "padding": "40px 22px", "width": "100%"},
            ),
        ),
        crud_dialog(),
        style=_AREA_BODY,
    )


def area_admin() -> rx.Component:
    return rx.box(
        rx.heading("Console piattaforma", size="5", margin_bottom="0.2rem"),
        rx.text("Vista d'insieme del marketplace.", color_scheme="gray", size="2",
                margin_bottom="1rem"),
        rx.hstack(
            kpi_card("Esperienze", State.experiences.length().to_string(),
                     "pubblicate", "#256E7E"),
            kpi_card("Prenotazioni", State.reg_count.to_string(), "totali", "#5a6b3f"),
            kpi_card("GMV", "€" + State.reg_gmv.to_string(), "intercettato", ACCENT),
            wrap="wrap", spacing="3", width="100%",
        ),
        rx.callout("Gestione utenti, moderazione operatori e payout: in arrivo, contro "
                   "gli `utenti` e `/api/v1/auth` del CDP.",
                   icon="info", color_scheme="amber", size="1", margin_top="1.2rem"),
        style=_AREA_BODY,
    )


def area_authed() -> rx.Component:
    return rx.box(
        area_topbar(),
        rx.match(
            State.auth_ruolo,
            ("operatore", area_operatore()),
            ("admin", area_admin()),
            area_turista(),
        ),
    )


def area_page() -> rx.Component:
    return rx.box(
        page_header(),
        rx.cond(State.is_auth, area_authed(), login_card()),
        style={"minHeight": "100vh",
               "background": rx.color_mode_cond(light="#f7f1e8", dark="#16130f")},
    )


app = rx.App(stylesheets=["/brand.css"])  # tema in rxconfig.py; font brand in assets/brand.css
app.add_page(index, title="Abruzzo Experience Market", on_load=State.on_load)
app.add_page(experience_page, route="/esperienza",
             title="Esperienza · Abruzzo Experience Market",
             on_load=State.load_experience_page)
app.add_page(area_page, route="/area",
             title="Area personale · Abruzzo Experience Market",
             on_load=State.load_area)
