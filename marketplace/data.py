"""Seed data (illustrativo) per il POC Abruzzo Experience Market.

Sorgente: demo HTML (@_docs/demo-pitch.html). Nessun dato reale se non Sextantio
(unico operatore partner reale); tutti gli altri operatori sono illustrativi.
Quando arriverà Neon (fonte di verità operatori = CDP) questo modulo verrà
sostituito dalla lettura dal DB.
"""

from pydantic import BaseModel

# ---- Categorie: (etichetta, colore) ------------------------------------
CATS: dict[str, tuple[str, str]] = {
    "outdoor": ("Natura & trekking", "#2E6349"),
    "wellness": ("Terme & benessere", "#256E7E"),
    "food": ("Enogastronomia", "#B7791A"),
    "culture": ("Cultura & borghi", "#7B4B8A"),
    "family": ("Famiglia", "#C25A3B"),
}

# colori dashboard / palette brand
BRAND = "#234E3A"
ACCENT = "#DE8E23"
COMMISSION = 0.11
OP_ID = "Wolf Trails Abruzzo"  # operatore che sta guardando la sua dashboard


def _darken(hex_color: str) -> str:
    """Restituisce una versione più scura del colore (per il gradiente card)."""
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    r, g, b = (max(0, int(c * 0.55)) for c in (r, g, b))
    return f"#{r:02x}{g:02x}{b:02x}"


class Experience(BaseModel):
    id: str
    cat: str
    cat_label: str = ""
    cat_color: str = ""
    grad: str = ""
    title: str
    area: str
    town: str
    op: str
    partner: bool = False
    struttura_slug: str = ""  # soft-link a strutture.slug del CDP (venue registrato)
    price: int
    dur: str
    group: str
    rating: float
    rev: int
    lead: str
    inc: list[str] = []
    route: list[str] = []
    route_str: str = ""


class Tag(BaseModel):
    dir: str  # "up" | "down"
    label: str


class Insight(BaseModel):
    id: str
    urgent: bool
    sig: str  # "hot" | "cold"
    target: str  # id esperienza
    title: str
    desc: str
    tags: list[Tag] = []
    action: str
    cta: str


class Booking(BaseModel):
    exp_id: str
    exp_title: str
    exp_town: str
    exp_op: str
    exp_cat: str
    exp_area: str
    price: int
    name: str
    pax: int
    date: str
    fresh: bool = False


def _exp(**kw) -> Experience:
    label, color = CATS[kw["cat"]]
    kw["cat_label"] = label
    kw["cat_color"] = color
    kw["grad"] = f"linear-gradient(135deg, {color}, {_darken(color)})"
    kw["route_str"] = "  ›  ".join(kw.get("route", []))
    return Experience(**kw)


