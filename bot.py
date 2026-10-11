"""ETA News - calendario economico Forex Factory su Discord (Edge Trading Academy)."""
import json, os, sys, urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

FEED = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
WEBHOOK = os.environ.get("DISCORD_WEBHOOK", "")
MODE = (os.environ.get("MODE") or "auto").strip().lower()   # auto | oggi | settimana | test
DRY_RUN = os.environ.get("DRY_RUN") == "1"
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json")
FEED_FILE = os.environ.get("FEED_FILE")  # solo per test locali

# --- Impostazioni ---------------------------------------------------------
ROMA = ZoneInfo("Europe/Rome")
VALUTE = ["USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD", "CNY"]
IMPATTI = ["High", "Medium"]
ORA_RIEPILOGO = 7          # riepilogo del giorno alle 7:00 ora italiana (lun-ven)
ORA_SETTIMANA = 18         # calendario della settimana la domenica alle 18:00
AVVISO_MINUTI = 25         # avvisa se l'evento esce entro questi minuti
AVVISO_VALUTE = ["USD","EUR"]    # avvisi solo per queste valute
AVVISO_IMPATTI = ["High"]  # avvisi solo per questi impatti
COLORE = 0x0777FC          # blu ETA
FOOTER = "Edge Trading Academy · Dati: Forex Factory · Non è consulenza finanziaria"

BANDIERE = {"USD": "🇺🇸", "EUR": "🇪🇺", "GBP": "🇬🇧", "JPY": "🇯🇵", "CHF": "🇨🇭",
            "CAD": "🇨🇦", "AUD": "🇦🇺", "NZD": "🇳🇿", "CNY": "🇨🇳"}
PALLINO = {"High": "🔴", "Medium": "🟠"}
GIORNI = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]
MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
        "agosto", "settembre", "ottobre", "novembre", "dicembre"]


def log(*a):
    print(*a, flush=True)


