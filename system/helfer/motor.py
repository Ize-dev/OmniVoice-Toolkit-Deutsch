#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gemeinsamer Modell-Unterbau fuer die Oberflaeche und die Arbeiter-Prozesse.

Hier steht alles, was mit OmniVoice selbst zu tun hat: Geraetewahl, Laden des
Modells, Erzeugen von Audio und Schreiben der WAV-Datei. Sowohl
oberflaeche.py (Hauptprozess) als auch arbeiter.py (Stapel-Arbeiter)
benutzen genau diesen Code - so kann es keine Unterschiede zwischen
Einzelstueck und Stapel geben.
"""

import sys
import time
from pathlib import Path

MODELL = "k2-fsa/OmniVoice"
ABTASTRATE = 24_000

# Grober Speicherbedarf eines Modells im Grafikspeicher (Gewichte, Zwischen-
# ergebnisse und Reserve). Dient nur der Empfehlung in den Einstellungen.
VRAM_JE_ARBEITER = 3.5


def sag(text: str = "") -> None:
    sys.stdout.write(text + "\n")
    sys.stdout.flush()


class Motor:
    def __init__(self) -> None:
        self.modell = None
        self.geraet = "cpu"
        self.geraetename = "Prozessor"
        self.dtype_name = "float32"
        self.vram_gb = 0.0

    def waehle_geraet(self):
        import torch

        try:
            if torch.cuda.is_available():
                self.geraet = "cuda:0"
                self.geraetename = torch.cuda.get_device_name(0)
                self.dtype_name = "float16"
                self.vram_gb = torch.cuda.get_device_properties(0).total_memory / 1024 ** 3
                return torch.float16
        except Exception:
            pass
        try:
            if hasattr(torch, "xpu") and torch.xpu.is_available():
                self.geraet = "xpu:0"
                self.geraetename = torch.xpu.get_device_name(0)
                self.dtype_name = "float16"
                return torch.float16
        except Exception:
            pass
        self.geraet = "cpu"
        self.geraetename = "Prozessor (CPU)"
        self.dtype_name = "float32"
        return torch.float32

    def laden(self, still: bool = False) -> None:
        import torch  # noqa: F401
        from omnivoice import OmniVoice

        dtype = self.waehle_geraet()
        if not still:
            sag(f"Gerät: {self.geraetename}  ({self.geraet}, {self.dtype_name})")
            sag("Sprachmodell wird in den Speicher geladen – das dauert einen Moment …")
        beginn = time.time()
        try:
            self.modell = OmniVoice.from_pretrained(MODELL, device_map=self.geraet, dtype=dtype)
        except TypeError:
            self.modell = OmniVoice.from_pretrained(MODELL, device_map=self.geraet)
        if not still:
            sag(f"Modell bereit nach {time.time() - beginn:.1f} Sekunden.")

    def erzeuge(self, **argumente):
        """Ruft generate() auf und laesst Argumente weg, die diese Fassung nicht kennt."""
        optional = ["duration", "speed", "num_step"]
        for _versuch in range(len(optional) + 1):
            try:
                return self.modell.generate(**argumente)
            except TypeError as fehler:
                name = next((n for n in optional if n in argumente and n in str(fehler)), None)
                if name is None:
                    name = next((n for n in optional if n in argumente), None)
                if name is None:
                    raise
                sag(f"Hinweis: »{name}« kennt diese OmniVoice-Fassung nicht und wird weggelassen.")
                argumente.pop(name)
                optional.remove(name)
        return self.modell.generate(**argumente)


MOTOR = Motor()


def empfohlene_arbeiter(vram_gb: float) -> int:
    """Wie viele Arbeiter passen grob in den Grafikspeicher?"""
    if vram_gb <= 0:
        return 1
    return max(1, min(8, int((vram_gb - 2.0) / VRAM_JE_ARBEITER)))


def als_array(ergebnis):
    import numpy as np

    if isinstance(ergebnis, (list, tuple)):
        if not ergebnis:
            raise RuntimeError("Das Modell hat kein Audio zurückgegeben.")
        ergebnis = ergebnis[0]
    daten = np.asarray(ergebnis)
    if daten.ndim > 1:
        daten = daten.reshape(-1)
    return daten.astype("float32", copy=False)


def schreibe_wav(daten, ziel: Path) -> None:
    import soundfile as sf

    ziel.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(ziel), daten, ABTASTRATE)


def audiolaenge(pfad) -> float:
    """Laenge einer Audiodatei in Sekunden (0.0, wenn nicht lesbar)."""
    if not pfad:
        return 0.0
    try:
        import soundfile as sf

        return float(sf.info(str(pfad)).duration)
    except Exception:
        pass
    try:
        import wave

        with wave.open(str(pfad), "rb") as datei:
            rate = datei.getframerate()
            return datei.getnframes() / rate if rate else 0.0
    except Exception:
        return 0.0


def ziel_dauer(auftrag: dict) -> float:
    """
    Gewuenschte Laenge der Ausgabe in Sekunden (0 = keine Vorgabe).

    Entweder fest vorgegeben oder von der Sprachprobe uebernommen, jeweils
    zuzueglich des eingestellten Versatzes.
    """
    if auftrag.get("duration"):
        return float(auftrag["duration"])
    if auftrag.get("dauer_von_probe") and auftrag.get("ref_audio"):
        laenge = audiolaenge(auftrag["ref_audio"]) + float(auftrag.get("dauer_offset", 0.0))
        return laenge if laenge > 0.2 else 0.0
    return 0.0


def baue_argumente(auftrag: dict) -> dict:
    argumente = {
        "text": auftrag["text"],
        "num_step": int(auftrag.get("num_step", 32)),
        "speed": float(auftrag.get("speed", 1.0)),
    }
    if auftrag.get("ref_audio"):
        argumente["ref_audio"] = auftrag["ref_audio"]
    if auftrag.get("ref_text"):
        argumente["ref_text"] = auftrag["ref_text"]

    dauer = ziel_dauer(auftrag)
    if dauer > 0:
        argumente["duration"] = dauer
        # OmniVoice legt in der Nachbearbeitung 0,1 s Stille an JEDE Seite
        # (pad_duration). Die Datei waere damit immer 0,2 s laenger als die
        # Vorlage - fuer eine Vertonung unbrauchbar. Also abschalten.
        argumente["pad_duration"] = 0.0
    return argumente


# ------------------------------------------------------------
# Klangbearbeitung nach dem Erzeugen
# ------------------------------------------------------------

def _rms(daten) -> float:
    import numpy as np

    if daten is None or len(daten) == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(daten, dtype="float64"))))


# ------------------------------------------------------------
# Textersetzungen vor der Spracherzeugung
# ------------------------------------------------------------

def _ersetzungswert(text: str) -> str:
    text = str(text or "").strip()
    if text in ('""', "''"):
        return ""
    return (text.replace(r"\r", "\r").replace(r"\n", "\n")
            .replace(r"\t", "\t").replace(r"\\", "\\"))


def parse_ersetzungen(regeltext: str) -> list:
    """Eine Regel je Zeile: Suchtext => Ersatz; \\r/\\n/\\t werden verstanden."""
    regeln = []
    for nummer, zeile in enumerate(str(regeltext or "").splitlines(), start=1):
        if not zeile.strip() or zeile.lstrip().startswith("#"):
            continue
        if "=>" not in zeile:
            raise ValueError(f"Ersetzungsregel {nummer} braucht »=>«.")
        suche, ersatz = zeile.split("=>", 1)
        suche, ersatz = _ersetzungswert(suche), _ersetzungswert(ersatz)
        if not suche:
            raise ValueError(f"Ersetzungsregel {nummer} hat keinen Suchtext.")
        regeln.append((suche, ersatz))
    return regeln


def ersetze_text(text: str, regeltext: str) -> str:
    ergebnis = str(text or "")
    for suche, ersatz in parse_ersetzungen(regeltext):
        ergebnis = ergebnis.replace(suche, ersatz)
    return ergebnis


FENSTER = 0.02        # 20 ms - die uebliche Fensterbreite fuer Sprachpegel
ZIEL_PEGEL_DB = -18.0     # Sprachpegel beim Normalisieren (Effektivwert)
SPITZE_DB = -1.0          # darueber wird nie ausgesteuert


def zu_mono(daten):
    """
    Mehrkanaliges Material auf eine Spur bringen, ohne den Pegel zu verlieren.

    Der naheliegende Mittelwert ueber alle Kanaele ist fuer Spielaufnahmen
    falsch: Liegt die Sprache nur auf dem Center einer 5.1-Datei, teilt der
    Mittelwert durch sechs - die Aufnahme wirkt dann ueber 15 dB leiser, als
    sie ist. Gemittelt wird deshalb nur ueber die Kanaele, die ueberhaupt
    etwas enthalten.
    """
    import numpy as np

    daten = np.asarray(daten)
    if daten.ndim <= 1:
        return np.asarray(daten, dtype="float32")
    if daten.shape[1] == 1:
        return np.asarray(daten[:, 0], dtype="float32")

    spitzen = np.max(np.abs(daten), axis=0)
    lautester = float(np.max(spitzen)) if len(spitzen) else 0.0
    if lautester <= 0.0:
        return np.zeros(len(daten), dtype="float32")
    # Alles, was mehr als 40 dB unter dem lautesten Kanal liegt, ist Beiwerk
    # (Raumhall, Uebersprechen) und darf den Pegel nicht verduennen.
    traegt = spitzen >= lautester * (10.0 ** (-40.0 / 20.0))
    if not traegt.any():
        traegt = spitzen >= lautester
    return np.asarray(daten[:, traegt].mean(axis=1), dtype="float32")


def lies_mono(pfad):
    """Datei als einspurige Fliesskommawerte - Pegel bleibt erhalten."""
    import soundfile as sf

    daten, rate = sf.read(str(pfad), dtype="float32", always_2d=False)
    return zu_mono(daten), int(rate)


def _pegel(daten, fenster: float = FENSTER):
    """Effektivwert je kurzem Fenster - der Verlauf der Lautheit."""
    import numpy as np

    breite = max(1, int(fenster * ABTASTRATE))
    anzahl = len(daten) // breite
    if anzahl < 1:
        return np.array([_rms(daten)], dtype="float64"), breite
    teil = np.asarray(daten[:anzahl * breite], dtype="float64").reshape(anzahl, breite)
    return np.sqrt(np.mean(np.square(teil), axis=1)), breite


def sprach_rms(daten, abstand_db: float = 25.0) -> float:
    """
    Lautheit der wirklich gesprochenen Stellen.

    Der schlichte Effektivwert ueber alles taugt zum Angleichen nicht: Enthaelt
    ein markierter Bereich mehrere Sekunden Ruhe, zieht die Ruhe den Wert nach
    unten und das Ergebnis wird viel zu leise. Gemessen wird deshalb nur, was
    nah genug am lautesten Fenster liegt.
    """
    import numpy as np

    if daten is None or len(daten) == 0:
        return 0.0
    pegel, _breite = _pegel(daten)
    lautestes = float(np.max(pegel)) if len(pegel) else 0.0
    if lautestes <= 0.0:
        return 0.0
    grenze = lautestes * (10.0 ** (-abs(abstand_db) / 20.0))
    aktiv = pegel[pegel >= grenze]
    if not len(aktiv):
        return float(lautestes)
    return float(np.sqrt(np.mean(np.square(aktiv))))


def stille_kuerzen(daten, abstand_db: float = 32.0, rand: float = 0.03,
                   halten: float = 0.06):
    """
    Entfernt die Ruhe am Anfang und laesst einen kleinen Vorlauf stehen.

    Gemessen wird der Pegelverlauf in 20-ms-Fenstern, und die Schwelle liegt
    einen festen Abstand unter der lautesten Stelle. Der frueher benutzte
    Vergleich einzelner Abtastwerte mit der Spitze (-45 dB) hat bei echten
    Aufnahmen so gut wie nie gegriffen: Schon ein Grundrauschen von -60 dB
    reicht, damit gleich der erste Wert ueber der Schwelle liegt und nichts
    weggeschnitten wird. Zusaetzlich muss der Pegel eine Weile oben bleiben,
    damit ein einzelner Knacks den Anfang nicht rettet.
    """
    import numpy as np

    if daten is None or len(daten) == 0:
        return daten
    pegel, breite = _pegel(daten)
    lautestes = float(np.max(pegel)) if len(pegel) else 0.0
    if lautestes <= 0.0:
        return daten
    grenze = lautestes * (10.0 ** (-abs(abstand_db) / 20.0))
    noetig = max(1, int(round(halten / FENSTER)))

    laut = pegel >= grenze
    beginn = -1
    for i in range(len(laut) - noetig + 1):
        if laut[i] and laut[i:i + noetig].all():
            beginn = i
            break
    if beginn <= 0:
        return daten
    start = max(0, beginn * breite - int(rand * ABTASTRATE))
    return daten[start:]


def _db(wert: float) -> float:
    import numpy as np

    return float(20.0 * np.log10(max(float(wert), 1e-9)))


def lautstaerke_anpassen(daten, modus: str, db: float = 0.0, referenz: str = "",
                         ziel_db: float = ZIEL_PEGEL_DB, bericht: dict = None,
                         referenz_daten=None):
    """
    »db«             feste Verstaerkung in Dezibel
    »wie_original«   gleicht die Lautheit der englischen Aufnahme an
    »normalisieren«  bringt die Aufnahme auf einen festen Sprachpegel

    In allen Faellen wird eine Uebersteuerung abgefangen. Was gemessen und
    angewendet wurde, landet in »bericht« - ohne diese Zahlen laesst sich ein
    "zu leise" nicht auseinanderhalten.
    """
    import numpy as np

    if bericht is None:
        bericht = {}
    if daten is None or len(daten) == 0 or modus in ("", "aus", None):
        bericht["modus"] = "aus"
        return daten

    ist = sprach_rms(daten)
    bericht.update({"modus": modus, "vorher_db": round(_db(ist), 1),
                    "vorher_spitze": round(float(np.max(np.abs(daten))), 3)})
    faktor = 1.0

    if modus == "db":
        if abs(float(db)) < 0.01:
            bericht["hinweis"] = "0 dB - nichts zu tun"
            return daten
        faktor = 10.0 ** (float(db) / 20.0)

    elif modus == "wie_original":
        if referenz_daten is not None:
            # Beim Mischen einer Szene liegt der passende Ausschnitt der
            # englischen Spur schon im Speicher - dann muss nichts gelesen
            # werden, und die Vorlage passt genau zum Segment.
            vorlage = zu_mono(referenz_daten)
        else:
            try:
                vorlage, _rate = lies_mono(referenz)
            except Exception as fehler:
                bericht["hinweis"] = f"Vorlage nicht lesbar ({fehler}) - unveraendert"
                return daten
        # Auf beiden Seiten nur die gesprochenen Stellen vergleichen. Sonst
        # entscheidet die Menge an Ruhe im markierten Bereich darueber, wie
        # laut das Ergebnis wird - vier Sekunden Pause druecken es um rund
        # 7 dB nach unten, und genau das klingt dann "viel zu leise".
        ziel = sprach_rms(vorlage)
        bericht["vorlage_db"] = round(_db(ziel), 1)
        if ziel <= 0.0 or ist <= 0.0:
            bericht["hinweis"] = "Vorlage oder Ergebnis ist still - unveraendert"
            return daten
        faktor = float(np.clip(ziel / ist, 0.05, 64.0))

    elif modus == "normalisieren":
        if ist <= 0.0:
            bericht["hinweis"] = "Ergebnis ist still - unveraendert"
            return daten
        bericht["ziel_db"] = round(float(ziel_db), 1)
        faktor = float(np.clip((10.0 ** (float(ziel_db) / 20.0)) / ist, 0.05, 64.0))

    else:
        bericht["hinweis"] = f"unbekannter Modus »{modus}« - unveraendert"
        return daten

    daten = np.asarray(daten, dtype="float32") * faktor
    grenze = 10.0 ** (SPITZE_DB / 20.0)
    spitze = float(np.max(np.abs(daten)))
    gebremst = 0.0
    if spitze > grenze:
        gebremst = _db(spitze / grenze)
        daten = daten * (grenze / spitze)
    bericht.update({
        "faktor_db": round(_db(faktor), 1),
        "nachher_db": round(_db(sprach_rms(daten)), 1),
        "nachher_spitze": round(float(np.max(np.abs(daten))), 3),
        "gebremst_db": round(gebremst, 1),
    })
    return daten.astype("float32", copy=False)


def laenge_erzwingen(daten, sekunden: float, ausblenden: float = 0.015):
    """
    Bringt die Aufnahme auf genau die gewuenschte Laenge.

    Noetig, weil OmniVoice die Vorgabe nur ungefaehr trifft: die eigene
    Nachbearbeitung schneidet Stille weg und legt Ruhe an die Raender. Zu lang
    darf eine Vertonung aber nie sein - sie passt sonst nicht in ihren Platz.
    Zu kurz wird mit Stille aufgefuellt, zu lang wird mit kurzer Ausblendung
    abgeschnitten (sonst knackt es).

    Liefert (Daten, Korrektur in Sekunden): positiv = gekuerzt, negativ = verlaengert.
    """
    import numpy as np

    ziel = int(round(float(sekunden) * ABTASTRATE))
    if ziel <= 0 or daten is None or len(daten) == ziel:
        return daten, 0.0
    abweichung = (len(daten) - ziel) / float(ABTASTRATE)
    if len(daten) > ziel:
        daten = np.array(daten[:ziel], dtype="float32", copy=True)
        blende = min(int(ausblenden * ABTASTRATE), len(daten))
        if blende > 1:
            daten[-blende:] *= np.linspace(1.0, 0.0, blende, dtype="float32")
    else:
        daten = np.concatenate([np.asarray(daten, dtype="float32"),
                                np.zeros(ziel - len(daten), dtype="float32")])
    return daten, abweichung


def klang_text(bericht: dict) -> str:
    """Was die Lautstaerkeanpassung gemessen und getan hat, in einem Satz."""
    if not bericht or bericht.get("modus") in (None, "aus"):
        return ""
    teile = [f"{bericht.get('vorher_db', 0):.1f} dB"]
    if "vorlage_db" in bericht:
        teile.append(f"Vorlage {bericht['vorlage_db']:.1f} dB")
    if "ziel_db" in bericht:
        teile.append(f"Ziel {bericht['ziel_db']:.1f} dB")
    if bericht.get("hinweis"):
        return "Lautstärke: " + ", ".join(teile) + " – " + bericht["hinweis"]
    teile.append(f"{bericht.get('faktor_db', 0):+.1f} dB")
    teile.append(f"jetzt {bericht.get('nachher_db', 0):.1f} dB "
                 f"(Spitze {bericht.get('nachher_spitze', 0):.2f})")
    if bericht.get("gebremst_db", 0) > 0.05:
        teile.append(f"um {bericht['gebremst_db']:.1f} dB gebremst")
    return "Lautstärke: " + ", ".join(teile)


def nachbearbeiten(daten, auftrag: dict, bericht: dict = None):
    """
    Stille kuerzen, Lautstaerke anpassen, Laenge einhalten.
    Gilt fuer Einzelstueck und Stapel gleichermassen.

    Liefert (Daten, Korrektur in Sekunden).
    """
    if auftrag.get("stille_weg"):
        daten = stille_kuerzen(daten)
    modus = auftrag.get("lautstaerke_modus", "aus")
    if modus and modus != "aus":
        daten = lautstaerke_anpassen(
            daten, modus, auftrag.get("lautstaerke_db", 0.0),
            auftrag.get("ref_audio", ""),
            float(auftrag.get("ziel_pegel", ZIEL_PEGEL_DB)),
            bericht if bericht is not None else {})
    korrektur = 0.0
    dauer = ziel_dauer(auftrag)
    if dauer > 0 and auftrag.get("laenge_erzwingen", True):
        daten, korrektur = laenge_erzwingen(daten, dauer)
    return daten, korrektur


def fuehre_auftrag_aus(auftrag: dict) -> dict:
    """
    Erzeugt eine einzelne Datei. Wird sowohl im Hauptprozess als auch in den
    Arbeiter-Prozessen benutzt und wirft niemals - Fehler kommen als Ergebnis
    zurueck, damit ein Stapel daran nicht zerbricht.
    """
    beginn = time.time()
    klang: dict = {}
    try:
        daten = als_array(MOTOR.erzeuge(**baue_argumente(auftrag)))
        daten, korrektur = nachbearbeiten(daten, auftrag, klang)
        schreibe_wav(daten, Path(auftrag["ziel"]))
        return {
            "id": auftrag.get("id"),
            "ok": True,
            "sekunden": time.time() - beginn,
            "ton": len(daten) / ABTASTRATE,
            "korrektur": korrektur,
            "klang": klang,
            "fehler": "",
        }
    except Exception as fehler:
        return {
            "id": auftrag.get("id"),
            "ok": False,
            "sekunden": time.time() - beginn,
            "ton": 0.0,
            "korrektur": 0.0,
            "fehler": f"{type(fehler).__name__}: {fehler}",
        }
