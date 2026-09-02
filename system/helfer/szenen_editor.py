#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Timeline-Editor für lange Szenen.

Bedienidee: Eine lange englische Aufnahme wird geladen und als Wellenform
gezeigt. Man markiert darin einen Bereich, tippt den deutschen Text und lässt
ihn sprechen - das Ergebnis landet **an genau derselben Stelle und mit genau
derselben Länge** in der deutschen Spur darunter. Teile der englischen Spur
lassen sich auch unverändert übernehmen (Atmo, Schreie, Lacher). Am Ende wird
die deutsche Spur als eine Datei gerendert und kann in den Stapelbetrieb
zurückgegeben werden.

Dieses Modul enthält nur Daten und Rechnung - kein Gradio, kein HTML. Damit
ist alles ohne Browser prüfbar. Die Bedienoberfläche liegt in oberflaeche.py.
"""

from __future__ import annotations

import json
import shutil
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path

import effekte
from motor import ABTASTRATE, als_array, baue_argumente, nachbearbeiten, schreibe_wav

# Auflösung der Wellenform, die an den Browser geht. 6000 Punkte reichen für
# eine halbe Stunde Material und bleiben als JSON klein genug.
WELLE_PUNKTE = 6000
MINDESTLAENGE = 0.15          # kürzere Bereiche ergeben keinen Sinn
BLENDE = 0.008                # kurze Ein-/Ausblendung an Schnittkanten


# ------------------------------------------------------------
# Datenmodell
# ------------------------------------------------------------

@dataclass
class Segment:
    nummer: int
    start: float
    ende: float
    art: str = "tts"              # tts | kopie
    text: str = ""
    original: str = ""            # englischer Text (z. B. von Whisper)
    datei: str = ""               # erzeugte oder ausgeschnittene Aufnahme
    sprecher: str = ""            # Referenzaufnahme für die Stimme
    stumm: bool = False
    veraltet: bool = False        # Länge geändert, Aufnahme passt nicht mehr

    @property
    def dauer(self) -> float:
        return max(0.0, self.ende - self.start)

    @property
    def fertig(self) -> bool:
        return bool(self.datei) and Path(self.datei).exists()

    def als_dict(self) -> dict:
        daten = asdict(self)
        daten["dauer"] = round(self.dauer, 3)
        daten["fertig"] = self.fertig
        return daten


@dataclass
class Szene:
    quelle: str = ""
    dauer: float = 0.0
    segmente: list = field(default_factory=list)
    naechste_nummer: int = 1
    arbeitsordner: str = ""
    # Wenn aktiv, besteht die deutsche Spur außerhalb fertiger Segmente aus
    # dem englischen Original statt aus Stille. Das ist ein Mischmodus und
    # erzeugt bewusst keine hunderte Kopie-Segmente in der Bearbeitungsliste.
    luecken_original: bool = False

    def segment(self, nummer: int):
        return next((s for s in self.segmente if s.nummer == nummer), None)

    def sortiert(self) -> list:
        return sorted(self.segmente, key=lambda s: s.start)

    def als_dict(self) -> dict:
        return {
            "quelle": self.quelle,
            "dauer": round(self.dauer, 3),
            "segmente": [s.als_dict() for s in self.sortiert()],
        }


# ------------------------------------------------------------
# Audio lesen und schreiben
# ------------------------------------------------------------

def lies_audio(pfad) -> tuple:
    """Liest eine Datei als Mono-Fließkomma mit 24 kHz (Rate, Daten)."""
    import numpy as np
    import soundfile as sf

    from motor import zu_mono

    daten, rate = sf.read(str(pfad), dtype="float32", always_2d=False)
    # Nicht schlicht mitteln: Bei Spielaufnahmen liegt die Sprache oft nur auf
    # einem Kanal, der Mittelwert wuerde sie um bis zu 15 dB verduennen.
    daten = zu_mono(daten)
    if rate != ABTASTRATE and len(daten):
        # Einfaches Umrechnen der Abtastrate - für Sprache völlig ausreichend.
        neu = int(round(len(daten) * ABTASTRATE / float(rate)))
        stellen = np.linspace(0, len(daten) - 1, neu, dtype="float64")
        daten = np.interp(stellen, np.arange(len(daten)), daten).astype("float32")
        rate = ABTASTRATE
    return rate, np.asarray(daten, dtype="float32")


def huellkurve(daten, punkte: int = WELLE_PUNKTE) -> list:
    """Spitzenwerte je Abschnitt, auf 0 bis 1 bezogen - Vorlage fürs Zeichnen."""
    import numpy as np

    if daten is None or len(daten) == 0:
        return []
    groesste = float(np.max(np.abs(daten))) or 1.0
    teile = np.array_split(np.abs(daten), min(punkte, len(daten)))
    return [round(float(np.max(t) / groesste), 4) if len(t) else 0.0 for t in teile]


def ausschnitt(daten, start: float, ende: float):
    """Bereich in Abtastwerten, mit weichen Kanten."""
    import numpy as np

    von = max(0, int(round(start * ABTASTRATE)))
    bis = min(len(daten), int(round(ende * ABTASTRATE)))
    if bis <= von:
        return np.zeros(0, dtype="float32")
    teil = np.array(daten[von:bis], dtype="float32", copy=True)
    kante = min(int(BLENDE * ABTASTRATE), len(teil) // 2)
    if kante > 1:
        teil[:kante] *= np.linspace(0.0, 1.0, kante, dtype="float32")
        teil[-kante:] *= np.linspace(1.0, 0.0, kante, dtype="float32")
    return teil


# ------------------------------------------------------------
# Wo liegt die Arbeit zu einer Quelldatei?
# ------------------------------------------------------------

def kennung(pfad) -> str:
    """
    Fester Ordnername je Quelldatei - damit man an einer Szene weiterarbeitet.

    Bewusst md5 statt hash(): Pythons eingebautes hash() ist bei Texten von
    Start zu Start unterschiedlich, der Ordner hieße also jedes Mal anders und
    der Zwischenstand waere nicht wiederzufinden.

    Klein geschrieben wird durchgehend, weil Windows Pfade ohne Rücksicht auf
    Groß- und Kleinschreibung vergleicht - sonst gäbe es zu derselben Datei je
    nach Schreibweise zwei Szenen.
    """
    import hashlib

    roh = str(Path(pfad).resolve()).lower().encode("utf-8", "replace")
    kurz = "".join(c if c.isalnum() else "_" for c in Path(pfad).stem.lower())[:40]
    return f"{kurz}_{hashlib.md5(roh).hexdigest()[:10]}"


def szenen_ordner(arbeitsordner, pfad) -> Path:
    return Path(arbeitsordner) / kennung(pfad)


def hat_szene(arbeitsordner, pfad) -> bool:
    """Gibt es zu dieser Aufnahme schon eine begonnene Szene?"""
    try:
        return (szenen_ordner(arbeitsordner, pfad) / "szene.omniprojekt.json").is_file()
    except Exception:
        return False


# ------------------------------------------------------------
# Der Editor
# ------------------------------------------------------------

class Editor:
    """Hält die geladene Szene und alle Segmente."""

    def __init__(self, arbeitsordner: Path):
        self.arbeitsordner = Path(arbeitsordner)
        self.szene = Szene()
        self._quelldaten = None          # Abtastwerte der englischen Spur
        self._de_daten = None            # gerenderte deutsche Spur
        self._vorschau = None            # zurücknehmbarer Stand beim Vorhören
        self.einstellungen = {}          # zuletzt bekannte Klangeinstellungen
        self.pegelbericht = []           # was beim Mischen nachgeregelt wurde
        self.meldung = ""

    # -- Arbeitsordner und Zwischenstand -----------------------
    def _kennung(self, pfad: Path) -> str:
        return kennung(pfad)

    def zustandsdatei_pfad(self) -> str:
        if not self.szene.arbeitsordner:
            return ""
        return str(Path(self.szene.arbeitsordner) / "szene.omniprojekt.json")

    def _sichern(self) -> None:
        """Automatisches Sichern nach jeder Änderung."""
        if not self.szene.quelle or not self.szene.arbeitsordner:
            return
        try:
            ziel = Path(self.zustandsdatei_pfad())
            ziel.parent.mkdir(parents=True, exist_ok=True)
            ziel.write_text(json.dumps(self.als_projekt(), indent=2, ensure_ascii=False),
                            encoding="utf-8")
        except Exception:
            pass

    # -- Laden -------------------------------------------------
    def laden(self, pfad, fortsetzen: bool = True) -> dict:
        pfad = Path(str(pfad).strip('" '))
        if not pfad.exists():
            return {"ok": False, "meldung": f"Datei nicht gefunden: {pfad}"}
        try:
            _rate, daten = lies_audio(pfad)
        except Exception as fehler:
            return {"ok": False, "meldung": f"Datei nicht lesbar: {fehler}"}
        if len(daten) == 0:
            return {"ok": False, "meldung": "Die Datei enthält keine Abtastwerte."}

        self._quelldaten = daten
        self._de_daten = None
        ordner = self.arbeitsordner / self._kennung(pfad)
        ordner.mkdir(parents=True, exist_ok=True)
        self.szene = Szene(quelle=str(pfad), dauer=len(daten) / ABTASTRATE,
                           arbeitsordner=str(ordner))

        # Frühere Arbeit an genau dieser Datei wieder aufnehmen.
        alt = ordner / "szene.omniprojekt.json"
        if fortsetzen and alt.exists():
            try:
                gespeichert = json.loads(alt.read_text(encoding="utf-8"))
                self.szene.naechste_nummer = int(gespeichert.get("naechste_nummer", 1))
                self.szene.luecken_original = bool(
                    gespeichert.get("luecken_original", False)
                )
                self.szene.segmente = [
                    Segment(**{k: v for k, v in s.items()
                               if k in Segment.__dataclass_fields__})
                    for s in gespeichert.get("segmente", [])
                ]
                fehlend = sum(1 for s in self.szene.segmente if not s.fertig)
                self.meldung = (f"{pfad.name} geladen · {self.szene.dauer:.1f} s · "
                                f"{len(self.szene.segmente)} Segmente aus dem letzten Mal"
                                + (f" ({fehlend} ohne Aufnahme)" if fehlend else ""))
                return {"ok": True, **self.zustand()}
            except Exception as fehler:
                self.meldung = f"Zwischenstand unlesbar ({fehler}) – frisch begonnen."
                self.szene.segmente = []

        self.meldung = f"{pfad.name} geladen · {self.szene.dauer:.1f} s"
        return {"ok": True, **self.zustand()}

    def geladen(self) -> bool:
        return self._quelldaten is not None and self.szene.dauer > 0

    # -- Zustand für den Browser -------------------------------
    def zustand(self, sichern: bool = True) -> dict:
        # Die deutsche Spur wird hier immer frisch gerechnet - sonst fehlt nach
        # dem Erzeugen die Wellenform, bis jemand speichert.
        if self._de_daten is None and self.geladen():
            self.rendern()
        if sichern:
            self._sichern()
        return {
            "quelle": Path(self.szene.quelle).name if self.szene.quelle else "",
            "pfad": self.szene.quelle,
            "dauer": round(self.szene.dauer, 3),
            "welle_en": huellkurve(self._quelldaten),
            "welle_de": huellkurve(self._de_daten) if self._de_daten is not None else [],
            "segmente": [s.als_dict() for s in self.szene.sortiert()],
            "belegt": round(sum(s.dauer for s in self.szene.segmente
                                 if s.fertig and not s.stumm), 2),
            "luecken_original": bool(self.szene.luecken_original),
            "projekt": self.zustandsdatei_pfad(),
            "meldung": self.meldung,
        }

    # -- Bereiche ----------------------------------------------
    def _pruefe_bereich(self, start: float, ende: float) -> str:
        if not self.geladen():
            return "Erst eine Datei laden."
        if ende - start < MINDESTLAENGE:
            return f"Der Bereich ist zu kurz (mindestens {MINDESTLAENGE:.2f} s)."
        if start < -0.001 or ende > self.szene.dauer + 0.001:
            return "Der Bereich liegt außerhalb der Aufnahme."
        return ""

    def neues_segment(self, start: float, ende: float, art: str, text: str = "",
                      sprecher: str = "") -> Segment:
        segment = Segment(nummer=self.szene.naechste_nummer,
                          start=round(max(0.0, start), 3),
                          ende=round(min(self.szene.dauer, ende), 3),
                          art=art, text=text.strip(), sprecher=sprecher)
        self.szene.naechste_nummer += 1
        self.szene.segmente.append(segment)
        return segment

    def kopieren(self, start: float, ende: float, ersetzt: int = 0) -> dict:
        """Ein Stück der englischen Spur unverändert in die deutsche übernehmen."""
        fehler = self._pruefe_bereich(start, ende)
        if fehler:
            return {"ok": False, "meldung": fehler}
        if ersetzt:
            self.szene.segmente = [s for s in self.szene.segmente if s.nummer != ersetzt]
        segment = self.neues_segment(start, ende, "kopie")
        teil = ausschnitt(self._quelldaten, segment.start, segment.ende)
        ziel = Path(self.szene.arbeitsordner) / f"seg_{segment.nummer:03d}_kopie.wav"
        schreibe_wav(teil, ziel)
        segment.datei = str(ziel)
        segment.veraltet = False
        self._de_daten = None
        self.meldung = (f"Original übernommen: {segment.start:.2f} bis "
                        f"{segment.ende:.2f} s")
        return {"ok": True, "nummer": segment.nummer, **self.zustand()}

    def sprechen(self, start: float, ende: float, text: str, einstellungen: dict) -> dict:
        """
        Deutschen Text für den markierten Bereich erzeugen.

        Die Stimme kommt aus genau diesem Bereich der englischen Spur, und die
        Länge wird auf den Bereich festgenagelt - deshalb passt das Ergebnis
        hinterher exakt in seine Lücke.
        """
        fehler = self._pruefe_bereich(start, ende)
        if fehler:
            return {"ok": False, "meldung": fehler}
        if not (text or "").strip():
            return {"ok": False, "meldung": "Bitte einen Text eingeben."}

        segment = self.neues_segment(start, ende, "tts", text)
        ordner = Path(self.szene.arbeitsordner)
        probe = ordner / f"seg_{segment.nummer:03d}_probe.wav"
        schreibe_wav(ausschnitt(self._quelldaten, segment.start, segment.ende), probe)
        segment.sprecher = str(probe)
        return self._erzeugen(segment, einstellungen)

    def neu_erzeugen(self, nummer: int, text: str, einstellungen: dict,
                     zustand_laden: bool = True) -> dict:
        segment = self.szene.segment(nummer)
        if segment is None:
            return {"ok": False, "meldung": f"Segment {nummer} gibt es nicht."}
        if segment.art != "tts":
            return {"ok": False, "meldung": "Nur gesprochene Segmente lassen sich neu erzeugen."}
        if (text or "").strip():
            segment.text = text.strip()
        if not segment.sprecher or not Path(segment.sprecher).exists():
            probe = Path(self.szene.arbeitsordner) / f"seg_{segment.nummer:03d}_probe.wav"
            schreibe_wav(ausschnitt(self._quelldaten, segment.start, segment.ende), probe)
            segment.sprecher = str(probe)
        return self._erzeugen(segment, einstellungen, zustand_laden)

    def _erzeugen(self, segment: Segment, einstellungen: dict,
                  zustand_laden: bool = True) -> dict:
        from motor import MOTOR

        from motor import ersetze_text

        ziel = Path(self.szene.arbeitsordner) / f"seg_{segment.nummer:03d}_de.wav"
        try:
            gesprochen = ersetze_text(segment.text, einstellungen.get("ersetzungen", ""))
        except ValueError as fehler:
            antwort = {"ok": False,
                       "meldung": f"Globale Textersetzungen sind ungültig: {fehler}"}
            if zustand_laden:
                antwort.update(self.zustand())
            return antwort
        auftrag = {
            "text": gesprochen,
            "text_anhang": str(einstellungen.get("anhang", "") or ""),
            "ref_audio": segment.sprecher,
            # Whisper kennt bei automatisch angelegten Szenen genau den
            # englischen Wortlaut dieses Zeitfensters. Ihn als Referenztext
            # mitzugeben ist deutlich zuverlässiger als die Probe erneut vom
            # Sprachmodell erraten zu lassen.
            "ref_text": einstellungen.get("ref_text", "") or segment.original,
            "num_step": int(einstellungen.get("num_step", 32)),
            "speed": float(einstellungen.get("speed", 1.0)),
            "ziel": str(ziel),
            # Genau die Länge des Bereichs - der Kern des Ganzen.
            "duration": segment.dauer,
            "stille_weg": bool(einstellungen.get("stille_weg", False)),
            "lautstaerke_modus": einstellungen.get("lautstaerke_modus", "aus"),
            "lautstaerke_db": float(einstellungen.get("lautstaerke_db", 0.0)),
            "ziel_pegel": float(einstellungen.get("ziel_pegel", -18.0)),
        }
        auftrag.update({name: einstellungen.get(name, effekte.STANDARD[name])
                        for name in effekte.FELDER})
        beginn = time.time()
        klang: dict = {}
        try:
            daten = als_array(MOTOR.erzeuge(**baue_argumente(auftrag)))
            daten, korrektur = nachbearbeiten(daten, auftrag, klang)
            schreibe_wav(daten, ziel)
        except Exception as fehler:
            self.szene.segmente = [s for s in self.szene.segmente
                                   if s.nummer != segment.nummer or s.fertig]
            antwort = {"ok": False, "meldung": f"{type(fehler).__name__}: {fehler}"}
            if zustand_laden:
                antwort.update(self.zustand())
            return antwort

        segment.datei = str(ziel)
        segment.veraltet = False
        self._de_daten = None
        from motor import klang_text

        zusatz = ""
        if abs(korrektur) > 0.02:
            zusatz = (f", um {abs(korrektur):.2f} s "
                      + ("gekürzt" if korrektur > 0 else "aufgefüllt"))
        pegel = klang_text(klang)
        self.meldung = (f"Segment {segment.nummer} gesprochen in "
                        f"{time.time() - beginn:.1f} s{zusatz}"
                        + (f" · {pegel}" if pegel else ""))
        antwort = {"ok": True, "nummer": segment.nummer, "meldung": self.meldung}
        if zustand_laden:
            antwort.update(self.zustand())
        else:
            self._sichern()
        return antwort

    # -- Segmente pflegen --------------------------------------
    def loeschen(self, nummer: int) -> dict:
        vorher = len(self.szene.segmente)
        self.szene.segmente = [s for s in self.szene.segmente if s.nummer != nummer]
        self._de_daten = None
        self.meldung = ("Segment gelöscht." if len(self.szene.segmente) < vorher
                        else "Segment nicht gefunden.")
        return {"ok": True, **self.zustand()}

    def umschalten(self, nummer: int) -> dict:
        segment = self.szene.segment(nummer)
        if segment is not None:
            segment.stumm = not segment.stumm
            self._de_daten = None
            self.meldung = (f"Segment {nummer} " +
                            ("stumm." if segment.stumm else "wieder aktiv."))
        return {"ok": True, **self.zustand()}

    def verschieben(self, nummer: int, start: float, ende: float) -> dict:
        """
        Anfang und Länge ändern (Ziehen an den Rändern).

        Kopien werden sofort neu aus der englischen Spur geschnitten - das
        kostet nichts. Gesprochene Segmente behalten ihre Aufnahme, werden aber
        als veraltet markiert, weil die Länge nicht mehr passt.
        """
        segment = self.szene.segment(nummer)
        if segment is None:
            return {"ok": False, "meldung": "Segment nicht gefunden."}
        fehler = self._pruefe_bereich(start, ende)
        if fehler:
            return {"ok": False, "meldung": fehler}
        # Reines Verschieben (gleiche Länge) lässt die Aufnahme gültig.
        nur_verschoben = abs((ende - start) - segment.dauer) < 0.005
        segment.start, segment.ende = round(start, 3), round(ende, 3)
        self._de_daten = None

        if nur_verschoben and segment.fertig:
            if segment.art == "kopie":
                ziel = Path(self.szene.arbeitsordner) / f"seg_{segment.nummer:03d}_kopie.wav"
                schreibe_wav(ausschnitt(self._quelldaten, segment.start, segment.ende), ziel)
                segment.datei = str(ziel)
            self.meldung = (f"Segment {nummer} verschoben nach {segment.start:.2f} s "
                            f"(Länge unverändert).")
            return {"ok": True, **self.zustand()}

        if segment.art == "kopie":
            ziel = Path(self.szene.arbeitsordner) / f"seg_{segment.nummer:03d}_kopie.wav"
            schreibe_wav(ausschnitt(self._quelldaten, segment.start, segment.ende), ziel)
            segment.datei = str(ziel)
            segment.veraltet = False
            self.meldung = (f"Segment {nummer}: {segment.start:.2f} s bis "
                            f"{segment.ende:.2f} s, neu geschnitten.")
        else:
            segment.veraltet = True
            self.meldung = (f"Segment {nummer}: jetzt {segment.dauer:.2f} s lang – "
                            f"zum Anpassen neu erzeugen (↻).")
        return {"ok": True, **self.zustand()}

    def alle_erzeugen(self, einstellungen: dict, nur_offene: bool = True,
                      melde=None) -> dict:
        """
        Alle Segmente mit Text nacheinander sprechen lassen.

        »nur_offene« lässt fertige Aufnahmen in Ruhe und nimmt nur die, denen
        noch etwas fehlt oder deren Länge sich geändert hat - so lässt sich
        eine Szene Stück für Stück aufbauen, ohne jedes Mal alles neu zu rechnen.
        """
        if not self.geladen():
            return {"ok": False, "meldung": "Erst eine Aufnahme laden."}
        offen = [s for s in self.szene.sortiert()
                 if s.art == "tts" and s.text.strip()
                 and (not nur_offene or not s.fertig or s.veraltet)]
        if not offen:
            ohne_text = sum(1 for s in self.szene.segmente
                            if s.art == "tts" and not s.text.strip())
            self.meldung = ("Nichts zu tun – alle gesprochenen Segmente sind aktuell."
                            + (f" {ohne_text} Segment(e) haben noch keinen Text."
                               if ohne_text else ""))
            return {"ok": True, **self.zustand()}

        beginn = time.time()
        fertig, fehler, letzter, abgebrochen = 0, 0, "", False
        for nummer, segment in enumerate(offen, start=1):
            if melde and melde(nummer, len(offen), segment.nummer) is False:
                abgebrochen = True
                break
            # Während eines Komplettlaufs nicht nach jedem Segment die ganze
            # Szene rendern und beide Wellenformen serialisieren. Das machte
            # große Cutscenes mit vielen Segmenten unnötig hakelig.
            antwort = self.neu_erzeugen(segment.nummer, segment.text, einstellungen,
                                         zustand_laden=False)
            if antwort.get("ok"):
                fertig += 1
            else:
                fehler += 1
                letzter = str(antwort.get("meldung", ""))
        self.meldung = (("Abgebrochen · " if abgebrochen else "")
                        + f"{fertig} von {len(offen)} Segmenten erzeugt in "
                        f"{time.time() - beginn:.0f} s"
                        + (f" · {fehler} fehlgeschlagen, zuletzt: {letzter}"
                           if fehler else ""))
        return {"ok": True, **self.zustand()}

    # -- Vorhören: erzeugen, hören, dann erst entscheiden ------
    def _merken(self, nummer: int, war_neu: bool) -> None:
        """
        Zustand eines Segments sichern, bevor die Vorschau ihn überschreibt.

        Gesichert wird auch die Aufnahme selbst, weil »neu erzeugen« immer in
        dieselbe Datei schreibt - ohne Kopie wäre die alte Fassung nach dem
        Vorhören unwiederbringlich weg.
        """
        segment = self.szene.segment(nummer)
        if segment is None:
            self._vorschau = None
            return
        sicherung = ""
        if not war_neu and segment.fertig:
            try:
                sicherung = str(Path(self.szene.arbeitsordner)
                                / f"seg_{nummer:03d}_vorher.wav")
                shutil.copy2(segment.datei, sicherung)
            except Exception:
                sicherung = ""
        self._vorschau = {"nummer": nummer, "neu": war_neu,
                          "felder": asdict(segment), "sicherung": sicherung}

    def vorschau_sprechen(self, start: float, ende: float, text: str,
                          einstellungen: dict) -> dict:
        """Neuen Bereich sprechen und dabei zurücknehmbar machen."""
        antwort = self.sprechen(start, ende, text, einstellungen)
        if antwort.get("ok") and antwort.get("nummer"):
            self._merken(int(antwort["nummer"]), war_neu=True)
            antwort["vorschau"] = True
        return antwort

    def vorschau_neu(self, nummer: int, text: str, einstellungen: dict) -> dict:
        """Vorhandenes Segment neu sprechen, alte Fassung bleibt abrufbar."""
        if self.szene.segment(nummer) is None:
            return {"ok": False, "meldung": f"Segment {nummer} gibt es nicht."}
        self._merken(nummer, war_neu=False)
        antwort = self.neu_erzeugen(nummer, text, einstellungen)
        if antwort.get("ok"):
            antwort["vorschau"] = True
        else:
            self.vorschau_verwerfen()
        return antwort

    def vorschau_behalten(self) -> dict:
        stand = self._vorschau
        self._vorschau = None
        if stand and stand.get("sicherung"):
            try:
                Path(stand["sicherung"]).unlink()
            except OSError:
                pass
        self.meldung = "Übernommen." if stand else "Nichts vorzumerken."
        return {"ok": True, **self.zustand()}

    def vorschau_verwerfen(self) -> dict:
        """Zurück auf den Stand vor der Vorschau."""
        stand = self._vorschau
        self._vorschau = None
        if not stand:
            return {"ok": True, **self.zustand()}

        nummer = int(stand["nummer"])
        if stand["neu"]:
            self.szene.segmente = [s for s in self.szene.segmente if s.nummer != nummer]
            self.meldung = "Verworfen – das Segment wurde wieder entfernt."
        else:
            felder = {k: v for k, v in stand["felder"].items()
                      if k in Segment.__dataclass_fields__}
            alt = Segment(**felder)
            self.szene.segmente = [alt if s.nummer == nummer else s
                                   for s in self.szene.segmente]
            if stand.get("sicherung") and Path(stand["sicherung"]).is_file():
                try:
                    shutil.copy2(stand["sicherung"], alt.datei)
                    Path(stand["sicherung"]).unlink()
                except Exception:
                    pass
            self.meldung = f"Verworfen – Segment {nummer} steht wieder wie vorher."
        self._de_daten = None
        return {"ok": True, **self.zustand()}

    def texte_setzen(self, texte: dict) -> dict:
        """Mehrere deutsche Texte auf einmal übernehmen (Nummer -> Text)."""
        gesetzt = 0
        for nummer, text in (texte or {}).items():
            segment = self.szene.segment(int(nummer))
            if segment is None:
                continue
            neu = str(text or "").strip()
            if neu and neu != segment.text:
                segment.text = neu
                # Die vorhandene Aufnahme spricht jetzt den falschen Text.
                segment.veraltet = bool(segment.fertig)
                gesetzt += 1
        self.meldung = f"{gesetzt} Text(e) übernommen."
        return {"ok": True, "gesetzt": gesetzt, **self.zustand()}

    def teilen(self, nummer: int, zeitpunkt: float) -> dict:
        """
        Ein Segment an der Cursorstelle in zwei zerlegen.

        Beide Hälften behalten ihren Ton - die Aufnahme wird an genau dieser
        Stelle durchgeschnitten. So lassen sich einzelne Teile anschließend
        löschen, verschieben oder neu sprechen.
        """
        segment = self.szene.segment(nummer)
        if segment is None:
            return {"ok": False, "meldung": "Segment nicht gefunden."}
        zeitpunkt = float(zeitpunkt)
        if not (segment.start + MINDESTLAENGE <= zeitpunkt <= segment.ende - MINDESTLAENGE):
            return {"ok": False,
                    "meldung": "Zum Teilen muss der Cursor mitten im Segment stehen "
                               f"(mindestens {MINDESTLAENGE:.2f} s Abstand zum Rand)."}

        teile = None
        if segment.fertig:
            try:
                _rate, daten = lies_audio(segment.datei)
                schnitt = int(round((zeitpunkt - segment.start) * ABTASTRATE))
                teile = (daten[:schnitt], daten[schnitt:])
            except Exception:
                teile = None

        zweiter = self.neues_segment(zeitpunkt, segment.ende, segment.art,
                                     segment.text, segment.sprecher)
        zweiter.original = segment.original
        zweiter.stumm = segment.stumm
        zweiter.veraltet = segment.veraltet
        segment.ende = round(zeitpunkt, 3)

        ordner = Path(self.szene.arbeitsordner)
        if teile is not None:
            for teil, ziel_segment in ((teile[0], segment), (teile[1], zweiter)):
                endung = "kopie" if ziel_segment.art == "kopie" else "de"
                ziel = ordner / f"seg_{ziel_segment.nummer:03d}_{endung}.wav"
                schreibe_wav(teil, ziel)
                ziel_segment.datei = str(ziel)
        else:
            zweiter.datei = ""
            zweiter.veraltet = True

        self._de_daten = None
        self.meldung = (f"Segment {nummer} bei {zeitpunkt:.2f} s geteilt – "
                        f"neue Teile {nummer} und {zweiter.nummer}.")
        return {"ok": True, "nummer": zweiter.nummer, **self.zustand()}

    def text_aendern(self, nummer: int, text: str) -> dict:
        """Nur den Text ändern, ohne gleich neu zu erzeugen."""
        segment = self.szene.segment(nummer)
        if segment is None:
            return {"ok": False, "meldung": "Segment nicht gefunden."}
        segment.text = (text or "").strip()
        if segment.art == "tts" and segment.fertig:
            segment.veraltet = True
            self.meldung = f"Text von Segment {nummer} geändert – zum Übernehmen neu erzeugen (↻)."
        else:
            self.meldung = f"Text von Segment {nummer} geändert."
        return {"ok": True, **self.zustand()}

    # -- Deutsche Spur -----------------------------------------
    def _belegte_bereiche(self) -> list[tuple[float, float]]:
        """Fertige oder ausdrücklich stummgeschaltete Zeitbereiche."""
        bereiche = []
        for segment in self.szene.sortiert():
            # Stumm ist eine bewusste Entscheidung für Ruhe und darf von der
            # automatischen Lückenfüllung nicht wieder mit Englisch gefüllt
            # werden. Ein unfertiges normales Segment besitzt dagegen noch
            # keine Aufnahme und zählt deshalb weiterhin als Lücke.
            if not segment.stumm and not segment.fertig:
                continue
            start = max(0.0, min(self.szene.dauer, float(segment.start)))
            ende = max(start, min(self.szene.dauer, float(segment.ende)))
            if ende > start:
                bereiche.append((start, ende))
        vereinigt = []
        for start, ende in bereiche:
            if vereinigt and start <= vereinigt[-1][1] + 0.001:
                vereinigt[-1] = (vereinigt[-1][0], max(vereinigt[-1][1], ende))
            else:
                vereinigt.append((start, ende))
        return vereinigt

    def luecken_mit_original(self, an: bool = True) -> dict:
        """
        Bereiche ohne fertiges deutsches Segment dynamisch aus EN übernehmen.

        Die Einstellung bleibt im Szenenprojekt erhalten. Neue deutsche
        Aufnahmen ersetzen ihren Bereich beim nächsten Rendern automatisch;
        deshalb muss nach späteren Erzeugungen nichts von Hand nachgeschnitten
        oder erneut aufgefüllt werden.
        """
        if not self.geladen():
            return {"ok": False, "meldung": "Erst eine Aufnahme laden."}
        self.szene.luecken_original = bool(an)
        self._de_daten = None
        if self.szene.luecken_original:
            belegt = sum(ende - start for start, ende in self._belegte_bereiche())
            frei = max(0.0, self.szene.dauer - belegt)
            self.meldung = (
                f"Englische Lückenfüllung aktiv: {frei:.2f} s ohne fertige deutsche "
                "Aufnahme werden automatisch aus dem Original übernommen."
            )
        else:
            self.meldung = (
                "Englische Lückenfüllung ausgeschaltet – unbelegte Bereiche sind wieder still."
            )
        return {"ok": True, **self.zustand()}

    def _segment_pegel(self, segment, teil, einstellungen: dict):
        """
        Ein einzelnes Segment beim Mischen auf den richtigen Pegel bringen.

        Das passiert hier und nicht nur beim Erzeugen, damit auch **schon
        fertig gedubbte** Szenen laut werden, ohne sie neu sprechen zu lassen:
        beim Speichern wird jedes Stück gemessen und, falls nötig, angehoben.

        Kopien aus dem Original bleiben unangetastet - sie sind ja bereits das
        Original und würden sich sonst von ihrer Umgebung abheben.
        """
        from motor import lautstaerke_anpassen, sprach_rms

        modus = str((einstellungen or {}).get("lautstaerke_modus", "aus") or "aus")
        if modus == "aus" or teil is None or not len(teil):
            return teil, None
        # Bei »an das Original angleichen« sind Kopien schon per Definition
        # richtig - sie kommen frisch aus der englischen Spur. Bei den anderen
        # Modi will man einen einheitlichen Pegel über die ganze Spur, dann
        # gehören sie dazu.
        if modus == "wie_original" and segment.art == "kopie":
            return teil, None

        bericht: dict = {}
        vorlage = None
        if modus == "wie_original" and self._quelldaten is not None:
            vorlage = ausschnitt(self._quelldaten, segment.start, segment.ende)
        neu = lautstaerke_anpassen(
            teil, modus, float(einstellungen.get("lautstaerke_db", 0.0)), "",
            float(einstellungen.get("ziel_pegel", -18.0)), bericht, vorlage)

        # »schon angepasst« heißt: weniger als 1 dB Abweichung. Dann bleibt
        # alles, wie es ist - sonst würde jedes Speichern minimal nachregeln.
        if abs(float(bericht.get("faktor_db", 0.0))) < 1.0:
            return teil, None
        _ = sprach_rms
        return neu, bericht

    def rendern(self, einstellungen: dict = None):
        """Legt alle Segmente auf eine stille oder mit EN gefüllte Spur."""
        import numpy as np

        einstellungen = einstellungen if einstellungen is not None else self.einstellungen
        spur = np.zeros(max(1, int(round(self.szene.dauer * ABTASTRATE))), dtype="float32")
        if self.szene.luecken_original and self._quelldaten is not None:
            anzahl = min(len(spur), len(self._quelldaten))
            spur[:anzahl] = self._quelldaten[:anzahl]
            # Nur die tatsächlich vorhandenen deutschen/kopierten Bereiche
            # sowie bewusst stumme Bereiche aus dem Originalbett ausstanzen.
            # Unfertige normale Segmente gelten als Lücke und bleiben Englisch.
            for start, ende in self._belegte_bereiche():
                von = max(0, int(round(start * ABTASTRATE)))
                bis = min(len(spur), int(round(ende * ABTASTRATE)))
                if bis > von:
                    spur[von:bis] = 0.0
        self.pegelbericht = []
        for segment in self.szene.sortiert():
            if segment.stumm or not segment.fertig:
                continue
            teil = None
            if segment.art == "kopie" and self._quelldaten is not None:
                # Kopien immer frisch aus der englischen Spur schneiden statt
                # aus ihrer Datei zu lesen. Damit stimmen sie garantiert mit
                # dem Original überein - auch in Szenen, die noch mit dem
                # falschen Kanal-Mittelwert anlegt wurden und deren Kopien
                # deshalb bis zu 15 dB zu leise auf der Platte liegen.
                teil = ausschnitt(self._quelldaten, segment.start, segment.ende)
            if teil is None or not len(teil):
                try:
                    _rate, teil = lies_audio(segment.datei)
                except Exception:
                    continue
            teil, bericht = self._segment_pegel(segment, teil, einstellungen)
            if bericht:
                self.pegelbericht.append((segment.nummer, bericht))
            von = max(0, int(round(segment.start * ABTASTRATE)))
            bis = min(len(spur), von + len(teil))
            if bis > von:
                spur[von:bis] += teil[:bis - von]
        spitze = float(np.max(np.abs(spur))) if len(spur) else 0.0
        if spitze > 0.99:
            spur *= 0.99 / spitze
        self._de_daten = spur
        return spur

    def _pegel_meldung(self) -> str:
        """Was beim Mischen an den Segmenten nachgeregelt wurde."""
        if not self.pegelbericht:
            return ""
        werte = [float(b.get("faktor_db", 0.0)) for _nr, b in self.pegelbericht]
        schnitt = sum(werte) / len(werte)
        return (f"{len(self.pegelbericht)} Segment(e) beim Mischen angepasst "
                f"({schnitt:+.1f} dB im Schnitt, "
                f"{min(werte):+.1f} bis {max(werte):+.1f} dB)")

    def kopien_auffrischen(self) -> int:
        """
        Alle übernommenen Originalstücke neu aus der englischen Spur schneiden.

        Nötig für Szenen aus älteren Fassungen: dort wurden Kopien über den
        Mittelwert aller Kanäle geschnitten und liegen deshalb bis zu 15 dB zu
        leise auf der Platte. Die Mischung holt sie sich zwar ohnehin frisch,
        aber so wird auch der Arbeitsordner wieder stimmig - unter anderem für
        das Teilen, das aus der Datei liest.
        """
        if self._quelldaten is None:
            return 0
        aufgefrischt = 0
        for segment in self.szene.segmente:
            if segment.art != "kopie":
                continue
            neu = ausschnitt(self._quelldaten, segment.start, segment.ende)
            ziel = Path(self.szene.arbeitsordner) / f"seg_{segment.nummer:03d}_kopie.wav"
            try:
                schreibe_wav(neu, ziel)
                segment.datei = str(ziel)
                aufgefrischt += 1
            except Exception:
                continue
        if aufgefrischt:
            self._de_daten = None
        return aufgefrischt

    def speichern(self, ziel, einstellungen: dict = None) -> dict:
        if not self.geladen():
            return {"ok": False, "meldung": "Erst eine Datei laden."}
        if (not any(s.fertig and not s.stumm for s in self.szene.segmente)
                and not self.szene.luecken_original):
            return {"ok": False, "meldung": "Die deutsche Spur ist noch leer."}
        if einstellungen is not None:
            self.einstellungen = dict(einstellungen)
        ziel = Path(str(ziel).strip('" '))
        try:
            kopien = self.kopien_auffrischen()
            # Frisch mischen, damit die Pegelanpassung auf jeden Fall läuft -
            # auch bei Szenen, die vor langer Zeit gedubbt wurden.
            self._de_daten = None
            gemischt = self.rendern()
            schreibe_wav(gemischt, ziel)
        except Exception as fehler:
            return {"ok": False, "meldung": f"Speichern nicht möglich: {fehler}"}
        nachgeregelt = self._pegel_meldung()
        self.meldung = (f"Deutsche Spur gespeichert: {ziel}"
                        + (f" · {nachgeregelt}" if nachgeregelt else "")
                        + (f" · {kopien} Originalstück(e) neu aus der englischen "
                           f"Spur geschnitten" if kopien else ""))
        return {"ok": True, "ziel": str(ziel), **self.zustand()}

    def bereich_uri(self, start: float, ende: float, spur: str = "en",
                    en_an: bool = True, de_an: bool = True) -> dict:
        """
        Ausschnitt als data:-Adresse zum Anhören.

        »spur« ist en, de oder beides. Bei »beides« werden beide Spuren
        gemischt, wobei die stummgeschalteten wegfallen. Stücke werden bewusst
        einzeln geholt - eine ganze Szene als data:-Adresse wäre zu groß.
        """
        import base64
        import io

        import numpy as np
        import soundfile as sf

        if not self.geladen():
            return {"ok": False, "meldung": "Erst eine Datei laden."}
        start = max(0.0, float(start))
        ende = min(self.szene.dauer, float(ende))
        if ende - start < 0.02:
            return {"ok": False, "meldung": "Der Bereich ist leer."}

        teile = []
        if spur in ("en", "beides") and en_an:
            teile.append(ausschnitt(self._quelldaten, start, ende))
        if spur in ("de", "beides") and de_an:
            deutsch = self._de_daten if self._de_daten is not None else self.rendern()
            teile.append(ausschnitt(deutsch, start, ende))
        if not teile:
            return {"ok": False, "meldung": "Beide Spuren sind stumm."}

        laenge = max(len(t) for t in teile)
        mischung = np.zeros(laenge, dtype="float32")
        for t in teile:
            mischung[:len(t)] += t
        spitze = float(np.max(np.abs(mischung))) if laenge else 0.0
        if spitze > 0.99:
            mischung *= 0.99 / spitze

        puffer = io.BytesIO()
        sf.write(puffer, mischung, ABTASTRATE, format="WAV", subtype="PCM_16")
        return {"ok": True,
                "uri": "data:audio/wav;base64,"
                       + base64.b64encode(puffer.getvalue()).decode("ascii"),
                "start": round(start, 3),
                "dauer": round(laenge / ABTASTRATE, 3)}

    # -- Automatische Vorbefüllung -----------------------------
    def texte_aus_liste(self, englisch: str, deutsch: str,
                        nur_leere: bool = True) -> dict:
        """
        Den deutschen Text der Liste auf die Segmente verteilen.

        In der Stapelliste steht zu einer langen Aufnahme der komplette
        englische **und** deutsche Text - oft ein Dutzend Sätze am Stück.
        Whisper kennt nur die englische Seite; die deutsche lag bisher
        ungenutzt daneben und musste von Hand verteilt werden.

        Zugeordnet wird über die englischen Wortlaute der Segmente: Beide
        Texte werden in Sätze zerlegt, paarweise verknüpft, und jedes Segment
        bekommt die deutschen Sätze, deren englische Gegenstücke am besten zu
        dem passen, was dort gesprochen wird.
        """
        import textverteilung

        deutsch = str(deutsch or "").strip()
        if not deutsch:
            return {"gesetzt": 0, "meldung": ""}
        segmente = [s for s in self.szene.sortiert() if s.art == "tts"]
        if not segmente:
            return {"gesetzt": 0, "meldung": ""}

        gehoerte = [s.original or s.text for s in segmente]
        verteilt = textverteilung.verteile(gehoerte, str(englisch or ""), deutsch)
        gesetzt = 0
        for segment, text in zip(segmente, verteilt):
            text = str(text or "").strip()
            if not text or (nur_leere and segment.text.strip()):
                continue
            if text != segment.text:
                segment.text = text
                segment.veraltet = bool(segment.fertig)
                gesetzt += 1
        if gesetzt:
            self._de_daten = None
        return {
            "gesetzt": gesetzt,
            "meldung": (f"{gesetzt} deutsche Texte aus der Liste übernommen"
                        if gesetzt else
                        "Aus der Liste kam nichts Neues dazu"),
        }

    def vorbefuellen(self, modell: str = "medium", geraet: str = "auto",
                     sprache: str = "en", mindestens: float = 0.4,
                     englisch: str = "", deutsch: str = "", dienst=None,
                     dienst_stoppen: bool = True) -> dict:
        """
        Whisper über die ganze Szene laufen lassen und daraus Segmente anlegen.

        Das erspart bei einer langen Cutscene das Setzen von Dutzenden
        Bereichen von Hand: Jeder erkannte Sprechabschnitt wird ein Segment
        mit Zeiten und englischem Text. Übersetzt wird nichts - der deutsche
        Text bleibt leer und wird von Hand oder später ergänzt.
        """
        if not self.geladen():
            return {"ok": False, "meldung": "Erst eine Aufnahme laden."}
        try:
            import whisper_dienst
        except Exception as fehler:
            return {"ok": False, "meldung": f"Whisper nicht verfügbar: {fehler}"}

        dienst = dienst or whisper_dienst.WhisperDienst()
        if not dienst.verfuegbar():
            return {"ok": False,
                    "meldung": "Whisper ist nicht eingerichtet. Bitte im Studio "
                               "»OmniVoice installieren« erneut ausführen."}
        beginn = time.time()
        try:
            antwort = dienst.transkribiere(self.szene.quelle, sprache=sprache,
                                           modell=modell, geraet=geraet,
                                           segmente=True, szenenmodus=True)
        except Exception as fehler:
            return {"ok": False, "meldung": f"Whisper: {fehler}"}
        finally:
            if dienst_stoppen:
                dienst.stoppen()

        gefunden = antwort.get("segmente") or []
        vorhanden = [(s.start, s.ende) for s in self.szene.segmente]
        neu = 0
        for teil in gefunden:
            start = float(teil.get("start", 0.0))
            ende = float(teil.get("end", teil.get("ende", 0.0)))
            if ende - start < mindestens:
                continue
            # Nichts anlegen, wo schon ein Segment liegt.
            if any(start < b and ende > a for a, b in vorhanden):
                continue
            segment = self.neues_segment(start, ende, "tts", "")
            segment.original = str(teil.get("text", "")).strip()
            vorhanden.append((segment.start, segment.ende))
            neu += 1

        self._de_daten = None
        # Steht in der Liste schon ein deutscher Text zu dieser Aufnahme, wird
        # er gleich mit auf die Abschnitte verteilt - sonst müsste man ihn von
        # Hand aufteilen, obwohl er längst da ist.
        verteilt = self.texte_aus_liste(englisch, deutsch)
        self.meldung = (f"Whisper hat {len(gefunden)} Abschnitte erkannt, "
                        f"{neu} neue Segmente angelegt ({time.time() - beginn:.0f} s). "
                        + (f"{verteilt['gesetzt']} deutsche Texte kamen aus der Liste dazu."
                           if verteilt.get("gesetzt")
                           else "Jetzt die deutschen Texte eintragen."))
        return {"ok": True, **self.zustand()}

    # -- Projektdatei ------------------------------------------
    def als_projekt(self) -> dict:
        return {
            "art": "omnivoice-szene",
            "version": 1,
            "quelle": self.szene.quelle,
            "dauer": self.szene.dauer,
            "arbeitsordner": self.szene.arbeitsordner,
            "naechste_nummer": self.szene.naechste_nummer,
            "luecken_original": bool(self.szene.luecken_original),
            "segmente": [asdict(s) for s in self.szene.sortiert()],
        }

    def projekt_speichern(self, ziel) -> dict:
        ziel = Path(str(ziel).strip('" '))
        try:
            ziel.parent.mkdir(parents=True, exist_ok=True)
            ziel.write_text(json.dumps(self.als_projekt(), indent=2, ensure_ascii=False),
                            encoding="utf-8")
        except Exception as fehler:
            return {"ok": False, "meldung": f"Projekt nicht speicherbar: {fehler}"}
        self.meldung = f"Projekt gespeichert: {ziel.name}"
        return {"ok": True, **self.zustand()}

    def projekt_laden(self, pfad) -> dict:
        pfad = Path(str(pfad).strip('" '))
        try:
            daten = json.loads(pfad.read_text(encoding="utf-8"))
        except Exception as fehler:
            return {"ok": False, "meldung": f"Projekt nicht lesbar: {fehler}"}
        if daten.get("art") != "omnivoice-szene":
            return {"ok": False, "meldung": "Das ist keine Szenen-Projektdatei."}

        ergebnis = self.laden(daten.get("quelle", ""))
        if not ergebnis.get("ok"):
            return ergebnis
        self.szene.arbeitsordner = daten.get("arbeitsordner") or self.szene.arbeitsordner
        self.szene.naechste_nummer = int(daten.get("naechste_nummer", 1))
        self.szene.luecken_original = bool(daten.get("luecken_original", False))
        self.szene.segmente = [Segment(**{k: v for k, v in s.items()
                                          if k in Segment.__dataclass_fields__})
                               for s in daten.get("segmente", [])]
        fehlend = sum(1 for s in self.szene.segmente if not s.fertig)
        self.meldung = (f"Projekt geladen: {len(self.szene.segmente)} Segmente"
                        + (f", {fehlend} ohne Aufnahme" if fehlend else ""))
        return {"ok": True, **self.zustand()}
