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
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path

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

    daten, rate = sf.read(str(pfad), dtype="float32", always_2d=False)
    if getattr(daten, "ndim", 1) > 1:
        daten = daten.mean(axis=1)
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

    def neu_erzeugen(self, nummer: int, text: str, einstellungen: dict) -> dict:
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
        return self._erzeugen(segment, einstellungen)

    def _erzeugen(self, segment: Segment, einstellungen: dict) -> dict:
        from motor import MOTOR

        ziel = Path(self.szene.arbeitsordner) / f"seg_{segment.nummer:03d}_de.wav"
        auftrag = {
            "text": segment.text,
            "ref_audio": segment.sprecher,
            "ref_text": einstellungen.get("ref_text", ""),
            "num_step": int(einstellungen.get("num_step", 32)),
            "speed": float(einstellungen.get("speed", 1.0)),
            "ziel": str(ziel),
            # Genau die Länge des Bereichs - der Kern des Ganzen.
            "duration": segment.dauer,
            "stille_weg": bool(einstellungen.get("stille_weg", False)),
            "lautstaerke_modus": einstellungen.get("lautstaerke_modus", "aus"),
            "lautstaerke_db": float(einstellungen.get("lautstaerke_db", 0.0)),
        }
        beginn = time.time()
        try:
            daten = als_array(MOTOR.erzeuge(**baue_argumente(auftrag)))
            daten, korrektur = nachbearbeiten(daten, auftrag)
            schreibe_wav(daten, ziel)
        except Exception as fehler:
            self.szene.segmente = [s for s in self.szene.segmente
                                   if s.nummer != segment.nummer or s.fertig]
            return {"ok": False, "meldung": f"{type(fehler).__name__}: {fehler}",
                    **self.zustand()}

        segment.datei = str(ziel)
        segment.veraltet = False
        self._de_daten = None
        zusatz = ""
        if abs(korrektur) > 0.02:
            zusatz = (f", um {abs(korrektur):.2f} s "
                      + ("gekürzt" if korrektur > 0 else "aufgefüllt"))
        self.meldung = (f"Segment {segment.nummer} gesprochen in "
                        f"{time.time() - beginn:.1f} s{zusatz}")
        return {"ok": True, "nummer": segment.nummer, **self.zustand()}

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
    def rendern(self):
        """Legt alle Segmente an ihre Stelle auf eine stille Spur voller Länge."""
        import numpy as np

        spur = np.zeros(max(1, int(round(self.szene.dauer * ABTASTRATE))), dtype="float32")
        for segment in self.szene.sortiert():
            if segment.stumm or not segment.fertig:
                continue
            try:
                _rate, teil = lies_audio(segment.datei)
            except Exception:
                continue
            von = max(0, int(round(segment.start * ABTASTRATE)))
            bis = min(len(spur), von + len(teil))
            if bis > von:
                spur[von:bis] += teil[:bis - von]
        spitze = float(np.max(np.abs(spur))) if len(spur) else 0.0
        if spitze > 0.99:
            spur *= 0.99 / spitze
        self._de_daten = spur
        return spur

    def speichern(self, ziel) -> dict:
        if not self.geladen():
            return {"ok": False, "meldung": "Erst eine Datei laden."}
        if not any(s.fertig and not s.stumm for s in self.szene.segmente):
            return {"ok": False, "meldung": "Die deutsche Spur ist noch leer."}
        ziel = Path(str(ziel).strip('" '))
        try:
            schreibe_wav(self.rendern(), ziel)
        except Exception as fehler:
            return {"ok": False, "meldung": f"Speichern nicht möglich: {fehler}"}
        self.meldung = f"Deutsche Spur gespeichert: {ziel}"
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
    def vorbefuellen(self, modell: str = "medium", geraet: str = "auto",
                     sprache: str = "en", mindestens: float = 0.4) -> dict:
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

        dienst = whisper_dienst.WhisperDienst()
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
        self.meldung = (f"Whisper hat {len(gefunden)} Abschnitte erkannt, "
                        f"{neu} neue Segmente angelegt ({time.time() - beginn:.0f} s). "
                        f"Jetzt die deutschen Texte eintragen.")
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
        self.szene.segmente = [Segment(**{k: v for k, v in s.items()
                                          if k in Segment.__dataclass_fields__})
                               for s in daten.get("segmente", [])]
        fehlend = sum(1 for s in self.szene.segmente if not s.fertig)
        self.meldung = (f"Projekt geladen: {len(self.szene.segmente)} Segmente"
                        + (f", {fehlend} ohne Aufnahme" if fehlend else ""))
        return {"ok": True, **self.zustand()}
