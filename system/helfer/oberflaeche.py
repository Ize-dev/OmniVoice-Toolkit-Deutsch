#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Deutsche Bedienoberflaeche fuer OmniVoice - laeuft INNERHALB der venv.

Ersetzt die englische Standard-Oberflaeche (omnivoice-demo) durch eine
aufgeraeumte deutsche Fassung mit drei Betriebsarten:

  * Stimme klonen  - Sprachprobe hochladen oder aufnehmen, Text sprechen lassen
  * Ueberraschung  - das Modell sucht sich selbst eine Stimme aus
  * Stapel (Batch) - ganze Projekte ueber eine CSV-Liste vertonen

Aufruf:
    python oberflaeche.py --ip 127.0.0.1 --port 7860 --ausgabe <ordner>

Rueckgabecodes:
    0  normal beendet
    4  diese Oberflaeche ist nicht startbar -> das Studio faellt auf die
       mitgelieferte Standard-Oberflaeche zurueck
"""

import argparse
import csv
import html
import io
import json
import os
import sys
import threading
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import messwerte  # noqa: E402
from motor import (ABTASTRATE, MODELL, MOTOR, als_array, audiolaenge,  # noqa: E402
                   empfohlene_arbeiter, sag, schreibe_wav)
from pool import VERWALTUNG  # noqa: E402

EXIT_NICHT_STARTBAR = 4

AUDIO_ENDUNGEN = {".wav", ".mp3", ".flac", ".ogg", ".opus", ".m4a", ".aac", ".wma", ".aiff", ".wem"}

BEISPIEL_TEXT = (
    "Das hier ist meine geklonte Stimme. "
    "Sie spricht jeden Text, den ich eingebe – und das komplett auf diesem Rechner."
)

BEISPIEL_CSV = (
    "C:\\Projekte\\Habitat\\content\\audio\\wwise\\stimme.wav;"
    "This is the original English line.;Das ist die deutsche Zeile."
)

# ------------------------------------------------------------
# Aussehen
# ------------------------------------------------------------

CSS = """
:root {
    --ize-magenta: #ff4fd8;
    --ize-cyan: #22e0ff;
    --ize-blau: #4d9bff;
    --ize-tief: #0b0d15;
}
.gradio-container {
    background: radial-gradient(1400px 700px at 12% -10%, #1d2136 0%, var(--ize-tief) 60%) fixed !important;
    max-width: 100% !important;
    width: 100% !important;
    padding-left: 20px !important;
    padding-right: 20px !important;
}
.gradio-container > .main, .gradio-container .wrap, .app { max-width: 100% !important; }
#ize-kopf {
    border: 1px solid rgba(34, 224, 255, .35);
    border-radius: 14px;
    padding: 16px 22px 12px 22px;
    margin-bottom: 6px;
    background: linear-gradient(135deg, rgba(255,79,216,.10), rgba(34,224,255,.07));
    box-shadow: 0 0 40px rgba(255, 79, 216, .10);
}
#ize-kopf h1 {
    margin: 0; font-size: 26px; letter-spacing: .34em; font-weight: 800;
    background: linear-gradient(90deg, var(--ize-magenta), var(--ize-cyan));
    -webkit-background-clip: text; background-clip: text; color: transparent;
}
#ize-kopf p { margin: 6px 0 0 0; font-size: 13.5px; opacity: .78; }
#ize-streifen {
    height: 3px; margin-top: 12px; border-radius: 3px;
    background: linear-gradient(90deg, var(--ize-magenta), var(--ize-cyan), var(--ize-magenta));
    background-size: 200% 100%; animation: ize-fluss 6s linear infinite;
}
@keyframes ize-fluss { from { background-position: 0 0; } to { background-position: 200% 0; } }
#ize-fuss {
    text-align: center; font-size: 12px; opacity: .6; padding: 14px 0 4px 0; letter-spacing: .08em;
}
#ize-fuss b { color: var(--ize-blau); letter-spacing: .25em; font-weight: 800; }
.ize-karte {
    border: 1px solid rgba(255,255,255,.08) !important;
    border-radius: 12px !important;
    background: rgba(20, 24, 38, .55) !important;
    padding: 14px !important;
}
#ize-los, #ize-stapel-los { font-size: 17px !important; font-weight: 700 !important; letter-spacing: .06em; }
.ize-tipp { font-size: 12.5px; opacity: .7; line-height: 1.65; }

