#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Erweiterte Ansicht des Stapelbetriebs: alle Zeilen der Liste als Tabelle,
mit beiden Wellenformen, Dauern, Status, Filtern und Knopf je Zeile.

Bewusst als HTML aufgebaut statt mit einer Gradio-Tabelle: nur so passen zwei
Wellenformen, zwei Texte, Statusmarken und ein Knopf in eine Zeile. Die
Bedienung laeuft ueber gr.HTML(server_functions=...) - die Knoepfe rufen also
direkt Python auf, ohne Umweg ueber versteckte Felder.

Die Wellenformen entstehen als kleines SVG direkt aus den Abtastwerten und
werden zwischengespeichert (Schluessel: Pfad, Aenderungszeit, Groesse).
Gezeichnet wird nur, was gerade sichtbar ist - die Liste laedt beim Scrollen nach.
"""

import base64
import fnmatch
import html
from dataclasses import dataclass
from pathlib import Path

TOLERANZ = 0.30          # ab dieser Abweichung in Sekunden gilt eine Zeile als laenger/kuerzer
WELLE_PUNKTE = 70        # Aufloesung der Wellenform
NACHLADEN = 40           # so viele Zeilen kommen beim Scrollen dazu
STUECK_SEKUNDEN = 60.0   # so viel wird von grossen Dateien am Stueck geliefert
VORSCHAU_RATE = 24000    # Vorschau reicht in Modellqualitaet, spart viel Groesse
_WELLEN_SPEICHER: dict = {}
_SPEICHER_GRENZE = 4000

FARBE_EN = "#8aa4c8"
FARBE_DE = "#4d9bff"

ZUSTAENDE = [
    "alle",
    "noch offen",
    "fertig",
    "deutsch länger",
    "deutsch kürzer",
    "englische Datei fehlt",
    "ohne deutschen Text",
]

SUCHFELDER = ["alles", "deutscher Text", "englischer Text", "Dateiname"]
RATING_FILTER = [
    "alle Ratings",
    "noch nicht geprüft",
    "unter 50 %",
    "50 bis 79 %",
    "ab 80 %",
]
SORTIERUNGEN = [
    "Zeile", "Dateiname", "Abweichung",
    "Dauer englisch ↓", "Dauer englisch ↑",
    "Dauer deutsch ↓", "Dauer deutsch ↑",
    "Rating ↓", "Rating ↑",
]

MIME = {
    ".wav": "audio/wav", ".mp3": "audio/mpeg", ".ogg": "audio/ogg",
    ".opus": "audio/ogg", ".flac": "audio/flac", ".m4a": "audio/mp4",
    ".aac": "audio/aac", ".aiff": "audio/aiff", ".wma": "audio/x-ms-wma",
}


# ------------------------------------------------------------
# Datenmodell
# ------------------------------------------------------------

@dataclass
class Eintrag:
    nummer: int
    quelle: Path
    ziel: Path
    englisch: str
    deutsch: str
    dauer_en: float = 0.0
    dauer_de: float = 0.0
    quelle_da: bool = False
    ziel_da: bool = False
    rating: float | None = None
    whisper_text: str = ""
    szene_da: bool = False        # im Szenen-Editor schon begonnen?

    @property
    def name(self) -> str:
        return self.quelle.name or "—"

    @property
    def abweichung(self) -> float:
        if not (self.ziel_da and self.dauer_en > 0):
            return 0.0
        return self.dauer_de - self.dauer_en

    @property
    def zustand(self) -> str:
        if not self.deutsch.strip():
            return "ohne deutschen Text"
        if not self.quelle_da:
            return "englische Datei fehlt"
        if not self.ziel_da:
            return "noch offen"
        if self.abweichung > TOLERANZ:
            return "deutsch länger"
        if self.abweichung < -TOLERANZ:
            return "deutsch kürzer"
        return "fertig"

    @property
    def machbar(self) -> bool:
        return self.quelle_da and bool(self.deutsch.strip())


def dauer(pfad: Path) -> float:
    try:
        import soundfile as sf

        return float(sf.info(str(pfad)).duration)
    except Exception:
        return 0.0


# Wo der Szenen-Editor seine angefangenen Szenen ablegt. Setzt oberflaeche.py
# beim Aufbau - so weiss die Liste, zu welcher Zeile schon eine Szene existiert.
SZENEN_ORDNER: Path | None = None


def setze_szenenordner(pfad) -> None:
    global SZENEN_ORDNER
    SZENEN_ORDNER = Path(pfad) if pfad else None


def _szene_vorhanden(quelle: Path) -> bool:
    if SZENEN_ORDNER is None:
        return False
    try:
        import szenen_editor

        return szenen_editor.hat_szene(SZENEN_ORDNER, quelle)
    except Exception:
        return False


def aktualisiere(eintrag: Eintrag) -> Eintrag:
    """Liest Vorhandensein und Dauer der beiden Dateien neu ein."""
    eintrag.quelle_da = eintrag.quelle.exists()
    eintrag.ziel_da = eintrag.ziel.exists()
    eintrag.dauer_en = dauer(eintrag.quelle) if eintrag.quelle_da else 0.0
    eintrag.dauer_de = dauer(eintrag.ziel) if eintrag.ziel_da else 0.0
    eintrag.szene_da = _szene_vorhanden(eintrag.quelle)
    return eintrag


def setze_bewertung(eintrag: Eintrag, bewertung: dict | None) -> Eintrag:
    """Übernimmt einen gültigen Eintrag aus dem dauerhaften Whisper-Speicher."""
    if not bewertung:
        eintrag.rating = None
        eintrag.whisper_text = ""
        return eintrag
    try:
        eintrag.rating = max(0.0, min(100.0, float(bewertung.get("rating"))))
    except (TypeError, ValueError):
        eintrag.rating = None
    eintrag.whisper_text = str(
        bewertung.get("transkript", bewertung.get("whisper_text", "")) or ""
    )
    return eintrag


def baue_eintraege(zeilen: list, wurzel: Path, basis: Path, loese_quelle, zielpfad) -> list:
    """Baut das Modell aus den CSV-Zeilen (die beiden Funktionen kommen von oberflaeche.py)."""
    eintraege = []
    for nummer, felder in enumerate(zeilen, start=1):
        quelle = loese_quelle(felder[0] if felder else "", str(wurzel))
        if len(felder) == 2:
            englisch, deutsch = "", felder[1].strip()
        else:
            englisch = felder[1].strip() if len(felder) > 1 else ""
            deutsch = felder[2].strip() if len(felder) > 2 else ""
        eintraege.append(aktualisiere(Eintrag(
            nummer=nummer, quelle=quelle, ziel=zielpfad(quelle, wurzel, basis),
            englisch=englisch, deutsch=deutsch)))
    return eintraege


# ------------------------------------------------------------
# Wellenform und Abspielen
# ------------------------------------------------------------

def _spitzen(pfad: Path, anzahl: int = WELLE_PUNKTE) -> list:
    """Liefert je Abschnitt den groessten Ausschlag (0 bis 1)."""
    try:
        import numpy as np
        import soundfile as sf

        daten, _rate = sf.read(str(pfad), dtype="float32", always_2d=False)
        if getattr(daten, "ndim", 1) > 1:
            daten = daten.mean(axis=1)
        if len(daten) == 0:
            return []
        groesste = float(np.max(np.abs(daten))) or 1.0
        teile = np.array_split(np.abs(daten), min(anzahl, max(1, len(daten))))
        return [float(np.max(t) / groesste) if len(t) else 0.0 for t in teile]
    except Exception:
        return []


def welle_svg(pfad: Path, farbe: str = FARBE_DE, breite: int = 160, hoehe: int = 30) -> str:
    """Kleine Wellenform als SVG. Ergebnis wird zwischengespeichert."""
    try:
        zustand = pfad.stat()
        schluessel = (str(pfad), zustand.st_mtime_ns, zustand.st_size, farbe)
    except OSError:
        return leere_welle(breite, hoehe)
    if schluessel in _WELLEN_SPEICHER:
        return _WELLEN_SPEICHER[schluessel]

    werte = _spitzen(pfad)
    if not werte:
        svg = leere_welle(breite, hoehe)
    else:
        mitte = hoehe / 2.0
        schritt = breite / max(1, len(werte) - 1) if len(werte) > 1 else breite
        oben, unten = [], []
        for i, wert in enumerate(werte):
            x = i * schritt
            ausschlag = max(0.05, wert) * (mitte - 1)
            oben.append(f"{x:.1f},{mitte - ausschlag:.1f}")
            unten.append(f"{x:.1f},{mitte + ausschlag:.1f}")
        strecke = "M" + " L".join(oben) + " L" + " L".join(reversed(unten)) + " Z"
        svg = (f"<svg viewBox='0 0 {breite} {hoehe}' width='100%' height='{hoehe}' "
               f"preserveAspectRatio='none' style='display:block'>"
               f"<path d='{strecke}' fill='{farbe}' fill-opacity='0.7'/></svg>")

    if len(_WELLEN_SPEICHER) > _SPEICHER_GRENZE:
        _WELLEN_SPEICHER.clear()
    _WELLEN_SPEICHER[schluessel] = svg
    return svg


def leere_welle(breite: int = 160, hoehe: int = 30) -> str:
    return (f"<svg viewBox='0 0 {breite} {hoehe}' width='100%' height='{hoehe}' "
            f"preserveAspectRatio='none' style='display:block'>"
            f"<line x1='0' y1='{hoehe / 2:.0f}' x2='{breite}' y2='{hoehe / 2:.0f}' "
            f"stroke='rgba(255,255,255,.16)' stroke-dasharray='3 4'/></svg>")


def daten_uri(pfad: Path, grenze_mb: float = 12.0) -> str:
    """Audiodatei als data:-Adresse, damit der Browser sie ohne Umweg abspielen kann."""
    try:
        if pfad.stat().st_size > grenze_mb * 1024 * 1024:
            return ""
        art = MIME.get(pfad.suffix.lower(), "audio/wav")
        return f"data:{art};base64," + base64.b64encode(pfad.read_bytes()).decode("ascii")
    except OSError:
        return ""


def ausschnitt_uri(pfad: Path, ab: float = 0.0, laenge: float = STUECK_SEKUNDEN,
                   rate: int = VORSCHAU_RATE) -> tuple:
    """
    Ein Stueck einer Aufnahme als kleine data:-Adresse (Adresse, Startzeit, Dauer).

    Grosse englische Originale sind haeufig mehrkanalige 48-kHz-Aufnahmen und
    damit weit ueber der Groesse, die als data:-Adresse noch sinnvoll ist. Statt
    das Abspielen zu verweigern, wird nur der gebrauchte Ausschnitt gelesen, auf
    Mono und eine Vorschaurate heruntergerechnet und einzeln geliefert. Der
    Rest der Datei wird dabei gar nicht erst angefasst.
    """
    import io

    import numpy as np
    import soundfile as sf

    with sf.SoundFile(str(pfad)) as datei:
        quelle_rate = int(datei.samplerate)
        gesamt = len(datei)
        beginn = max(0, min(gesamt - 1, int(round(max(0.0, ab) * quelle_rate))))
        anzahl = min(gesamt - beginn, int(round(max(1.0, laenge) * quelle_rate)))
        datei.seek(beginn)
        daten = datei.read(anzahl, dtype="float32", always_2d=False)

    if getattr(daten, "ndim", 1) > 1:
        daten = daten.mean(axis=1)
    daten = np.asarray(daten, dtype="float32")
    if not len(daten):
        return "", 0.0, 0.0
    if quelle_rate != rate:
        neu = max(1, int(round(len(daten) * rate / float(quelle_rate))))
        stellen = np.linspace(0, len(daten) - 1, neu, dtype="float64")
        daten = np.interp(stellen, np.arange(len(daten)), daten).astype("float32")

    puffer = io.BytesIO()
    sf.write(puffer, daten, rate, format="WAV", subtype="PCM_16")
    adresse = "data:audio/wav;base64," + base64.b64encode(puffer.getvalue()).decode("ascii")
    return adresse, round(beginn / quelle_rate, 3), round(len(daten) / rate, 3)


# ------------------------------------------------------------
# Filtern und Sortieren
# ------------------------------------------------------------

def _passt_text(eintrag: Eintrag, suche: str, feld: str) -> bool:
    suche = (suche or "").strip().lower()
    if not suche:
        return True
    muster = suche if ("*" in suche or "?" in suche) else f"*{suche}*"
    if feld == "deutscher Text":
        quellen = [eintrag.deutsch]
    elif feld == "englischer Text":
        quellen = [eintrag.englisch]
    elif feld == "Dateiname":
        quellen = [eintrag.name, str(eintrag.quelle)]
    else:
        quellen = [eintrag.deutsch, eintrag.englisch, eintrag.name, str(eintrag.quelle)]
    return any(fnmatch.fnmatch(str(q).lower(), muster) for q in quellen)


def filtere(eintraege: list, suche: str = "", feld: str = "alles",
            zustand: str = "alle", sortierung: str = "Zeile",
            rating_filter: str = "alle Ratings") -> list:
    ergebnis = [e for e in eintraege
                if _passt_text(e, suche, feld)
                and (zustand in ("", "alle") or e.zustand == zustand)
                and _passt_rating(e, rating_filter)]
    if sortierung == "Dateiname":
        ergebnis.sort(key=lambda e: e.name.lower())
    elif sortierung == "Abweichung":
        ergebnis.sort(key=lambda e: -abs(e.abweichung))
    # »Dauer englisch« ohne Pfeil ist die alte Schreibweise und bleibt lesbar.
    elif sortierung in ("Dauer englisch ↓", "Dauer englisch"):
        ergebnis.sort(key=lambda e: (-e.dauer_en, e.nummer))
    elif sortierung == "Dauer englisch ↑":
        # Zeilen ohne Datei stehen hinten statt vorne - eine Dauer von 0 wäre
        # sonst immer der erste Treffer und die Sortierung nutzlos.
        ergebnis.sort(key=lambda e: (not e.quelle_da, e.dauer_en, e.nummer))
    elif sortierung == "Dauer deutsch ↓":
        ergebnis.sort(key=lambda e: (-e.dauer_de, e.nummer))
    elif sortierung == "Dauer deutsch ↑":
        ergebnis.sort(key=lambda e: (not e.ziel_da, e.dauer_de, e.nummer))
    elif sortierung == "Rating ↓":
        ergebnis.sort(key=lambda e: (e.rating is None, -(e.rating or 0.0), e.nummer))
    elif sortierung == "Rating ↑":
        ergebnis.sort(key=lambda e: (e.rating is None, e.rating or 0.0, e.nummer))
    return ergebnis


def _passt_rating(eintrag: Eintrag, auswahl: str) -> bool:
    if auswahl in ("", "alle Ratings"):
        return True
    if auswahl == "noch nicht geprüft":
        return eintrag.rating is None
    if eintrag.rating is None:
        return False
    if auswahl == "unter 50 %":
        return eintrag.rating < 50.0
    if auswahl == "50 bis 79 %":
        return 50.0 <= eintrag.rating < 80.0
    if auswahl == "ab 80 %":
        return eintrag.rating >= 80.0
    return True


# ------------------------------------------------------------
# Aussehen der Liste (wird von Gradio auf die Komponente begrenzt)
# ------------------------------------------------------------

CSS_LISTE = """
.ize-rahmen {
    max-height: 58vh; overflow-y: auto; border-radius: 12px;
    border: 1px solid rgba(255,255,255,.10); background: rgba(11,13,21,.55);
}
.ize-liste { width: 100%; border-collapse: collapse;
             font-family: system-ui, -apple-system, "Segoe UI", sans-serif; }