EXPERIENCES: list[Experience] = [
    _exp(
        id="gole-sagittario-raiano", cat="outdoor",
        title="Gole del Sagittario + Terme di Raiano",
        area="Valle del Sagittario", town="Anversa degli Abruzzi",
        op="Wolf Trails Abruzzo", partner=False, price=68,
        dur="1 giorno · 6h", group="max 10", rating=4.9, rev=212,
        lead="Cammino nella riserva WWF tra pareti calcaree a strapiombo e il fiume "
             "turchese, poi relax nelle sorgenti sulfuree all'imbocco della gola.",
        inc=["Guida ambientale escursionistica abilitata", "Ingresso riserva WWF",
             "Ingresso terme sulfuree", "Assicurazione infortuni"],
        route=["Volo", "TUA4Fly → Sulmona", "Navetta Anversa"],
    ),
    _exp(
        id="sextantio-notte-candela", cat="wellness",
        title="Notte a lume di candela + cena d'osteria",
        area="Gran Sasso — L'Aquila", town="Santo Stefano di Sessanio",
        op="Sextantio Albergo Diffuso", partner=True,
        struttura_slug="sextantio-santo-stefano", price=180,
        dur="1 notte", group="coppia", rating=4.9, rev=948,
        lead="L'albergo diffuso che ha fatto scuola in Italia: camere in pietra "
             "restaurate, niente TV, luce di candela, cena nell'osteria del borgo a 1.250 m.",
        inc=["Pernottamento in camera storica", "Cena degustazione d'osteria",
             "Tisaneria e colazione", "Accesso al borgo medievale"],
        route=["Volo", "TUA4Fly → L'Aquila", "Navetta borgo"],
    ),
    _exp(
        id="corno-grande-guidato", cat="outdoor",
        title="Corno Grande guidato — il tetto dell'Appennino",
        area="Gran Sasso & Campo Imperatore", town="Campo Imperatore",
        op="Aquila Alpina — guide alpine", partner=False, price=95,
        dur="1 giorno · 8h", group="max 6", rating=4.8, rev=134,
        lead="Salita alla vetta più alta degli Appennini (2.912 m) con guida alpina, "
             "tra camosci e vedute a 360° sull'altopiano di Campo Imperatore.",
        inc=["Guida alpina UIAGM", "Kit sicurezza (casco, imbrago)",
             "Briefing e transfer base", "Assicurazione"],
        route=["Volo", "TUA4Fly → L'Aquila", "Funivia Campo Imperatore"],
    ),
    _exp(
        id="ebike-costa-trabocchi", cat="outdoor",
        title="E-bike sulla Costa dei Trabocchi + pranzo su trabocco",
        area="Costa dei Trabocchi", town="Fossacesia",
        op="Costa Verde Bike", partner=False, price=75,
        dur="1 giorno · 5h", group="max 12", rating=4.7, rev=301,
        lead="Pedalata facile sulla Via Verde, l'ex ferrovia adriatica trasformata in "
             "greenway, con pranzo di pesce su un trabocco storico sospeso sul mare.",
        inc=["Noleggio e-bike + casco", "Guida cicloturistica",
             "Pranzo di pesce su trabocco", "Rientro assistito"],
        route=["Volo", "TUA4Fly → Pescara", "Treno costa → Fossacesia"],
    ),
    _exp(
        id="zafferano-navelli", cat="food",
        title="Zafferano di Navelli & Montepulciano d'Abruzzo",
        area="Piana di Navelli", town="Navelli",
        op="Oro Rosso Navelli", partner=False, price=45,
        dur="3 ore", group="max 15", rating=4.8, rev=97,
        lead="Visita ai campi dell'oro rosso d'Abruzzo, la spezia DOP più preziosa "
             "d'Italia, con degustazione guidata di piatti allo zafferano e vini del territorio.",
        inc=["Visita guidata ai campi", "Degustazione 4 assaggi allo zafferano",
             "Calici di Montepulciano d'Abruzzo", "Confezione di zafferano DOP"],
        route=["Volo", "TUA4Fly → L'Aquila", "Navetta Navelli"],
    ),
    _exp(
        id="ciaspolata-majella-terme", cat="wellness",
        title="Ciaspolata al tramonto + terme d'inverno",
        area="Parco Nazionale della Majella", town="Caramanico Terme",
        op="Majella Wild", partner=False, price=58,
        dur="1 giorno", group="max 10", rating=4.9, rev=156,
        lead="Racchette da neve nel silenzio della Majella al tramonto, poi il tepore "
             "delle acque termali di Caramanico per sciogliere la stanchezza.",
        inc=["Noleggio ciaspole e bastoncini", "Guida escursionistica",
             "Ingresso terme serale", "Tisana calda di vetta"],
        route=["Volo", "TUA4Fly → Scafa", "Navetta Caramanico"],
    ),
    _exp(
        id="museo-lupo-barrea", cat="family",
        title="Museo del Lupo + Lago di Barrea in famiglia",
        area="Parco Nazionale d'Abruzzo", town="Civitella Alfedena",
        op="Parco Experience", partner=False, price=30,
        dur="1 giorno", group="famiglie", rating=4.8, rev=274,
        lead="Il recinto faunistico del lupo appenninico e una passeggiata facile sulla "
             "riva panoramica del Lago di Barrea: natura a misura di bambino.",
        inc=["Ingresso Museo del Lupo", "Attività didattica per bambini",
             "Passeggiata guidata al lago", "Kit piccolo esploratore"],
        route=["Volo", "TUA4Fly → Castel di Sangro", "Navetta Barrea"],
    ),
    _exp(
        id="confetti-sulmona", cat="culture",
        title="Confetti di Sulmona: tour del laboratorio storico",
        area="Valle Peligna", town="Sulmona",
        op="Confetteria storica — experience", partner=False, price=22,
        dur="2 ore", group="max 20", rating=4.7, rev=188,
        lead="Dentro una confetteria storica dove nascono i celebri confetti di Sulmona, "
             "tra macchinari d'epoca, i fiori di confetto e la città di Ovidio.",
        inc=["Visita guidata al laboratorio", "Dimostrazione dei fiori di confetto",
             "Degustazione", "Passeggiata nel centro di Sulmona"],
        route=["Volo", "TUA4Fly → Sulmona", "A piedi in centro"],
    ),
]

# prenotazioni preesistenti così le dashboard non sono vuote
SEED_BOOKINGS_RAW = [
    ("sextantio-notte-candela", "Familie Weber", 2, "12 ago"),
    ("ebike-costa-trabocchi", "The Owens", 2, "14 ago"),
    ("gole-sagittario-raiano", "M. Dupont", 4, "15 ago"),
]

INSIGHTS: list[Insight] = [
    Insight(
        id="i1", urgent=True, sig="hot", target="ebike-costa-trabocchi",
        title="+800 arrivi previsti sulla Costa dei Trabocchi — sab 16/08",
        desc="Meteo ottimo e concerto a Fossacesia. La domanda di esperienze in zona "
             "supera del 60% l'offerta prenotata: rischio flusso non intercettato.",
        tags=[Tag(dir="up", label="Domanda +60%"), Tag(dir="down", label="Offerta sotto soglia")],
        action="Metti in evidenza E-bike Costa dei Trabocchi e attiva la navetta TUA4Fly dedicata.",
        cta="Spingi esperienza + navetta",
    ),
    Insight(
        id="i2", urgent=False, sig="cold", target="sextantio-notte-candela",
        title="Borghi dell'entroterra sotto-visitati",
        desc="Occupazione borghi interni 34% contro 91% della costa. Opportunità di "
             "riequilibrio dei flussi verso Santo Stefano di Sessanio e Scanno.",
        tags=[Tag(dir="down", label="Borghi 34%"), Tag(dir="up", label="Costa 91%")],
        action="Promuovi Notte a Santo Stefano di Sessanio ai turisti in arrivo a Pescara.",
        cta="Promuovi esperienza borghi",
    ),
    Insight(
        id="i3", urgent=False, sig="cold", target="ciaspolata-majella-terme",
        title="Bassa stagione Majella: capacità termale inutilizzata",
        desc="Le terme di Caramanico viaggiano al 40% infrasettimanale a febbraio. Un "
             "pacchetto ciaspole+terme può assorbire la capacità.",
        tags=[Tag(dir="down", label="Terme 40%"), Tag(dir="up", label="Neve ottima")],
        action="Spingi Ciaspolata + terme d'inverno sul canale bassa stagione.",
        cta="Attiva pacchetto inverno",
    ),
]