def carica_feed():
    if FEED_FILE:
        return json.load(open(FEED_FILE))
    req = urllib.request.Request(FEED, headers={"User-Agent": "ETA-News-Bot/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def eventi(feed):
    out = []
    for e in feed:
        if e.get("country") not in VALUTE or e.get("impact") not in IMPATTI:
            continue
        try:
            dt = datetime.fromisoformat(e["date"]).astimezone(timezone.utc)
        except Exception:
            continue
        out.append({**e, "dt": dt, "id": f'{e["date"]}|{e["country"]}|{e["title"]}'})
    out.sort(key=lambda x: (x["dt"], 0 if x["impact"] == "High" else 1, x["country"]))
    return out


def ts(dt, fmt="t"):
    return f"<t:{int(dt.timestamp())}:{fmt}>"


def riga(e, con_ora=True):
    dati = []
    if e.get("forecast"):
        dati.append(f'atteso {e["forecast"]}')
    if e.get("previous"):
        dati.append(f'precedente {e["previous"]}')
    extra = f' · {" · ".join(dati)}' if dati else ""
    ora = f"`{e['dt'].astimezone(ROMA):%H:%M}` " if con_ora else ""
    return f'{ora}{PALLINO[e["impact"]]} {BANDIERE.get(e["country"], "")} **{e["country"]}** {e["title"]}{extra}'


def data_it(d):
    return f"{GIORNI[d.weekday()]} {d.day} {MESI[d.month - 1]}"


def invia(embed):
    payload = {"embeds": [embed], "allowed_mentions": {"parse": []}}
    if DRY_RUN or not WEBHOOK:
        log(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    req = urllib.request.Request(WEBHOOK, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json",
                                          "User-Agent": "ETA-News-Bot/1.0"})
    urllib.request.urlopen(req, timeout=30).read()


def embed(titolo, descr, fields=None):
    e = {"title": titolo, "description": descr, "color": COLORE, "footer": {"text": FOOTER}}
    if fields:
        e["fields"] = fields
    return e


# --- Messaggi ---------------------------------------------------------------
def riepilogo_oggi(ev, oggi):
    del_giorno = [e for e in ev if e["dt"].astimezone(ROMA).date() == oggi]
    if not del_giorno:
        return False
    righe = "\n".join(riga(e) for e in del_giorno)
    invia(embed(f"📅 Notizie di oggi · {data_it(oggi)}",
                f"{righe}\n\n*Orari in ora italiana. 🔴 alto impatto · 🟠 medio impatto*"))
    return True


def calendario_settimana(ev):
    giorni = {}
    for e in ev:
        giorni.setdefault(e["dt"].astimezone(ROMA).date(), []).append(e)
    if not giorni:
        invia(embed("🗓️ Calendario della settimana", "Nessuna notizia ad alto o medio impatto in calendario."))
        return
    fields = []
    for d in sorted(giorni)[:25]:
        testo = "\n".join(riga(e) for e in giorni[d])
        if len(testo) > 1024:
            testo = testo[:1000].rsplit("\n", 1)[0] + "\n…"
        fields.append({"name": data_it(d), "value": testo, "inline": False})
    alti = sum(1 for e in ev if e["impact"] == "High")
    invia(embed("🗓️ Calendario della settimana",
                f"**{alti}** notizie ad alto impatto e **{len(ev) - alti}** a medio impatto.\n"
                "*Orari in ora italiana. 🔴 alto impatto · 🟠 medio impatto*", fields))


def avvisi(ev, ora, stato):
    gia = set(stato.get("avvisati", []))
    da_avvisare = [e for e in ev if e["id"] not in gia
                   and e["country"] in AVVISO_VALUTE and e["impact"] in AVVISO_IMPATTI
                   and timedelta(0) < e["dt"] - ora <= timedelta(minutes=AVVISO_MINUTI)]
    gruppi = {}
    for e in da_avvisare:
        gruppi.setdefault(e["dt"], []).append(e)
    for dt, gruppo in sorted(gruppi.items()):
        righe = "\n".join(riga(e, con_ora=False) for e in gruppo)
        invia(embed("🔴 Notizia importante in arrivo",
                    f"Esce **{ts(dt, 'R')}**, alle {ts(dt)} (nel tuo orario)\n\n{righe}\n\n"
                    "*Spread più larghi e movimenti bruschi: valuta se restare fuori dal mercato.*"))
        gia.update(e["id"] for e in gruppo)
    # tieni solo gli id degli ultimi 14 giorni
    limite = ora - timedelta(days=14)
    stato["avvisati"] = sorted(i for i in gia if datetime.fromisoformat(i.split("|")[0]) >= limite)


# --- Main -------------------------------------------------------------------
def main():
    stato = {}
    if os.path.exists(STATE_FILE):
        try:
            stato = json.load(open(STATE_FILE))
        except Exception:
            stato = {}
    try:
        ev = eventi(carica_feed())
    except Exception as ex:
        log("Feed non disponibile:", ex)
        return 0

    ora = datetime.fromisoformat(os.environ["NOW_ISO"]) if os.environ.get("NOW_ISO") else datetime.now(timezone.utc)
    ora = ora.astimezone(timezone.utc)
    roma = ora.astimezone(ROMA)
    oggi = roma.date()

    if MODE == "test":
        invia(embed("✅ ETA News è attivo",
                    "Da ora in questo canale arrivano:\n"
                    f"• il riepilogo delle notizie del giorno alle {ORA_RIEPILOGO}:00 (lun-ven)\n"
                    f"• il calendario della settimana la domenica alle {ORA_SETTIMANA}:00\n"
                    "• un avviso prima di ogni notizia importante (alto impatto USA)"))
        return 0
    if MODE == "oggi":
        if not riepilogo_oggi(ev, oggi):
            invia(embed(f"📅 Notizie di oggi · {data_it(oggi)}", "Nessuna notizia ad alto o medio impatto oggi."))
        return 0
    if MODE == "settimana":
        calendario_settimana(ev)
        return 0

    # Modalità automatica
    if roma.weekday() < 5 and roma.hour >= ORA_RIEPILOGO and stato.get("riepilogo") != str(oggi):
        riepilogo_oggi(ev, oggi)
        stato["riepilogo"] = str(oggi)
    if roma.weekday() == 6 and roma.hour >= ORA_SETTIMANA and stato.get("settimana") != str(oggi):
        calendario_settimana(ev)
        stato["settimana"] = str(oggi)
    avvisi(ev, ora, stato)

    with open(STATE_FILE, "w") as f:
        json.dump(stato, f, indent=2, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