.ize-liste thead th {
    position: sticky; top: 0; z-index: 2; text-align: left;
    background: #121524; color: #7f8ca4; font-size: 10px; font-weight: 800;
    letter-spacing: .16em; padding: 9px 10px;
    border-bottom: 1px solid rgba(255,255,255,.10);
}
.ize-zeile { border-top: 1px solid rgba(255,255,255,.055); transition: background .12s ease; }
.ize-zeile:hover { background: rgba(77,155,255,.09); }
.ize-zeile:hover .ize-name { color: #ffffff; }
.ize-zeile:hover .ize-welle svg path { fill-opacity: 1; }
.ize-zeile td { padding: 9px 10px; vertical-align: top; }
.ize-welle {
    cursor: pointer; border-radius: 6px; padding: 2px 0;
    border: 1px solid transparent; transition: border-color .12s ease, box-shadow .12s ease;
}
.ize-welle:hover { border-color: rgba(77,155,255,.55); }
.ize-welle.spielt { border-color: #4d9bff; box-shadow: 0 0 14px rgba(77,155,255,.45); }
.ize-knopf {
    width: 100%; padding: 7px 8px; border-radius: 8px; cursor: pointer;
    border: 1px solid rgba(77,155,255,.45); background: rgba(77,155,255,.14);
    color: #dbe6ff; font-size: 12px; font-weight: 700; letter-spacing: .03em;
    transition: background .12s ease, transform .08s ease;
}
.ize-knopf:hover { background: rgba(77,155,255,.30); }
.ize-knopf:active { transform: scale(.97); }
.ize-knopf[disabled] { opacity: .3; cursor: not-allowed; }
.ize-knopf.laeuft { background: rgba(255,79,216,.25); border-color: rgba(255,79,216,.65); }
.ize-knopf.ize-text-knopf {
    margin-top: 6px; border-color: rgba(34,224,255,.32);
    background: rgba(34,224,255,.08); font-size: 11px;
}
.ize-knopf.ize-szene-knopf {
    margin-top: 6px; border-color: rgba(255,79,216,.34);
    background: rgba(255,79,216,.09); font-size: 11px;
}
.ize-knopf.ize-szene-knopf:hover { background: rgba(255,79,216,.26); }
.ize-editor {
    position: fixed !important; inset: 50% auto auto 50% !important;
    transform: translate(-50%, -50%);
    margin: 0 !important; width: min(860px, 92vw); max-height: 86vh; overflow: auto;
    border: 1px solid rgba(77,155,255,.55); border-radius: 14px;
    padding: 18px; color: var(--ize-text, #eaf2ff);
    background: var(--ize-flaeche-stark, #121524);
    box-shadow: 0 24px 80px var(--ize-schatten, rgba(0,0,0,.65));
    animation: ize-editor-rein .22s cubic-bezier(.2,.85,.25,1) both;
}
.ize-editor::backdrop { background: rgba(0,0,0,.72); backdrop-filter: blur(3px); }
.ize-editor textarea, .ize-editor input {
    box-sizing: border-box; width: 100%; color: var(--ize-text, #eaf2ff);
    background: var(--ize-eingabe, rgba(0,0,0,.28));
    border: 1px solid var(--ize-rand, rgba(255,255,255,.14));
    border-radius: 8px; padding: 9px 10px;
}
.ize-editor textarea { min-height: 82px; resize: vertical; }
.ize-editor label {
    display:block; margin: 10px 0 5px; font-size: 11px; font-weight: 800; opacity:.72;
}
.ize-editor-aktionen { display:flex; gap:8px; justify-content:flex-end; margin-top:14px; }
.ize-editor-treffer { display:grid; gap:5px; margin-top:7px; max-height:230px; overflow:auto; }
.ize-editor-treffer button {
    text-align:left; padding:8px 10px; border-radius:8px; cursor:pointer;
    color:#dbe6ff; background:rgba(77,155,255,.09);
    border:1px solid rgba(77,155,255,.20);
}
.ize-editor-treffer button:hover { background:rgba(77,155,255,.22); }
.ize-editor-treffer small { display:block; margin-top:3px; opacity:.48; }
.ize-editor-audios {
    display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:10px; margin-top:14px;
}
.ize-editor-audios section {
    min-width:0; padding:10px; border:1px solid var(--ize-rand,rgba(255,255,255,.10));
    border-radius:10px; background:var(--ize-eingabe,rgba(0,0,0,.24));
    transition:background .28s ease,border-color .22s ease,transform .18s ease;
}
.ize-editor-audios section:hover {
    transform:translateY(-1px); border-color:rgba(34,224,255,.38);
}
.ize-editor-audios b {
    display:block; margin-bottom:7px; font-size:10px; letter-spacing:.13em; opacity:.72;
}
.ize-editor-audios audio { display:block; width:100%; height:36px; }
.ize-editor-audios small {
    display:block; overflow:hidden; margin-top:5px; opacity:.52;
    text-overflow:ellipsis; white-space:nowrap;
}
@keyframes ize-editor-rein {
    from { opacity:0; transform:translate(-50%,-47%) scale(.975); }
    to { opacity:1; transform:translate(-50%,-50%) scale(1); }
}
@media (max-width:680px) {
    .ize-editor-audios { grid-template-columns:1fr; }
}
.ize-mehr { padding: 12px; text-align: center; font-size: 11.5px; opacity: .5; }
.ize-leer { padding: 26px; text-align: center; opacity: .55; }
.ize-meldung {
    min-height: 17px; padding: 0 2px 7px 2px; font-size: 12px; color: #9fb0cc;
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
}
.ize-meldung:empty { padding: 0; min-height: 0; }
"""


def _sek(wert: float) -> str:
    return f"{wert:.2f}".replace(".", ",") + " s"


def _kuerze(text: str, laenge: int = 170) -> str:
    text = (text or "").strip()
    if len(text) <= laenge:
        return text or "—"
    return text[:laenge - 1] + "…"


def _marke(text: str, farbe: str, hintergrund: str) -> str:
    return (f"<span style='display:inline-block;padding:2px 8px;border-radius:9px;"
            f"font-size:10.5px;font-weight:800;letter-spacing:.04em;white-space:nowrap;"
            f"color:{farbe};background:{hintergrund}'>{html.escape(text)}</span>")


def _status_marken(eintrag: Eintrag) -> str:
    marken = {
        "ohne deutschen Text": _marke("kein Text", "#ff9b9b", "rgba(255,107,107,.16)"),
        "englische Datei fehlt": _marke("Datei fehlt", "#ff9b9b", "rgba(255,107,107,.16)"),
        "noch offen": _marke("offen", "#b9c4d8", "rgba(255,255,255,.09)"),
        "fertig": _marke("fertig", "#7ff0b0", "rgba(70,224,138,.15)"),
        "deutsch länger": _marke("länger", "#ffd27d", "rgba(255,200,87,.16)"),
        "deutsch kürzer": _marke("kürzer", "#ffd27d", "rgba(255,200,87,.16)"),
    }
    text = marken.get(eintrag.zustand, "")
    if eintrag.ziel_da and abs(eintrag.abweichung) > 0.01:
        vorzeichen = "+" if eintrag.abweichung > 0 else "−"
        farbe = "#ffd27d" if abs(eintrag.abweichung) > TOLERANZ else "#8a94a8"
        text += (f"<div style='font-size:10.5px;margin-top:5px;color:{farbe}'>"
                 f"{vorzeichen}{_sek(abs(eintrag.abweichung))}</div>")
    return text


def _rating_marke(eintrag: Eintrag) -> str:
    if eintrag.rating is None:
        return "<span style='font-size:10.5px;opacity:.35'>nicht geprüft</span>"
    rating = float(eintrag.rating)
    if rating >= 80:
        farbe, hintergrund = "#7ff0b0", "rgba(70,224,138,.15)"
    elif rating >= 50:
        farbe, hintergrund = "#ffd27d", "rgba(255,200,87,.16)"
    else:
        farbe, hintergrund = "#ff9b9b", "rgba(255,107,107,.16)"
    titel = html.escape(
        f"Whisper erkannt: {eintrag.whisper_text}" if eintrag.whisper_text
        else "Whisper-Prüfung abgeschlossen"
    )
    return (f"<span title='{titel}' style='display:inline-block;padding:4px 8px;"
            f"border-radius:9px;font-size:12px;font-weight:850;color:{farbe};"
            f"background:{hintergrund};white-space:nowrap'>{rating:.1f} %</span>")


def _spur(eintrag: Eintrag, welche: str) -> str:
    """Eine Sprachspur: anklickbare Wellenform, Dauer, Text."""
    if welche == "en":
        da, laenge, farbe, text = (eintrag.quelle_da, eintrag.dauer_en,
                                   FARBE_EN, eintrag.englisch)
        textstil = "opacity:.75"
        pfad = eintrag.quelle
    else:
        da, laenge, farbe, text = (eintrag.ziel_da, eintrag.dauer_de,
                                   FARBE_DE, eintrag.deutsch)
        textstil = "color:#dbe6ff"
        pfad = eintrag.ziel
    welle = welle_svg(pfad, farbe) if da else leere_welle()
    huelle = (f"class='ize-welle' data-ize-welle='1' data-ize-nr='{eintrag.nummer}' "
              f"data-ize-welche='{welche}' title='Klicken spielt ab dieser Stelle'"
              if da else "style='opacity:.45'")
    return (f"<div {huelle}>{welle}</div>"
            f"<div style='font-size:10.5px;opacity:.45;margin:4px 0 5px 0'>"
            f"{_sek(laenge) if da else '—'}</div>"
            f"<div style='font-size:12px;line-height:1.45;{textstil}'>"
            f"{html.escape(_kuerze(text))}</div>")


def zeile_html(eintrag: Eintrag) -> str:
    """Eine Tabellenzeile - wird auch einzeln ersetzt, wenn sie neu erzeugt wurde."""
    knopf_text = "↻ neu" if eintrag.ziel_da else "▶ erzeugen"
    gesperrt = "" if eintrag.machbar else "disabled"
    szene_zeichen = (
        "<span title='Für diese Aufnahme gibt es schon eine begonnene Szene' "
        "style='margin-right:5px;color:#ff9be9'>🎬</span>" if eintrag.szene_da else "")
    szene_titel = ("Szene weiterbearbeiten" if eintrag.szene_da
                   else "lange Aufnahme im Szenen-Editor öffnen")
    return (
        f"<tr class='ize-zeile' data-ize-zeile='{eintrag.nummer}'>"
        f"<td style='width:44px;font-size:12px;opacity:.4'>{eintrag.nummer}</td>"
        f"<td style='min-width:140px;max-width:220px'>"
        f"<div class='ize-name' style='font-size:12px;font-weight:700;color:#e7eeff;"
        f"word-break:break-all'>{szene_zeichen}{html.escape(eintrag.name)}</div>"
        f"<div style='font-size:10px;opacity:.35;word-break:break-all;margin-top:2px'>"
        f"{html.escape(_kuerze(str(eintrag.quelle.parent), 58))}</div></td>"
        f"<td style='min-width:190px'>{_spur(eintrag, 'en')}</td>"
        f"<td style='min-width:190px'>{_spur(eintrag, 'de')}</td>"
        f"<td style='width:100px'>{_status_marken(eintrag)}</td>"
        f"<td style='width:92px'>{_rating_marke(eintrag)}</td>"
        f"<td style='width:100px'>"
        f"<button type='button' class='ize-knopf' data-ize-neu='{eintrag.nummer}' "
        f"{gesperrt}>{knopf_text}</button>"
        f"<button type='button' class='ize-knopf ize-text-knopf' "
        f"data-ize-text='{eintrag.nummer}'>✎ Text</button>"
        f"<button type='button' class='ize-knopf ize-szene-knopf' "
        f"data-ize-szene='{eintrag.nummer}' title='{szene_titel}' "
        f"data-ize-quelle=\"{html.escape(str(eintrag.quelle), quote=True)}\" "
        f"data-ize-ziel=\"{html.escape(str(eintrag.ziel), quote=True)}\""
        f"{'' if eintrag.quelle_da else ' disabled'}>"
        f"{'🎬 Szene ›' if eintrag.szene_da else '🎬 Szene'}</button></td></tr>"
    )


def zeilen_html(eintraege: list, von: int, bis: int) -> str:
    return "".join(zeile_html(e) for e in eintraege[von:bis])


def meldung_html(text: str = "") -> str:
    """Statuszeile über der Liste - wird auch aus dem Browser heraus beschrieben."""
    return (f"<div class='ize-meldung' data-ize-meldung='1'>{html.escape(text)}</div>")


def tabelle_html(eintraege: list, sichtbar: int = NACHLADEN, meldung: str = "") -> str:
    """Baut die Liste. Gezeichnet werden nur die ersten Zeilen, der Rest kommt beim Scrollen."""
    if not eintraege:
        return (meldung_html(meldung) + "<div class='ize-rahmen'><div class='ize-leer'>"
                "Keine Zeile passt zu diesem Filter.</div></div>")

    sichtbar = max(1, min(int(sichtbar), len(eintraege)))
    kopf = ("<tr><th style='width:44px'>#</th><th>DATEI</th><th>ENGLISCH</th>"
            "<th>DEUTSCH</th><th style='width:100px'>STATUS</th>"
            "<th style='width:92px'>RATING</th>"
            "<th style='width:100px'></th></tr>")
    rest = len(eintraege) - sichtbar
    fuss = (f"<div class='ize-mehr' data-ize-mehr='{sichtbar}'>"
            f"noch {rest} Zeilen – einfach weiterscrollen …</div>" if rest > 0 else
            f"<div class='ize-mehr'>alle {len(eintraege)} Zeilen angezeigt</div>")
    return (meldung_html(meldung)
            + f"<div class='ize-rahmen' data-ize-rahmen='1'>"
              f"<table class='ize-liste'><thead>{kopf}</thead>"
              f"<tbody data-ize-koerper='1'>{zeilen_html(eintraege, 0, sichtbar)}</tbody>"
              f"</table>{fuss}</div>")


def stati_html(alle: list, gefiltert: list) -> str:
    """Zaehlwerk ueber den gesamten Bestand, unabhaengig vom Filter."""
    if not alle:
        return ("<div style='padding:14px;opacity:.55;border:1px dashed rgba(255,255,255,.15);"
                "border-radius:12px;font-size:12.5px'>Noch keine Liste eingelesen.</div>")

    zaehler = {name: 0 for name in ZUSTAENDE[1:]}
    for eintrag in alle:
        zaehler[eintrag.zustand] = zaehler.get(eintrag.zustand, 0) + 1
    dauer_en = sum(e.dauer_en for e in alle)
    dauer_de = sum(e.dauer_de for e in alle if e.ziel_da)
    fertig = (zaehler.get("fertig", 0) + zaehler.get("deutsch länger", 0)
              + zaehler.get("deutsch kürzer", 0))
    ratings = [float(e.rating) for e in alle if e.rating is not None]

    felder = [
        (str(len(alle)), "Zeilen gesamt", "#eaf2ff"),
        (str(fertig), "erzeugt", "#7ff0b0"),
        (str(zaehler.get("noch offen", 0)), "noch offen", "#b9c4d8"),
        (str(zaehler.get("deutsch länger", 0)), "deutsch länger", "#ffd27d"),
        (str(zaehler.get("deutsch kürzer", 0)), "deutsch kürzer", "#ffd27d"),
        (str(zaehler.get("englische Datei fehlt", 0)), "Datei fehlt", "#ff9b9b"),
        (str(zaehler.get("ohne deutschen Text", 0)), "ohne Text", "#ff9b9b"),
        (_minuten(dauer_en), "Ton englisch", "#8aa4c8"),
        (_minuten(dauer_de), "Ton deutsch", "#4d9bff"),
        ((f"{sum(ratings) / len(ratings):.1f} %" if ratings else "–"),
         f"Rating Ø ({len(ratings)})", "#22e0ff"),
        (str(len(gefiltert)), "im Filter", "#ff4fd8"),
    ]
    kacheln = "".join(
        "<div style='background:rgba(0,0,0,.28);border:1px solid rgba(255,255,255,.06);"
        "border-radius:10px;padding:8px 11px;flex:1 1 92px;min-width:92px'>"
        f"<b style='display:block;font-size:18px;font-weight:800;color:{farbe};"
        f"line-height:1.25'>{wert}</b>"
        f"<span style='display:block;font-size:10px;opacity:.55;margin-top:2px;"
        f"letter-spacing:.04em'>{titel}</span></div>"
        for wert, titel, farbe in felder
    )
    return "<div style='display:flex;gap:8px;flex-wrap:wrap'>" + kacheln + "</div>"


def _minuten(sekunden: float) -> str:
    sekunden = max(0.0, float(sekunden))
    if sekunden < 60:
        return f"{sekunden:.0f} s"
    minuten, rest = divmod(int(sekunden), 60)
    if minuten < 60:
        return f"{minuten}:{rest:02d}"
    stunden, minuten = divmod(minuten, 60)
    return f"{stunden}:{minuten:02d}:{rest:02d}"
