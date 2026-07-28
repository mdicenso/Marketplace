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

from . import repo
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
        chips = [Cat(key="all", label="Tutte", color="#7A857C", count=len(self.experiences))]
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
        colors = {"Costa": "#256E7E", "Borghi": "#DE8E23", "Montagna": "#2E6349"}
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
        rx.text(delta, size="1", color_scheme="green", margin_top="0.2rem"),
        style={
            "background": SURFACE, "border": f"1px solid {BORDER}",
            "borderRadius": "14px", "padding": "18px 19px",
            "boxShadow": rx.cond(pulse, f"0 0 0 2px {ACCENT}", "0 1px 3px rgba(0,0,0,.06)"),
        },
        flex="1", min_width="180px",
    )


# ----------------------------------------------------------------- top bar
def role_button(label: str, value: str) -> rx.Component:
    active = State.role == value
    return rx.button(
        label,
        on_click=State.set_role(value),
        variant=rx.cond(active, "solid", "soft"),
        color_scheme=rx.cond(active, "green", "gray"),
        size="2", cursor="pointer",
    )


def top_bar() -> rx.Component:
    return rx.box(
        rx.hstack(
            rx.hstack(
                rx.box("▲", style={
                    "background": f"linear-gradient(135deg,{BRAND},#2E6349)",
                    "color": ACCENT, "width": "30px", "height": "30px",
                    "borderRadius": "9px", "display": "grid", "placeItems": "center",
                    "fontSize": "13px", "fontWeight": "800",
                }),
                rx.vstack(
                    rx.text("Abruzzo Experience Market", weight="bold", size="3"),
                    rx.text("Marketplace esperienze · POC", size="1", color_scheme="gray"),
                    spacing="0", align="start",
                ),
                align="center", spacing="2",
            ),
            rx.spacer(),
            rx.hstack(
                role_button("Turista", "turista"),
                role_button("Operatore", "operatore"),
                role_button("Regione · TDH", "regione"),
                spacing="1",
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
    tag = lambda t: rx.box(
        t, style={
            "background": "rgba(255,255,255,.14)", "border": "1px solid rgba(255,255,255,.24)",
            "color": "white", "padding": "7px 13px", "borderRadius": "999px",
            "fontSize": "13px", "fontWeight": "600",
        })
    return rx.box(
        eyebrow("Esperienze locali · non un altro sito di hotel",
                style={"color": "rgba(255,255,255,.82)"}),
        rx.heading("L'Abruzzo autentico, prenotabile in due tap.",
                   size="8", color="white", margin_top="0.6rem",
                   style={"maxWidth": "16ch"}),
        rx.text("Tour, natura, enogastronomia e borghi — venduti dagli operatori del "
                "territorio, già collegati ai trasporti pubblici. Il margine resta in regione.",
                color="rgba(255,255,255,.9)", margin_top="0.8rem", style={"maxWidth": "52ch"}),
        rx.hstack(
            tag("Commissione operatori 11% (vs 15–25%)"),
            tag("Trasporto incluso TUA4Fly"),
            tag("Operatori verificati dalla Regione"),
            wrap="wrap", spacing="2", margin_top="1.2rem",
        ),
        style={
            "background": f"radial-gradient(80% 120% at 82% -10%, {ACCENT}44, transparent 55%),"
                          f"linear-gradient(120deg,#1A3B2C,#2E6349)",
            "padding": "52px 22px 40px", "borderBottom": f"1px solid {BORDER}",
        },
    )


def cat_chip(c: Cat) -> rx.Component:
    active = State.active_filter == c.key
    return rx.button(
        rx.box(width="8px", height="8px", border_radius="50%",
               style={"background": c.color}),
        c.label,
        rx.text(c.count.to_string(), style={"opacity": "0.7"}),
        on_click=State.set_filter(c.key),
        variant=rx.cond(active, "solid", "outline"),
        color_scheme=rx.cond(active, "green", "gray"),
        size="2", cursor="pointer", radius="full",
    )


def exp_card(e: Experience) -> rx.Component:
    return rx.link(
        rx.box(
        # "immagine" = gradiente categoria con badge
        rx.box(
            rx.hstack(
                rx.cond(
                    State.boosted.contains(e.id),
                    rx.badge("⚡ Spinta dalla Regione", color_scheme="green", variant="solid"),
                ),
                rx.cond(
                    e.partner,
                    rx.badge("★ Partner CDP", color_scheme="amber", variant="solid"),
                ),
                spacing="1", wrap="wrap",
            ),
            rx.spacer(),
            rx.badge(e.cat_label, style={"background": "rgba(0,0,0,.32)", "color": "white"}),
            style={
                "background": e.grad, "height": "150px", "borderRadius": "12px 12px 0 0",
                "padding": "12px", "display": "flex", "flexDirection": "column",
            },
        ),
        rx.vstack(
            rx.text("📍 ", e.area, " · ", e.town, size="1", weight="medium",
                    style={"color": e.cat_color}),
            rx.heading(e.title, size="4"),
            rx.text("di ", rx.text.strong(e.op), size="2", color_scheme="gray"),
            rx.box(
                rx.text("✈ ", e.route_str, "  · intermodale", size="1", weight="medium"),
                style={"background": rx.color_mode_cond(light="#E1EEF0", dark="#173036"),
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
            rx.hstack(rx.foreach(State.cat_chips, cat_chip),
                      wrap="wrap", spacing="2"),
            style={"padding": "16px 22px", "borderBottom": f"1px solid {BORDER}"},
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
        style={"background": rx.color_mode_cond(light="#ECEFE8", dark="#1D2620"),
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
                rx.text("✓", color_scheme="green", weight="bold"),
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
            style={"background": rx.color_mode_cond(light="#E1EEF0", dark="#173036"),
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
                    size="1", color_scheme="green", weight="bold"),
            rx.text("Commissione piattaforma 11% — reinvestita in Abruzzo: €",
                    State.ck_fee.to_string(), size="1", color_scheme="gray"),
            style={"background": rx.color_mode_cond(light="#ECEFE8", dark="#1D2620"),
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
        rx.box("✓", style={"background": rx.color_mode_cond(light="#E4F0E6", dark="#16281C"),
                           "color": "#2F7D4F", "width": "72px", "height": "72px",
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
            style={"background": rx.color_mode_cond(light="#ECEFE8", dark="#1D2620"),
                   "border": f"1.5px dashed {BORDER}", "borderRadius": "15px",
                   "padding": "18px 20px", "width": "100%", "textAlign": "center"},
        ),
        rx.hstack(
            rx.button("Continua a esplorare", on_click=State.close_dialog,
                      variant="soft", color_scheme="gray", cursor="pointer"),
            rx.button("Vedi lato operatore", on_click=[State.close_dialog,
                      State.set_role("operatore")], color_scheme="green", cursor="pointer"),
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
            kpi_card("Incasso netto", "€" + State.op_net.to_string(), "89% trattenuto", "#2F7D4F"),
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
            rx.text("€", r.net.to_string(), color_scheme="green", weight="bold"),
            rx.cond(r.fresh, rx.badge("nuova", color_scheme="amber")),
            spacing="2", align="center")),
        style=rx.cond(r.fresh, {"background": rx.color_mode_cond(
            light="#E4F0E6", dark="#16281C")}, {}),
    )


# -------------------------------------------------------------- vista REGIONE
def insight_card(i: Insight) -> rx.Component:
    done = State.boosted.contains(i.target)
    return rx.box(
        rx.hstack(
            rx.box(rx.cond(i.sig == "hot", "🔥", "❄"),
                   style={"width": "38px", "height": "38px", "borderRadius": "11px",
                          "display": "grid", "placeItems": "center",
                          "background": rx.cond(i.sig == "hot", ACCENT, "#E1EEF0"),
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
                rx.text("✓ Attiva sul marketplace", color_scheme="green",
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
                   "background": rx.color_mode_cond(light="#ECEFE8", dark="#1D2620"),
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
                     "reinvestito", "#2F7D4F"),
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
                    style={"background": "#1A3B2C", "borderRadius": "14px",
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
        rx.match(
            State.role,
            ("operatore", operatore_view()),
            ("regione", regione_view()),
            turista_view(),
        ),
        exp_dialog(),
        style={"minHeight": "100vh",
               "background": rx.color_mode_cond(light="#F4F6F1", dark="#0E1310")},
    )


# ----------------------------------------------- pagina esperienza /slug
def page_header() -> rx.Component:
    """Header leggero per la pagina dedicata (brand → home + tema)."""
    return rx.box(
        rx.hstack(
            rx.link(
                rx.hstack(
                    rx.box("▲", style={
                        "background": f"linear-gradient(135deg,{BRAND},#2E6349)",
                        "color": ACCENT, "width": "30px", "height": "30px",
                        "borderRadius": "9px", "display": "grid", "placeItems": "center",
                        "fontSize": "13px", "fontWeight": "800"}),
                    rx.text("Abruzzo Experience Market", weight="bold", size="3"),
                    align="center", spacing="2",
                ),
                href="/", underline="none", color="inherit",
            ),
            rx.spacer(),
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
        style={"background": rx.color_mode_cond(light="#ECEFE8", dark="#1D2620"),
               "borderRadius": "11px", "padding": "12px 13px"}, flex="1", min_width="120px",
    )
    return rx.box(
        rx.link("← Torna al catalogo", href="/", color_scheme="gray", size="2"),
        rx.box(
            rx.hstack(
                rx.cond(State.boosted.contains(e.id),
                        rx.badge("⚡ Spinta dalla Regione", color_scheme="green", variant="solid")),
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
                        rx.text("✓", color_scheme="green", weight="bold"),
                        rx.text(i, size="3", color_scheme="gray"), spacing="2", align="start")),
                    spacing="1", align="start", width="100%",
                ),
                rx.box(
                    rx.text("🚌 Come arrivare senza auto — mobilità integrata",
                            weight="bold", size="2", color="#256E7E"),
                    rx.hstack(
                        rx.foreach(e.route, lambda s: rx.badge(s, color_scheme="cyan", variant="soft")),
                        wrap="wrap", spacing="2", margin_top="0.6rem"),
                    style={"background": rx.color_mode_cond(light="#E1EEF0", dark="#173036"),
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
            rx.link(rx.button("← Vai al catalogo", color_scheme="green"), href="/"),
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
               "background": rx.color_mode_cond(light="#F4F6F1", dark="#0E1310")},
    )


app = rx.App()  # tema configurato in rxconfig.py (RadixThemesPlugin)
app.add_page(index, title="Abruzzo Experience Market", on_load=State.on_load)
app.add_page(experience_page, route="/esperienza",
             title="Esperienza · Abruzzo Experience Market",
             on_load=State.load_experience_page)