/* ---------- Stapel-Anzeige ---------- */
.ize-batch {
    border: 1px solid rgba(34,224,255,.28); border-radius: 14px; padding: 16px 18px 14px 18px;
    background: linear-gradient(160deg, rgba(34,224,255,.06), rgba(255,79,216,.05));
}
.ize-batch-kopf { display: flex; justify-content: space-between; align-items: baseline; gap: 16px; flex-wrap: wrap; }
.ize-batch-titel { font-size: 15px; font-weight: 800; letter-spacing: .22em; color: var(--ize-cyan); }
.ize-batch-titel.fertig { color: #46e08a; }
.ize-batch-titel.fehler { color: #ff6b6b; }
.ize-batch-datei { font-size: 12.5px; opacity: .72; font-family: ui-monospace, Consolas, monospace;
                   overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 62%; }
.ize-bar { height: 16px; border-radius: 8px; margin: 12px 0 4px 0; overflow: hidden;
           background: rgba(255,255,255,.07); box-shadow: inset 0 0 8px rgba(0,0,0,.45); }
.ize-bar-fuell {
    height: 100%; border-radius: 8px; transition: width .35s ease;
    background: linear-gradient(90deg, var(--ize-magenta, #ff4fd8),
                                       var(--ize-blau, #4d9bff),
                                       var(--ize-cyan, #22e0ff));
    background-size: 250% 100%; animation: ize-fluss 3.5s linear infinite;
    box-shadow: 0 0 18px rgba(77,155,255,.55);
}
/* Fertiger Stapel: ruhiges Blau mit Glow, passend zum iZE in der Fußzeile. */
.ize-bar-fuell.fertig {
    background: linear-gradient(90deg, #2f7dff, #4d9bff, #8ecbff);
    background-size: 100% 100%;
    animation: ize-glimmen 2.6s ease-in-out infinite;
    box-shadow: 0 0 22px rgba(77,155,255,.85), 0 0 48px rgba(77,155,255,.40);
}
@keyframes ize-glimmen {
    0%, 100% { box-shadow: 0 0 18px rgba(77,155,255,.65), 0 0 36px rgba(77,155,255,.28); }
    50%      { box-shadow: 0 0 26px rgba(77,155,255,.95), 0 0 56px rgba(77,155,255,.50); }
}
.ize-grid {
    display: grid; grid-template-columns: repeat(auto-fit, minmax(112px, 1fr));
    gap: 10px; margin-top: 14px;
}
.ize-grid > div {
    background: rgba(0,0,0,.28); border: 1px solid rgba(255,255,255,.06);
    border-radius: 10px; padding: 9px 11px;
}
.ize-grid b { display: block; font-size: 19px; font-weight: 800; color: #eaf2ff; line-height: 1.25; }
.ize-grid span { display: block; font-size: 11px; opacity: .62; letter-spacing: .06em; margin-top: 2px; }
.ize-grid .warn b { color: #ffc857; }
.ize-grid .schlecht b { color: #ff6b6b; }
footer { display: none !important; }
"""

KOPF_HTML = """
<div id="ize-kopf">
  <h1>OMNIVOICE STUDIO</h1>
  <p>Stimmen klonen und Sprache erzeugen – komplett auf diesem Rechner.
     Nichts wird hochgeladen, nichts gespeichert außer deinen eigenen Ergebnissen.</p>
  <div id="ize-streifen"></div>
</div>
"""

FUSS_HTML = """
<div id="ize-fuss">
  OMNIVOICE STUDIO · deutsche Fassung von <b>iZE</b> · läuft lokal auf {geraet}<br>
  Modell: k2-fsa/OmniVoice · Ausgabe: 24 kHz Mono
</div>
"""

# Laeuft im Browser, sobald ein Stapel durch ist: kurzer Dreiklang und optional
# eine Benachrichtigung des Betriebssystems. Der Ton wird per WebAudio erzeugt,
# damit keine Tondatei mitgeliefert werden muss.
MELDUNG_JS = """
(ton, hinweis, blinken, protokoll) => {
  try {
    const zeilen = String(protokoll || "").trim().split("\\n").reverse();
    const text = (zeilen.find(z => z.startsWith("FERTIG:")) || "Der Stapel ist durch.").trim();
    if (blinken && !document.hasFocus()) {
      const alt = window.__izeTitel || document.title;
      window.__izeTitel = alt;
      if (window.__izeBlinken) clearInterval(window.__izeBlinken);
      let an = false;
      window.__izeBlinken = setInterval(() => {
        an = !an;
        document.title = an ? "✅ FERTIG · OmniVoice" : alt;
      }, 900);
      const aufhoeren = () => {
        clearInterval(window.__izeBlinken);
        window.__izeBlinken = null;
        document.title = alt;
        window.removeEventListener("focus", aufhoeren);
        document.removeEventListener("visibilitychange", aufhoeren);
      };
      window.addEventListener("focus", aufhoeren);
      document.addEventListener("visibilitychange", aufhoeren);
      setTimeout(aufhoeren, 120000);
    }
    if (ton) {
      const Klang = window.AudioContext || window.webkitAudioContext;
      if (Klang) {
        const ctx = new Klang();
        [660, 880, 1320].forEach((hz, i) => {
          const t0 = ctx.currentTime + i * 0.16;
          const o = ctx.createOscillator(), g = ctx.createGain();
          o.type = "sine"; o.frequency.value = hz;
          g.gain.setValueAtTime(0.0001, t0);
          g.gain.exponentialRampToValueAtTime(0.22, t0 + 0.03);
          g.gain.exponentialRampToValueAtTime(0.0001, t0 + 0.30);
          o.connect(g); g.connect(ctx.destination);
          o.start(t0); o.stop(t0 + 0.32);
        });
        setTimeout(() => { try { ctx.close(); } catch (e) {} }, 2500);
      }
    }
    if (hinweis && "Notification" in window) {
      const zeigen = () => new Notification("OmniVoice Studio", {
        body: text, tag: "ize-stapel", requireInteraction: false });
      if (Notification.permission === "granted") { zeigen(); }
      else if (Notification.permission !== "denied") {
        Notification.requestPermission().then(p => { if (p === "granted") zeigen(); });
      }
    }
  } catch (e) { console.warn("OmniVoice-Benachrichtigung:", e); }
}
"""

ERLAUBNIS_JS = """
(an) => {
  try {
    if (an && "Notification" in window && Notification.permission === "default") {
      Notification.requestPermission();
    }
  } catch (e) {}
}
"""

# Gradio waehlt seine Sprache allein anhand von navigator.language. Das hier
# wird in den <head> gehaengt und laeuft damit VOR dem Programmteil von Gradio -
# so ist die Oberflaeche auch dann deutsch, wenn der Browser auf Englisch steht.
SPRACHE_HEAD = """
<script>
  try {
    Object.defineProperty(navigator, "language",
      { get: () => "de-DE", configurable: true });
    Object.defineProperty(navigator, "languages",
      { get: () => ["de-DE", "de"], configurable: true });
    document.documentElement.lang = "de";
  } catch (e) {}
</script>
"""

# Ein paar Texte sind in Gradio fest eingebaut und lassen sich nicht
# uebersetzen ("processing |", "queue: 1/3 |"). Die werden hier im laufenden
# Betrieb ersetzt, sobald sie auftauchen.
UEBERSETZUNG_JS = """
() => {
  const ersetzungen = [
    [/\\bprocessing \\|/g, "wird berechnet |"],
    [/\\bqueue: /g, "Warteschlange: "],
    [/^\\s*Processing\\s*$/g, "Wird berechnet"],
    [/^\\s*Loading\\.\\.\\.\\s*$/g, "Wird geladen …"],
    [/^\\s*Waiting\\s*$/g, "Warten"],
  ];
  const behandeln = (knoten) => {
    if (!knoten) return;
    if (knoten.nodeType === 3) {
      let text = knoten.nodeValue;
      if (!text) return;
      let neu = text;
      for (const [muster, ersatz] of ersetzungen) neu = neu.replace(muster, ersatz);
      if (neu !== text) knoten.nodeValue = neu;
    } else if (knoten.nodeType === 1 && knoten.childNodes) {
      knoten.childNodes.forEach(behandeln);
    }
  };
  try {
    const beobachter = new MutationObserver((eintraege) => {
      for (const eintrag of eintraege) {
        if (eintrag.type === "characterData") behandeln(eintrag.target);
        else eintrag.addedNodes.forEach(behandeln);
      }
    });
    beobachter.observe(document.body,
      { childList: true, subtree: true, characterData: true });
    behandeln(document.body);
  } catch (e) { console.warn("OmniVoice-Übersetzung:", e); }
}
"""


# ------------------------------------------------------------
# Kleine Helfer
# ------------------------------------------------------------


def komma(wert: float, stellen: int = 1) -> str:
    return f"{wert:.{stellen}f}".replace(".", ",")


# ------------------------------------------------------------
# Einstellungen (bleiben ueber Neustarts erhalten)
# ------------------------------------------------------------

STANDARD_EINSTELLUNGEN = {
    "arbeiter": 1,
    "qualitaet": 32,
    "tempo": 1.0,
    "wurzel": "",
    "ausgabe": "",
    "ueberspringen": True,
    "dauer_von_probe": False,
    "monitor": True,
    "ton": True,
    "hinweis": False,
    "blinken": True,
    "bericht": True,
    "autoplay": False,
}


def lies_einstellungen(pfad: Path) -> dict:
    werte = dict(STANDARD_EINSTELLUNGEN)
    try:
        if pfad.exists():
            gespeichert = json.loads(pfad.read_text(encoding="utf-8"))
            if isinstance(gespeichert, dict):
                werte.update({k: v for k, v in gespeichert.items() if k in werte})
    except Exception as fehler:
        sag(f"Hinweis: Einstellungen konnten nicht gelesen werden ({fehler}).")
    return werte


def schreibe_einstellungen(pfad: Path, werte: dict) -> str:
    try:
        pfad.parent.mkdir(parents=True, exist_ok=True)
        pfad.write_text(json.dumps(werte, indent=2, ensure_ascii=False), encoding="utf-8")
        return f"✅  Gespeichert in `{pfad}`"
    except Exception as fehler:
        return f"❌  Speichern nicht möglich: {fehler}"


def dauer_text(sekunden: float) -> str:
    sekunden = max(0.0, float(sekunden))
    if sekunden < 60:
        return f"{komma(sekunden)} s"
    minuten, rest = divmod(int(sekunden), 60)
    stunden, minuten = divmod(minuten, 60)
    if stunden:
        return f"{stunden}:{minuten:02d}:{rest:02d}"
    return f"{minuten}:{rest:02d}"


def uhrzeit_text(in_sekunden: float) -> str:
    """Voraussichtliche Fertigstellung als Uhrzeit."""
    if in_sekunden <= 0 or in_sekunden > 60 * 60 * 48:
        return "–"
    ziel = time.localtime(time.time() + in_sekunden)
    jetzt = time.localtime()
    text = time.strftime("%H:%M", ziel)
    if ziel.tm_yday != jetzt.tm_yday:
        text = "morgen " + text
    return text + " Uhr"


# ------------------------------------------------------------
# CSV-Verarbeitung fuer den Stapelbetrieb
# ------------------------------------------------------------

def lies_csv(pfad: str) -> list[list[str]]:
    """Liest die Liste ein: Trennzeichen, Kodierung und Kopfzeile werden erkannt."""
    rohtext = None
    for kodierung in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            rohtext = Path(pfad).read_text(encoding=kodierung)
            break
        except UnicodeDecodeError:
            continue
        except OSError as fehler:
            raise RuntimeError(f"Die Liste ließ sich nicht öffnen: {fehler}")
    if rohtext is None:
        raise RuntimeError("Die Textkodierung der Liste wurde nicht erkannt.")

    probe = rohtext[:8192]
    try:
        trenner = csv.Sniffer().sniff(probe, delimiters=";,\t|").delimiter
    except csv.Error:
        trenner = max(";,\t|", key=probe.count)

    zeilen = []
    for felder in csv.reader(io.StringIO(rohtext), delimiter=trenner):
        felder = [f.strip().strip('"').strip() for f in felder]
        if any(felder):
            zeilen.append(felder)

    if zeilen and not sieht_nach_datei_aus(zeilen[0][0]):
        zeilen = zeilen[1:]          # Kopfzeile überspringen
    return zeilen


def sieht_nach_datei_aus(text: str) -> bool:
    if not text:
        return False
    if Path(text).suffix.lower() in AUDIO_ENDUNGEN:
        return True
    return ("\\" in text or "/" in text) and Path(text).suffix != ""


def loese_quelle(eintrag: str, wurzel: str) -> Path:
    pfad = Path(eintrag.strip().strip('"'))
    if not pfad.is_absolute() and wurzel.strip():
        pfad = Path(wurzel.strip()) / pfad
    return pfad


def erkenne_wurzel(quellen: list[Path]) -> Path:
    """Ohne Angabe: den gemeinsamen Ordner aller Dateien als Projektstart nehmen."""
    vorhanden = [str(p.resolve()) for p in quellen if p.exists()]
    if not vorhanden:
        vorhanden = [str(p) for p in quellen]
    if not vorhanden:
        return Path.cwd()
    try:
        return Path(os.path.commonpath(vorhanden))
    except ValueError:
        return Path(vorhanden[0]).parent


def zielpfad(quelle: Path, wurzel: Path, basis: Path) -> Path:
    """Spiegelt den Pfad unterhalb der Wurzel in den Ausgabeordner."""
    try:
        rel = quelle.resolve().relative_to(wurzel.resolve())
    except (ValueError, OSError):
        rel = Path(quelle.name)
    return (basis / rel).with_suffix(".wav")


# ------------------------------------------------------------
# Fancy Stapel-Anzeige
# ------------------------------------------------------------

def batch_html(zustand: str, datei: str, erledigt: int, gesamt: int, fehler: int,
               vergangen: float, rest: float, pro_datei: float, tonlaenge: float,
               arbeiter: str = "") -> str:
    anteil = (erledigt / gesamt * 100.0) if gesamt else 0.0
    titel = {"laeuft": "STAPEL LÄUFT", "fertig": "STAPEL FERTIG", "start": "STAPEL STARTET",
             "abbruch": "STAPEL ANGEHALTEN", "fehler": "STAPEL ABGEBROCHEN"}.get(zustand, "STAPEL")
    klasse = {"fertig": " fertig", "fehler": " fehler", "abbruch": " fehler"}.get(zustand, "")
    laeuft = zustand in ("laeuft", "start")
    pro_minute = (erledigt / vergangen * 60.0) if vergangen > 0 and erledigt else 0.0
    faktor = (tonlaenge / vergangen) if vergangen > 0 and tonlaenge else 0.0

    felder = [
        (f"{erledigt} <span style='opacity:.45'>/ {gesamt}</span>", "Dateien erledigt", ""),
        (f"{komma(anteil)} %", "geschafft", ""),
        (dauer_text(vergangen), "vergangen", ""),
        (dauer_text(rest) if laeuft and rest else "–", "Restzeit", ""),
        (uhrzeit_text(rest) if laeuft else "–", "fertig gegen", ""),
        (f"{komma(pro_datei)} s", "pro Datei", ""),
        (f"{komma(pro_minute)}", "Dateien/Minute", ""),
        (f"{komma(faktor)}×", "schneller als Echtzeit", ""),
        (str(fehler), "Fehler", "schlecht" if fehler else ""),
    ]
    if arbeiter:
        felder.insert(5, (arbeiter, "Arbeiter aktiv", ""))
    kacheln = "".join(
        f"<div class='{klasse_kachel}'><b>{wert}</b><span>{beschriftung}</span></div>"
        for wert, beschriftung, klasse_kachel in felder
    )
    # Der Balken traegt sich komplett selbst: Hoehe, Rundung, Farbe und Glow
    # stehen direkt am Element. Damit haengt die Anzeige weder an den
    # CSS-Variablen noch daran, ob Gradio das eingebettete Stylesheet an
    # dieser Stelle ueberhaupt anwendet. Die Klasse steuert nur noch die
    # Animation - fehlt sie, bleibt der Balken trotzdem farbig.
    if zustand == "fertig":
        fuell_klasse = " fertig"
        farbe = "linear-gradient(90deg,#2f7dff,#4d9bff,#8ecbff)"
        glut = "0 0 22px rgba(77,155,255,.85),0 0 48px rgba(77,155,255,.40)"
    elif zustand in ("fehler", "abbruch"):
        fuell_klasse = ""
        farbe = "linear-gradient(90deg,#c2455f,#ff6b6b,#ffa07a)"
        glut = "0 0 18px rgba(255,107,107,.60)"
    else:
        fuell_klasse = ""
        farbe = "linear-gradient(90deg,#ff4fd8,#4d9bff,#22e0ff) 0 0 / 250% 100%"
        glut = "0 0 20px rgba(77,155,255,.65)"
    fuell_stil = (f"width:{max(0.8, anteil):.2f}%;height:100%;border-radius:8px;"
                  f"background:{farbe};box-shadow:{glut};")
    return f"""
<div class="ize-batch">
  <div class="ize-batch-kopf">
    <span class="ize-batch-titel{klasse}">{titel}</span>
    <span class="ize-batch-datei">{html.escape(datei or "–")}</span>
  </div>
  <div class="ize-bar" style="height:16px;border-radius:8px;overflow:hidden;
       background:rgba(255,255,255,.07);margin:12px 0 4px 0">
    <div class="ize-bar-fuell{fuell_klasse}" style="{fuell_stil}"></div>
  </div>
  <div class="ize-grid">{kacheln}</div>
</div>
"""


LEERE_ANZEIGE = batch_html("bereit", "noch nichts gestartet", 0, 0, 0, 0, 0, 0, 0)


# ------------------------------------------------------------
# Stapelbetrieb (ohne Gradio testbar)
# ------------------------------------------------------------

# Solange ein Stapel laeuft, sind Pruefung und ein zweiter Start gesperrt.
# Der Zustand haengt am Server, gilt also auch fuer weitere Browserfenster.
STAPEL_LAEUFT = threading.Event()


def pruefe_liste(csv_datei, wurzel, ziel_basis, standard_basis: Path) -> str:
    """Liest die Liste probeweise und meldet, was daraus wuerde."""
    if STAPEL_LAEUFT.is_set():
        return ("⏳  Es läuft gerade ein Stapel. Die Prüfung ist so lange gesperrt – "
                "bitte abwarten oder oben auf »Anhalten« drücken.")
    if not csv_datei:
        return "⚠️  Bitte zuerst eine CSV-Liste auswählen."
    pfad = csv_datei if isinstance(csv_datei, str) else getattr(csv_datei, "name", "")
    try:
        zeilen = lies_csv(pfad)
    except Exception as fehler:
        return f"❌  {fehler}"
    if not zeilen:
        return "⚠️  In der Liste steht keine einzige Zeile."

    quellen = [loese_quelle(z[0], wurzel) for z in zeilen if z and z[0]]
    fehlen = [p for p in quellen if not p.exists()]
    genutzte_wurzel = Path(wurzel.strip()) if wurzel.strip() else erkenne_wurzel(quellen)
    basis = Path(ziel_basis.strip()) if ziel_basis.strip() else standard_basis
    spalten = max(len(z) for z in zeilen)

    bericht = [
        f"**{len(zeilen)} Zeilen** gefunden, {spalten} Spalten erkannt.",
        f"**{len(quellen) - len(fehlen)}** Audiodateien vorhanden, **{len(fehlen)}** fehlen.",
        f"Projektstart: `{genutzte_wurzel}`"
        + ("  *(automatisch erkannt)*" if not wurzel.strip() else ""),
    ]
    if spalten < 3:
        bericht.append("ℹ️  Nur zwei Spalten – der englische Text fehlt. "
                       "OmniVoice hört die Sprachprobe dann selbst ab.")
    if quellen:
        bericht.append(f"Beispiel-Ziel: `{zielpfad(quellen[0], genutzte_wurzel, basis)}`")
    for fehlende in fehlen[:5]:
        bericht.append(f"❌ fehlt: `{fehlende}`")
    if len(fehlen) > 5:
        bericht.append(f"… und {len(fehlen) - 5} weitere.")
    if not fehlen:
        bericht.append("✅  Alles bereit – der Stapel kann losgehen.")
    return "\n\n".join(bericht)


def stapel_durchlauf(csv_datei, wurzel, ziel_basis, ueberspringen,
                     schritte, tempo, standard_basis: Path, arbeiterzahl: int = 1,
                     dauer_von_probe: bool = False, bericht_schreiben: bool = True):
    """
    Klammer um den eigentlichen Durchlauf: setzt die Sperre und nimmt sie am
    Ende in jedem Fall wieder weg - auch beim Anhalten mitten im Lauf.
    """
    if STAPEL_LAEUFT.is_set():
        yield (batch_html("fehler", "es läuft bereits ein Stapel", 0, 0, 0, 0, 0, 0, 0),
               "Es läuft bereits ein Stapel. Bitte diesen erst beenden.", None)
        return
    STAPEL_LAEUFT.set()
    try:
        yield from stapel_arbeiten(csv_datei, wurzel, ziel_basis, ueberspringen, schritte,
                                   tempo, standard_basis, arbeiterzahl, dauer_von_probe,
                                   bericht_schreiben)
    finally:
        STAPEL_LAEUFT.clear()


def stapel_arbeiten(csv_datei, wurzel, ziel_basis, ueberspringen,
                    schritte, tempo, standard_basis: Path, arbeiterzahl: int = 1,
                    dauer_von_probe: bool = False, bericht_schreiben: bool = True):
    """
    Arbeitet die Liste ab und liefert laufend (Anzeige, Protokoll, Bericht).

    Die eigentliche Erzeugung uebernimmt ein »Betrieb«: entweder der
    Hauptprozess (1 Arbeiter) oder mehrere eigene Prozesse. Nach jeder
    fertigen Datei - und mindestens zweimal pro Sekunde - wird der Zustand
    gemeldet, damit Fortschritt und Restzeit live mitlaufen.
    """
    protokoll: list[str] = []
    beginn = time.time()
    tonlaenge = 0.0

    def hole_meldungen(betrieb) -> None:
        while True:
            try:
                protokoll.append(betrieb.meldungen.get_nowait())
            except Exception:
                return

    def anzeige(zustand, datei, erledigt, gesamt, fehler, betrieb=None):
        vergangen = time.time() - beginn
        pro_datei = (vergangen / erledigt) if erledigt else 0.0
        rest = pro_datei * (gesamt - erledigt) if erledigt else 0.0
        arbeiter_text = ""
        if betrieb is not None:
            if getattr(betrieb, "art", "") == "pool":
                arbeiter_text = f"{betrieb.beschaeftigt()} <span style='opacity:.45'>/ " \
                                f"{betrieb.anzahl}</span>"
            else:
                arbeiter_text = "1 <span style='opacity:.45'>/ 1</span>"
        return (batch_html(zustand, datei, erledigt, gesamt, fehler, vergangen, rest,
                           pro_datei, tonlaenge, arbeiter_text),
                "\n".join(protokoll[-400:]))

    def abbruchanzeige(text, fehlerzahl=1):
        return batch_html("fehler", text, 0, 0, fehlerzahl, 0, 0, 0, 0), "\n".join(protokoll), None

    if not csv_datei:
        protokoll.append("Keine CSV-Liste ausgewählt.")
        yield abbruchanzeige("keine Liste")
        return

    pfad = csv_datei if isinstance(csv_datei, str) else getattr(csv_datei, "name", "")
    try:
        zeilen = lies_csv(pfad)
    except Exception as fehler:
        protokoll.append(f"FEHLER: {fehler}")
        yield abbruchanzeige("Liste unlesbar")
        return
    if not zeilen:
        protokoll.append("In der Liste steht keine einzige Zeile.")
        yield abbruchanzeige("Liste leer")
        return

    quellen = [loese_quelle(z[0], wurzel) for z in zeilen if z and z[0]]
    genutzte_wurzel = Path(wurzel.strip()) if wurzel.strip() else erkenne_wurzel(quellen)
    basis = Path(ziel_basis.strip()) if ziel_basis.strip() else standard_basis
    gesamt = len(zeilen)
    arbeiterzahl = max(1, int(arbeiterzahl))

    protokoll.append(f"Liste       : {pfad}")
    protokoll.append(f"Zeilen      : {gesamt}")
    protokoll.append(f"Projektstart: {genutzte_wurzel}")
    protokoll.append(f"Ausgabe     : {basis}")
    protokoll.append(f"Arbeiter    : {arbeiterzahl}"
                     + ("" if arbeiterzahl > 1 else " (im Hauptprozess)"))
    if dauer_von_probe:
        protokoll.append("Länge       : je Zeile so lang wie die englische Aufnahme")
    protokoll.append("")
    yield anzeige("start", "Liste wird geprüft …", 0, gesamt, 0) + (None,)

    # ---------------- Vorlauf: prüfen, was überhaupt zu tun ist
    auftraege: list[dict] = []
    eintraege: dict[int, tuple] = {}
    erledigt = anzahl_fehler = 0

    for nummer, felder in enumerate(zeilen, start=1):
        quelle = loese_quelle(felder[0], wurzel)
        if len(felder) == 2:
            englisch, deutsch = "", felder[1].strip()
        else:
            englisch = felder[1].strip() if len(felder) > 1 else ""
            deutsch = felder[2].strip() if len(felder) > 2 else ""
        ziel = zielpfad(quelle, genutzte_wurzel, basis)

        if not deutsch:
            anzahl_fehler += 1
            erledigt += 1
            protokoll.append(f"[{nummer}/{gesamt}] übersprungen (kein deutscher Text): {quelle.name}")
            eintraege[nummer] = (str(quelle), str(ziel), "fehler", "kein deutscher Text", "0")
        elif not quelle.exists():
            anzahl_fehler += 1
            erledigt += 1
            protokoll.append(f"[{nummer}/{gesamt}] fehlt: {quelle}")
            eintraege[nummer] = (str(quelle), str(ziel), "fehler", "Audiodatei fehlt", "0")
        elif ueberspringen and ziel.exists():
            erledigt += 1
            protokoll.append(f"[{nummer}/{gesamt}] schon vorhanden: {ziel.name}")
            eintraege[nummer] = (str(quelle), str(ziel), "übersprungen", "bereits vorhanden", "0")
        else:
            auftraege.append({"id": nummer, "text": deutsch, "ref_audio": str(quelle),
                              "ref_text": englisch, "num_step": int(schritte),
                              "speed": float(tempo), "ziel": str(ziel),
                              "dauer_von_probe": bool(dauer_von_probe),
                              "name": quelle.name})

    protokoll.append("")
    protokoll.append(f"Zu erzeugen: {len(auftraege)} von {gesamt} Zeilen.")
    yield anzeige("start", f"{len(auftraege)} Dateien vorgemerkt", erledigt, gesamt,
                  anzahl_fehler) + (None,)

    offen: dict[int, dict] = {}
    betrieb = None
    try:
        if auftraege:
            # ---------------- Arbeiter bereitstellen
            betrieb = VERWALTUNG.betrieb(arbeiterzahl)
            hole_meldungen(betrieb)
            wartete = time.time()
            while betrieb.bereit_anzahl() == 0 and betrieb.lebende() > 0:
                hole_meldungen(betrieb)
                yield anzeige("start",
                              f"Arbeiter werden vorbereitet – {betrieb.bereit_anzahl()} von "
                              f"{betrieb.anzahl} bereit ({dauer_text(time.time() - wartete)})",
                              erledigt, gesamt, anzahl_fehler, betrieb) + (None,)
                time.sleep(0.5)
            if betrieb.lebende() == 0:
                protokoll.append("FEHLER: Es konnte kein Arbeiter gestartet werden.")
                yield abbruchanzeige("kein Arbeiter verfügbar")
                return
            hole_meldungen(betrieb)

            # ---------------- Verteilen und einsammeln
            naechster = 0
            while naechster < len(auftraege) or offen:
                while naechster < len(auftraege):
                    platz = betrieb.freier()
                    if platz is None:
                        break
                    auftrag = auftraege[naechster]
                    betrieb.sende(platz, auftrag)
                    offen[auftrag["id"]] = auftrag
                    naechster += 1

                if not offen and betrieb.lebende() == 0:
                    protokoll.append("FEHLER: Alle Arbeiter sind ausgefallen.")
                    break

                ergebnis = betrieb.antwort(timeout=0.4)
                hole_meldungen(betrieb)
                if ergebnis is None:
                    yield anzeige("laeuft", f"{len(offen)} Datei(en) in Arbeit",
                                  erledigt, gesamt, anzahl_fehler, betrieb) + (None,)
                    continue

                auftrag = offen.pop(ergebnis.get("id"), None)
                if auftrag is None:
                    continue
                nummer = auftrag["id"]
                erledigt += 1
                if ergebnis.get("ok"):
                    tonlaenge += float(ergebnis.get("ton", 0.0))
                    protokoll.append(
                        f"[{nummer}/{gesamt}] ✔ {Path(auftrag['ziel']).name}  "
                        f"({dauer_text(ergebnis.get('sekunden', 0))}, "
                        f"{dauer_text(ergebnis.get('ton', 0))} Ton)")
                    eintraege[nummer] = (auftrag["ref_audio"], auftrag["ziel"], "ok", "",
                                         komma(float(ergebnis.get("sekunden", 0.0))))
                else:
                    anzahl_fehler += 1
                    protokoll.append(f"[{nummer}/{gesamt}] ✖ {auftrag['name']}: "
                                     f"{ergebnis.get('fehler', 'unbekannter Fehler')}")
                    eintraege[nummer] = (auftrag["ref_audio"], auftrag["ziel"], "fehler",
                                         str(ergebnis.get("fehler", "")), "0")
                yield anzeige("laeuft", auftrag["name"], erledigt, gesamt,
                              anzahl_fehler, betrieb) + (None,)
    finally:
        # Beim Anhalten laufende Auftraege noch einsammeln, damit die Arbeiter
        # danach wieder frei sind und nicht in der Luft haengen.
        if betrieb is not None and offen:
            def nachlesen(rest_offen):
                ende = time.time() + 300
                while rest_offen and time.time() < ende:
                    antwort = betrieb.antwort(timeout=1.0)
                    if antwort is not None:
                        rest_offen.pop(antwort.get("id"), None)

            threading.Thread(target=nachlesen, args=(dict(offen),), daemon=True).start()

    # ---------------- Bericht schreiben
    bericht_datei = None
    if bericht_schreiben:
        try:
            basis.mkdir(parents=True, exist_ok=True)
            bericht_datei = basis / time.strftime("_bericht_%Y-%m-%d_%H-%M-%S.csv")
            with open(bericht_datei, "w", encoding="utf-8-sig", newline="") as datei:
                schreiber = csv.writer(datei, delimiter=";")
                schreiber.writerow(("zeile", "quelle", "ziel", "status", "meldung", "sekunden"))
                for nummer in sorted(eintraege):
                    schreiber.writerow((nummer,) + eintraege[nummer])
            protokoll.append("")
            protokoll.append(f"Bericht geschrieben: {bericht_datei}")
        except Exception as fehler:
            bericht_datei = None
            protokoll.append(f"Bericht konnte nicht geschrieben werden: {fehler}")

    vergangen = time.time() - beginn
    gelungen = erledigt - anzahl_fehler
    protokoll.append("")
    protokoll.append(f"FERTIG: {gelungen} von {gesamt} Dateien in {dauer_text(vergangen)}, "
                     f"{anzahl_fehler} Fehler.")
    if betrieb is not None and getattr(betrieb, "art", "") == "pool":
        protokoll.append(f"Die {betrieb.anzahl} Arbeiter bleiben für den nächsten Stapel bereit "
                         f"(Einstellungen → »Arbeiter stoppen« gibt den Grafikspeicher frei).")
    yield (batch_html("fehler" if anzahl_fehler and not gelungen else "fertig",
                      f"{gelungen} von {gesamt} Dateien erzeugt", erledigt, gesamt,
                      anzahl_fehler, vergangen, 0,
                      vergangen / erledigt if erledigt else 0.0, tonlaenge),
           "\n".join(protokoll[-400:]),
           str(bericht_datei) if bericht_datei else None)


# ------------------------------------------------------------
# Oberflaeche
# ------------------------------------------------------------

def gradio_hauptversion() -> int:
    """Gradio 6 erwartet css und theme bei launch(), aeltere Fassungen bei Blocks()."""
    try:
        import gradio as gr

        return int(str(gr.__version__).split(".")[0])
    except Exception:
        return 0


def baue_thema():
    try:
        import gradio as gr

        return gr.themes.Base(primary_hue="fuchsia", secondary_hue="cyan", neutral_hue="slate")
    except Exception:
        return None


def passende_argumente(funktion, **kandidaten) -> dict:
    """Behaelt nur die Argumente, die diese Gradio-Fassung wirklich kennt."""
    import inspect

    try:
        erlaubt = set(inspect.signature(funktion).parameters)
    except (TypeError, ValueError):
        return dict(kandidaten)
    if "kwargs" in erlaubt:          # durchgereichte Signatur - nichts filtern
        return dict(kandidaten)
    return {name: wert for name, wert in kandidaten.items() if name in erlaubt}


def mach(klasse, **argumente):
    """
    Erzeugt eine Gradio-Komponente und laesst dabei Parameter weg, die die
    installierte Gradio-Fassung nicht kennt (z. B. show_copy_button ab Gradio 6).
    So bleibt die Oberflaeche ueber Versionsgrenzen hinweg lauffaehig.
    """
    rest = dict(argumente)
    for _versuch in range(len(argumente) + 1):
        try:
            return klasse(**rest)
        except TypeError as fehler:
            name = next((n for n in list(rest) if f"'{n}'" in str(fehler)), None)
            if name is None:
                raise
            rest.pop(name)
            sag(f"Hinweis: »{name}« kennt diese Gradio-Fassung nicht und wird weggelassen.")
    return klasse()


def arbeiter_zustand_html(zusatz: str = "") -> str:
    """Kleine Statuskarte fuer die Einstellungen."""
    pool = VERWALTUNG.laufend()
    if pool is None:
        farbe, titel = "#8a93a6", "KEINE ARBEITER GESTARTET"
        text = ("Der Stapel rechnet dann im Hauptprozess – ein Auftrag nach dem anderen. "
                "Kein zusätzlicher Grafikspeicher.")
    elif pool.bereit_anzahl() == pool.anzahl:
        farbe, titel = "#46e08a", f"{pool.anzahl} ARBEITER BEREIT"
        text = f"Beschäftigt: {pool.beschaeftigt()} · frei: {pool.bereit_anzahl() - pool.beschaeftigt()}"
    else:
        farbe, titel = "#ffc857", "ARBEITER WERDEN VORBEREITET"
        text = f"{pool.bereit_anzahl()} von {pool.anzahl} bereit – jeder lädt sein eigenes Modell."
    if zusatz:
        text += "<br>" + html.escape(zusatz)
    return (f"<div class='ize-batch' style='padding:12px 16px'>"
            f"<span class='ize-batch-titel' style='color:{farbe}'>{titel}</span>"
            f"<div style='font-size:12.5px;opacity:.75;margin-top:6px'>{text}</div></div>")


def baue_oberflaeche(ausgabe_ordner: Path, einstellungen_pfad: Path = None):
    import gradio as gr

    stapel_basis = ausgabe_ordner / "batch"
    einstellungen_pfad = einstellungen_pfad or (ausgabe_ordner / "einstellungen.json")
    einst = lies_einstellungen(einstellungen_pfad)
    empfehlung = empfohlene_arbeiter(MOTOR.vram_gb)

    def audio_eingabe(**kw):
        return mach(gr.Audio, sources=["upload", "microphone"], type="filepath", **kw)

    def audio_ausgabe(beschriftung="Ergebnis"):
        return mach(gr.Audio, label=beschriftung, type="numpy",
                    autoplay=False, show_download_button=True)

    # ---------------------------------------------- Einzelstück
    def lauf(text, ref_audio, ref_text, schritte, tempo, laenge, modus,
             wie_probe=False, autoplay=False):
        beginn = time.time()
        text = (text or "").strip()
        if not text:
            return None, "⚠️  Bitte zuerst einen Text eingeben, der gesprochen werden soll."
        if modus == "klonen" and not ref_audio:
            return None, "⚠️  Bitte eine Sprachprobe hochladen oder aufnehmen (5 bis 15 Sekunden)."

        argumente = {"text": text, "num_step": int(schritte), "speed": float(tempo)}
        vorgabe = ""
        if wie_probe and modus == "klonen" and ref_audio:
            probenlaenge = audiolaenge(ref_audio)
            if probenlaenge > 0.05:
                argumente["duration"] = probenlaenge
                vorgabe = f" · Länge wie Sprachprobe ({dauer_text(probenlaenge)})"
            else:
                vorgabe = " · Länge der Sprachprobe nicht lesbar – automatisch"
        elif laenge and float(laenge) > 0:
            argumente["duration"] = float(laenge)
        if modus == "klonen":
            argumente["ref_audio"] = ref_audio
            if (ref_text or "").strip():
                argumente["ref_text"] = ref_text.strip()

        try:
            daten = als_array(MOTOR.erzeuge(**argumente))
        except Exception as fehler:
            traceback.print_exc()
            hinweis = f"❌  Es hat nicht geklappt: {type(fehler).__name__}: {fehler}"
            if "out of memory" in str(fehler).lower():
                hinweis += ("\n\nDer Grafikspeicher ist voll. Kürzeren Text versuchen, "
                            "andere Programme schließen oder die Qualitätsstufe senken.")
            return None, hinweis

        gebraucht = time.time() - beginn
        try:
            ziel = ausgabe_ordner / time.strftime("omnivoice_%Y-%m-%d_%H-%M-%S.wav")
            schreibe_wav(daten, ziel)
            gespeichert = f"\n💾  Gespeichert als **{ziel.name}** in `{ziel.parent}`"
        except Exception as fehler:
            gespeichert = f"\n(Speichern nicht möglich: {fehler})"

        # Bei »automatisch abspielen« wird die Komponente selbst zurückgegeben,
        # damit sie mit autoplay=True neu aufgebaut wird.
        klang = (mach(gr.Audio, value=(ABTASTRATE, daten), autoplay=True) if autoplay
                 else (ABTASTRATE, daten))
        return klang, (
            f"✅  Fertig in {dauer_text(gebraucht)} · Länge "
            f"{dauer_text(len(daten) / ABTASTRATE)}{vorgabe} · {MOTOR.geraetename}{gespeichert}"
        )

    # ---------------------------------------------- Stapel
    def stapel_pruefen(csv_datei, wurzel, ziel_basis):
        return pruefe_liste(csv_datei, wurzel, ziel_basis, stapel_basis)

    def stapel_lauf(csv_datei, wurzel, ziel_basis, ueberspringen, schritte, tempo,
                    arbeiter, wie_probe, bericht):
        yield from stapel_durchlauf(csv_datei, wurzel, ziel_basis, ueberspringen,
                                    schritte, tempo, stapel_basis, arbeiter, wie_probe,
                                    bericht)

    # ---------------------------------------------- Auslastungsanzeige
    def monitor_aktualisieren():
        return messwerte.monitor_html(MOTOR.geraetename, True)

    def monitor_umschalten(an):
        import gradio as gr

        if an:
            messwerte.starten()
        return (gr.Timer(active=bool(an)),
                messwerte.monitor_html(MOTOR.geraetename, bool(an)))

    # ---------------------------------------------- Arbeiter verwalten
    def arbeiter_starten(anzahl):
        anzahl = max(1, int(anzahl))
        if anzahl <= 1:
            VERWALTUNG.stoppen()
            yield arbeiter_zustand_html(
                "Bei einem Arbeiter wird nichts zusätzlich gestartet – das ist gewollt.")
            return
        betrieb = VERWALTUNG.betrieb(anzahl)
        wartete = time.time()
        while betrieb.bereit_anzahl() < betrieb.anzahl and betrieb.lebende() > 0:
            yield arbeiter_zustand_html(f"läuft seit {dauer_text(time.time() - wartete)}")
            time.sleep(0.5)
        yield arbeiter_zustand_html(
            f"bereit nach {dauer_text(time.time() - wartete)}" if betrieb.lebende()
            else "Es konnte kein Arbeiter gestartet werden – siehe Protokoll im Studio.")

    def arbeiter_stoppen():
        VERWALTUNG.stoppen()
        return arbeiter_zustand_html("Der Grafikspeicher der Arbeiter ist wieder frei.")

    def einstellungen_speichern(anzahl, qualitaet, sprechtempo, wurzel_wert, ausgabe_wert,
                                ueberspringen_wert, wie_probe_wert, monitor_wert,
                                ton_wert, hinweis_wert, blinken_wert, bericht_wert,
                                autoplay_wert):
        return schreibe_einstellungen(einstellungen_pfad, {
            "arbeiter": int(anzahl), "qualitaet": int(qualitaet), "tempo": float(sprechtempo),
            "wurzel": wurzel_wert or "", "ausgabe": ausgabe_wert or "",
            "ueberspringen": bool(ueberspringen_wert),
            "dauer_von_probe": bool(wie_probe_wert), "monitor": bool(monitor_wert),
            "ton": bool(ton_wert), "hinweis": bool(hinweis_wert),
            "blinken": bool(blinken_wert), "bericht": bool(bericht_wert),
            "autoplay": bool(autoplay_wert),
        })

    def ordner_oeffnen(pfad_text=""):
        ziel = Path(pfad_text.strip()) if pfad_text.strip() else ausgabe_ordner
        try:
            ziel.mkdir(parents=True, exist_ok=True)
            if os.name == "nt":
                os.startfile(str(ziel))
            return f"📂  Ordner geöffnet: {ziel}"
        except Exception as fehler:
            return f"Ordner: {ziel}  ({fehler})"

    # ---------------------------------------------- Aufbau
    blocks_args = {"title": "OmniVoice Studio · iZE", "analytics_enabled": False, "fill_width": True}
    if gradio_hauptversion() < 6:
        blocks_args["css"] = CSS
        thema = baue_thema()
        if thema is not None:
            blocks_args["theme"] = thema

    with gr.Blocks(**passende_argumente(gr.Blocks.__init__, **blocks_args)) as seite:
        gr.HTML(KOPF_HTML)

        with gr.Tabs():
            # ------------------------------------------------ klonen
            with gr.Tab("🎤  Stimme klonen"):
                gr.Markdown(
                    "**So geht's:** eine kurze Sprachprobe hochladen oder direkt aufnehmen, "
                    "rechts den Text eintippen, auf *Sprechen lassen* klicken."
                )
                with gr.Row():
                    with gr.Column(scale=1, elem_classes="ize-karte"):
                        probe = audio_eingabe(label="1 · Sprachprobe (5 bis 15 Sekunden)")
                        probe_text = gr.Textbox(
                            label="2 · Was wird in der Probe gesagt? (optional)",
                            placeholder="Leer lassen – dann hört das Modell selbst hin.",
                            lines=2,
                        )
                        gr.Markdown(
                            "<div class='ize-tipp'>"
                            "· 5 bis 15 Sekunden reichen völlig aus<br>"
                            "· sauber aufgenommen, ohne Hall, ohne Musik im Hintergrund<br>"
                            "· nur eine Person sprechend<br>"
                            "· der Text darf in einer anderen Sprache sein als die Probe"
                            "</div>"
                        )
                    with gr.Column(scale=1, elem_classes="ize-karte"):
                        text_klon = gr.Textbox(label="3 · Dieser Text wird gesprochen",
                                               value=BEISPIEL_TEXT, lines=7)
                        klon_wie_probe = mach(
                            gr.Checkbox, value=bool(einst["dauer_von_probe"]),
                            label="Ausgabe genauso lang wie die Sprachprobe",
                            info="Die Aufnahme bekommt exakt die Länge der Sprachprobe. "
                                 "Gut fürs Vertonen, wenn die Zeile ins selbe Zeitfenster passen muss.")
                        klon_autoplay = mach(
                            gr.Checkbox, value=bool(einst["autoplay"]),
                            label="Ergebnis sofort abspielen",
                            info="Spielt die fertige Aufnahme automatisch ab – praktisch "
                                 "beim schnellen Ausprobieren mehrerer Texte.")
                        los_klon = gr.Button("▶  Sprechen lassen", variant="primary", elem_id="ize-los")
                with gr.Row():
                    with gr.Column(scale=2, elem_classes="ize-karte"):
                        ergebnis_klon = audio_ausgabe()
                    with gr.Column(scale=1, elem_classes="ize-karte"):
                        bericht_klon = gr.Markdown("Noch nichts erzeugt.")
                        gr.Button("📂  Ergebnis-Ordner öffnen").click(
                            lambda: ordner_oeffnen(""), inputs=None, outputs=[bericht_klon])

            # ------------------------------------------------ Überraschung
            with gr.Tab("🎲  Überraschung"):
                gr.Markdown("Ohne Vorgabe: Das Modell sucht sich selbst eine Stimme aus. "
                            "Gut zum schnellen Ausprobieren.")
                with gr.Column(elem_classes="ize-karte"):
                    text_zufall = gr.Textbox(label="Dieser Text wird gesprochen",
                                             value=BEISPIEL_TEXT, lines=5)
                    los_zufall = gr.Button("▶  Sprechen lassen", variant="primary", elem_id="ize-los")
                with gr.Row():
                    with gr.Column(scale=2, elem_classes="ize-karte"):
                        ergebnis_zufall = audio_ausgabe()
                    with gr.Column(scale=1, elem_classes="ize-karte"):
                        bericht_zufall = gr.Markdown("Noch nichts erzeugt.")

            # ------------------------------------------------ Stapel
            with gr.Tab("📦  Stapel (ganzes Projekt)"):
                gr.Markdown(
                    "Vertont eine ganze Liste auf einmal: Jede Zeile klont die Stimme aus der "
                    "englischen Audiodatei und spricht damit den deutschen Text.\n\n"
                    "**Format der CSV-Liste** – drei Spalten, getrennt durch Semikolon oder Komma:\n"
                    "`englische Audiodatei ; englischer Text ; deutscher Text`\n\n"
                    f"Beispiel: `{BEISPIEL_CSV}`\n\n"
                    "Der mittlere Text ist optional – fehlt er, hört OmniVoice die Aufnahme selbst ab."
                )
                with gr.Row():
                    with gr.Column(scale=1, elem_classes="ize-karte"):
                        csv_datei = mach(gr.File, label="1 · CSV-Liste",
                                         file_types=[".csv", ".txt"], type="filepath")
                        wurzel = mach(gr.Textbox,
                            label="2 · Wo fängt das Projekt an? (Wurzelordner)",
                            value=einst["wurzel"],
                            placeholder=r"z. B. C:\Projekte   –   leer lassen = automatisch erkennen",
                            lines=1,
                        )
                        gr.Markdown(
                            "<div class='ize-tipp'>Der Teil des Pfades <b>unterhalb</b> dieses Ordners "
                            "wird im Ausgabeordner nachgebaut.<br>"
                            r"Beispiel: Wurzel <code>C:\Projekte</code> und Datei "
                            r"<code>C:\Projekte\habitat\audio\stimme.wav</code> "
                            r"→ Ausgabe <code>batch\habitat\audio\stimme.wav</code>.</div>"
                        )
                    with gr.Column(scale=1, elem_classes="ize-karte"):
                        ziel_basis = mach(gr.Textbox, label="3 · Ausgabeordner",
                                          value=einst["ausgabe"] or str(stapel_basis), lines=1)
                        ueberspringen = mach(
                            gr.Checkbox, value=bool(einst["ueberspringen"]),
                            label="Bereits vorhandene Dateien überspringen",
                            info="So lässt sich ein abgebrochener Stapel einfach fortsetzen.")
                        stapel_wie_probe = mach(
                            gr.Checkbox, value=bool(einst["dauer_von_probe"]),
                            label="Jede Ausgabe so lang wie ihre englische Aufnahme",
                            info="Die deutsche Zeile bekommt exakt die Länge der Originaldatei – "
                                 "passt damit ins selbe Zeitfenster.")
                        bericht_an = mach(
                            gr.Checkbox, value=bool(einst["bericht"]),
                            label="Bericht als CSV schreiben",
                            info="Legt am Ende eine Liste mit Status je Zeile im "
                                 "Ausgabeordner ab (_bericht_<Zeitpunkt>.csv).")
                        stapel_arbeiter = mach(
                            gr.Slider, minimum=1, maximum=8,
                            value=int(einst["arbeiter"]), step=1,
                            label="Arbeiter (parallele OmniVoice-Prozesse)",
                            info=f"1 = im Hauptprozess. Für diese Grafikkarte empfohlen: "
                                 f"bis {empfehlung}. Einstellbar auch im Reiter »Einstellungen«.")
                        with gr.Row():
                            pruefen_knopf = gr.Button("🔍  Liste prüfen")
                            los_stapel = gr.Button("▶  Stapel starten", variant="primary",
                                                   elem_id="ize-stapel-los")
                            stopp_stapel = gr.Button("⏹  Anhalten", variant="stop")
                        pruef_bericht = gr.Markdown("Noch nicht geprüft.")

                stapel_anzeige = gr.HTML(LEERE_ANZEIGE)
                with gr.Row():
                    with gr.Column(scale=3):
                        stapel_protokoll = mach(gr.Textbox, label="Protokoll", lines=14,
                                                max_lines=14, autoscroll=True,
                                                show_copy_button=True)
                    with gr.Column(scale=1, elem_classes="ize-karte"):
                        bericht_datei_aus = mach(gr.File, label="Bericht (CSV)")
                        gr.Button("📂  Ausgabeordner öffnen").click(
                            ordner_oeffnen, inputs=[ziel_basis], outputs=[pruef_bericht])

            # ------------------------------------------------ Einstellungen
            with gr.Tab("⚙️  Einstellungen"):
                with gr.Row():
                    with gr.Column(scale=1, elem_classes="ize-karte"):
                        gr.Markdown(
                            "### Arbeiter\n"
                            "Jeder Arbeiter ist ein **eigener OmniVoice-Prozess** mit einem "
                            "eigenen Modell im Grafikspeicher. Der Stapelbetrieb verteilt die "
                            "Dateien darauf und rechnet dadurch wirklich parallel.\n\n"
                            f"· **1 Arbeiter** rechnet im Hauptprozess – kein zusätzlicher Speicher.\n"
                            f"· Jeder weitere Arbeiter braucht grob **3,5 GB** Grafikspeicher.\n"
                            f"· Erkannt: **{komma(MOTOR.vram_gb)} GB** auf {html.escape(MOTOR.geraetename)} "
                            f"→ empfohlen bis **{empfehlung}**.\n\n"
                            "Die Arbeiter starten automatisch beim ersten Stapel und bleiben "
                            "danach bereit. Zum Freigeben des Speichers hier stoppen."
                        )
                        arbeiter_regler = mach(
                            gr.Slider, minimum=1, maximum=8, value=int(einst["arbeiter"]), step=1,
                            label="Anzahl der Arbeiter",
                            info="Gilt für den Stapelbetrieb.")
                        with gr.Row():
                            arbeiter_start_knopf = gr.Button("⚡  Arbeiter starten", variant="primary")
                            arbeiter_stopp_knopf = gr.Button("⏹  Arbeiter stoppen", variant="stop")
                    with gr.Column(scale=1, elem_classes="ize-karte"):
                        arbeiter_anzeige = gr.HTML(arbeiter_zustand_html())
                        gr.Markdown("### Anzeige und Benachrichtigung")
                        monitor_an = mach(
                            gr.Checkbox, value=bool(einst["monitor"]),
                            label="Auslastung einblenden",
                            info="Kleines Fenster unten rechts mit Prozessor, Arbeitsspeicher, "
                                 "Grafikkarte und Grafikspeicher – wird alle 2 Sekunden aktualisiert.")
                        ton_an = mach(
                            gr.Checkbox, value=bool(einst["ton"]),
                            label="Signalton, wenn ein Stapel fertig ist",
                            info="Nur im Stapelbetrieb.")
                        hinweis_an = mach(
                            gr.Checkbox, value=bool(einst["hinweis"]),
                            label="Browser-Benachrichtigung, wenn ein Stapel fertig ist",
                            info="Beim Einschalten fragt der Browser einmalig um Erlaubnis.")
                        blinken_an = mach(
                            gr.Checkbox, value=bool(einst["blinken"]),
                            label="Browser-Tab blinken lassen, wenn ein Stapel fertig ist",
                            info="Der Reitertitel wechselt, bis das Fenster wieder im "
                                 "Vordergrund ist. Nur wenn der Tab gerade nicht sichtbar ist.")
                        gr.Markdown(
                            "### Speichern\n"
                            "Alle Einstellungen dieser Seite werden gemerkt und beim nächsten "
                            "Start wieder eingesetzt."
                        )
                        speichern_knopf = gr.Button("💾  Einstellungen speichern")
                        speicher_bericht = gr.Markdown(f"Ablage: `{einstellungen_pfad}`")
                        gr.Markdown(
                            "<div class='ize-tipp'>"
                            f"Gerät: {html.escape(MOTOR.geraetename)} ({MOTOR.dtype_name})<br>"
                            f"Modell: {MODELL}<br>"
                            f"Ergebnisse: {html.escape(str(ausgabe_ordner))}<br>"
                            f"Stapel: {html.escape(str(stapel_basis))}"
                            "</div>"
                        )

        with gr.Accordion("⚙️  Feineinstellung (kann meistens so bleiben)", open=False):
            with gr.Row():
                schritte = mach(gr.Slider, minimum=8, maximum=64, value=int(einst["qualitaet"]),
                                step=1, label="Qualitätsstufe",
                                info="mehr = besser und langsamer")
                tempo = mach(gr.Slider, minimum=0.5, maximum=1.5, value=float(einst["tempo"]),
                             step=0.05, label="Sprechtempo", info="1,0 = normal")
                laenge = mach(gr.Slider, minimum=0, maximum=60, value=0, step=1,
                              label="Feste Länge in Sekunden",
                              info="0 = automatisch. Gilt nicht im Stapel; das Häkchen "
                                   "»so lang wie die Sprachprobe« hat Vorrang.")

        gr.HTML(FUSS_HTML.format(geraet=html.escape(MOTOR.geraetename)))

        # Schwebende Auslastungsanzeige - liegt außerhalb der Reiter und ist
        # damit überall sichtbar.
        if bool(einst["monitor"]):
            messwerte.starten()
        monitor_feld = gr.HTML(messwerte.monitor_html(MOTOR.geraetename, bool(einst["monitor"])))
        monitor_takt = mach(gr.Timer, value=2.0, active=bool(einst["monitor"]))

        # ---------------------------------------------- Verdrahtung
        los_klon.click(
            lambda t, a, rt, s, sp, l, w, ap: lauf(t, a, rt, s, sp, l, "klonen", w, ap),
            inputs=[text_klon, probe, probe_text, schritte, tempo, laenge,
                    klon_wie_probe, klon_autoplay],
            outputs=[ergebnis_klon, bericht_klon],
        )
        los_zufall.click(
            lambda t, s, sp, l: lauf(t, None, "", s, sp, l, "zufall"),
            inputs=[text_zufall, schritte, tempo, laenge],
            outputs=[ergebnis_zufall, bericht_zufall],
        )
        pruefen_knopf.click(stapel_pruefen, inputs=[csv_datei, wurzel, ziel_basis],
                            outputs=[pruef_bericht])
        # Während ein Stapel läuft, sind Prüfen und Starten gesperrt. Freigegeben
        # wird am Ende des Laufs - und beim Anhalten, weil die Kette dann abbricht.
        def knoepfe(aktiv):
            return gr.Button(interactive=aktiv), gr.Button(interactive=aktiv)

        sperre = los_stapel.click(lambda: knoepfe(False), inputs=None,
                                  outputs=[pruefen_knopf, los_stapel])
        stapel_ereignis = sperre.then(
            stapel_lauf,
            inputs=[csv_datei, wurzel, ziel_basis, ueberspringen, schritte, tempo,
                    stapel_arbeiter, stapel_wie_probe, bericht_an],
            outputs=[stapel_anzeige, stapel_protokoll, bericht_datei_aus],
        )
        freigabe = stapel_ereignis.then(lambda: knoepfe(True), inputs=None,
                                        outputs=[pruefen_knopf, los_stapel])
        try:
            stopp_stapel.click(lambda: knoepfe(True), inputs=None,
                               outputs=[pruefen_knopf, los_stapel],
                               cancels=[stapel_ereignis])
        except TypeError:
            stopp_stapel.click(lambda: knoepfe(True), inputs=None,
                               outputs=[pruefen_knopf, los_stapel])

        # Nach dem Stapel: Ton und Browser-Benachrichtigung. Läuft komplett im
        # Browser, deshalb als reine JavaScript-Aktion ohne Python-Funktion.
        try:
            freigabe.then(None,
                          inputs=[ton_an, hinweis_an, blinken_an, stapel_protokoll],
                          outputs=[], js=MELDUNG_JS)
        except Exception as fehler:
            sag(f"Hinweis: Benachrichtigung nicht verfügbar ({fehler}).")
        try:
            hinweis_an.change(None, inputs=[hinweis_an], outputs=[], js=ERLAUBNIS_JS)
        except Exception:
            pass

        # Auslastungsanzeige
        monitor_takt.tick(monitor_aktualisieren, inputs=None, outputs=[monitor_feld])
        monitor_an.change(monitor_umschalten, inputs=[monitor_an],
                          outputs=[monitor_takt, monitor_feld])

        # Beide Regler für die Arbeiterzahl zeigen immer denselben Wert.
        stapel_arbeiter.change(lambda wert: wert, inputs=[stapel_arbeiter],
                               outputs=[arbeiter_regler])
        arbeiter_regler.change(lambda wert: wert, inputs=[arbeiter_regler],
                               outputs=[stapel_arbeiter])
        arbeiter_start_knopf.click(arbeiter_starten, inputs=[arbeiter_regler],
                                   outputs=[arbeiter_anzeige])
        arbeiter_stopp_knopf.click(arbeiter_stoppen, inputs=None, outputs=[arbeiter_anzeige])
        speichern_knopf.click(
            einstellungen_speichern,
            inputs=[arbeiter_regler, schritte, tempo, wurzel, ziel_basis, ueberspringen,
                    stapel_wie_probe, monitor_an, ton_an, hinweis_an, blinken_an,
                    bericht_an, klon_autoplay],
            outputs=[speicher_bericht],
        )
        # Beide Häkchen für die Länge zeigen immer dasselbe.
        stapel_wie_probe.change(lambda wert: wert, inputs=[stapel_wie_probe],
                                outputs=[klon_wie_probe])
        klon_wie_probe.change(lambda wert: wert, inputs=[klon_wie_probe],
                              outputs=[stapel_wie_probe])

    return seite


# ------------------------------------------------------------
# Start
# ------------------------------------------------------------

def main() -> int:
    zerleger = argparse.ArgumentParser(add_help=False)
    zerleger.add_argument("--ip", default="127.0.0.1")
    zerleger.add_argument("--port", type=int, default=7860)
    zerleger.add_argument("--ausgabe", default="")
    zerleger.add_argument("--einstellungen", default="")
    argumente, _rest = zerleger.parse_known_args()

    ausgabe = Path(argumente.ausgabe) if argumente.ausgabe else Path.home() / "OmniVoice"
    einstellungen = (Path(argumente.einstellungen) if argumente.einstellungen
                     else ausgabe / "einstellungen.json")

    try:
        import gradio  # noqa: F401
    except Exception as fehler:
        sag(f"FEHLER: Gradio ist nicht verfügbar ({fehler}).")
        return EXIT_NICHT_STARTBAR

    try:
        MOTOR.laden()
    except Exception as fehler:
        sag("")
        sag(f"FEHLER: Das Sprachmodell ließ sich nicht laden: {type(fehler).__name__}: {fehler}")
        traceback.print_exc()
        return EXIT_NICHT_STARTBAR

    try:
        seite = baue_oberflaeche(ausgabe, einstellungen)
    except Exception as fehler:
        sag("")
        sag(f"FEHLER: Die deutsche Oberfläche ließ sich nicht aufbauen: "
            f"{type(fehler).__name__}: {fehler}")
        traceback.print_exc()
        return EXIT_NICHT_STARTBAR

    sag("")
    sag(f"Ergebnisse landen in: {ausgabe}")
    sag(f"Stapel-Ausgaben in  : {ausgabe / 'batch'}")
    sag(f"Einstellungen       : {einstellungen}")
    sag(f"Empfohlene Arbeiter : bis {empfohlene_arbeiter(MOTOR.vram_gb)} "
        f"({komma(MOTOR.vram_gb)} GB Grafikspeicher)")
    sag("Die Oberfläche wird gestartet …")
    try:
        seite.queue()
    except Exception:
        pass

    start_args = {
        "server_name": argumente.ip,
        "server_port": argumente.port,
        "share": False,
        "inbrowser": False,
        "show_api": False,
        "quiet": False,
        "show_error": True,
        "allowed_paths": [str(ausgabe)],
        # Sprache: head läuft vor Gradios Programmteil und stellt die
        # Oberfläche auf Deutsch, js ersetzt danach die fest eingebauten
        # englischen Reste ("processing |").
        "head": SPRACHE_HEAD,
        "js": UEBERSETZUNG_JS,
    }
    if gradio_hauptversion() >= 6:
        # Ab Gradio 6 werden Aussehen und Thema erst hier übergeben.
        start_args["css"] = CSS
        thema = baue_thema()
        if thema is not None:
            start_args["theme"] = thema

    try:
        seite.launch(**passende_argumente(seite.launch, **start_args))
    finally:
        # Arbeiter nie zurücklassen - sie hätten sonst weiter Grafikspeicher belegt.
        VERWALTUNG.stoppen()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        VERWALTUNG.stoppen()
        sag("Beendet.")
        sys.exit(0)
