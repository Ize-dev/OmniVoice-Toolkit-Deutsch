#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
============================================================
 OMNIVOICE STUDIO - Deutsches Ein-Klick-Toolkit
============================================================
 Grafische Konsolen-Oberflaeche fuer Installation, Pruefung
 und Start von OmniVoice (Stimmklonung, komplett lokal).

 Laeuft mit dem System-Python und benutzt ausschliesslich
 die Standardbibliothek - es muss also nichts vorinstalliert
 sein ausser Python selbst.
============================================================
"""

from __future__ import annotations

import collections
import ctypes
import json
import math
import os
import platform
import random
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable, Optional

# ------------------------------------------------------------
# Grunddaten
# ------------------------------------------------------------

APP_NAME = "O M N I V O I C E   S T U D I O"
APP_UNTERTITEL = "Deutsche Ein-Klick-Installation für lokale Stimmklonung"
APP_VERSION = "v1.2.0"
APP_MARKE = "iZE"
APP_FUSS = f"von {APP_MARKE} · 100 % lokal · keine Cloud · kein Konto · keine Telemetrie"

# Wunschgröße des Konsolenfensters (Spalten × Zeilen)
FENSTER_SPALTEN = 118
FENSTER_ZEILEN = 44

PAKET_NAME = "omnivoice"
MODELL_REPO = "k2-fsa/OmniVoice"
MODELL_BYTES = 3_270_000_000          # ca. 3,27 GB laut Hugging Face
WHISPER_STANDARD_MODELL = "medium"
WHISPER_REPO = "Systran/faster-whisper-medium"
WHISPER_MODELL_BYTES = 1_530_000_000  # rund 1,5 GB
WHISPER_PAKET = "faster-whisper>=1.1,<2"
TORCH_VERSION = "2.8.0"
CUDA_KANAL = "cu128"                  # CUDA 12.8 - nötig für RTX 40xx/50xx
MIN_TREIBER = 570                     # NVIDIA-Treiberversion für CUDA 12.8
PYTHON_MIN = (3, 10)
PYTHON_MAX = (3, 13)                  # für neuere Versionen gibt es kein PyTorch-Paket

SKRIPT = Path(__file__).resolve()
SYSTEM_DIR = SKRIPT.parent
TOOLKIT_DIR = SYSTEM_DIR.parent
HELFER_DIR = SYSTEM_DIR / "helfer"
DATEN_DIR = SYSTEM_DIR / "daten"
PROTOKOLL_DIR = DATEN_DIR / "protokolle"
VENV_DIR = SYSTEM_DIR / "umgebung"
WHISPER_VENV_DIR = SYSTEM_DIR / "whisper-umgebung"
CONFIG_DATEI = DATEN_DIR / "installation.json"
ERGEBNIS_DIR = TOOLKIT_DIR / "Ergebnisse"
VERSION_DATEI = TOOLKIT_DIR / "VERSION"
try:
    _version_text = VERSION_DATEI.read_text(encoding="utf-8-sig").strip()
    _version_treffer = re.fullmatch(r"v?(\d+)\.(\d+)(?:\.(\d+))?", _version_text)
    if _version_treffer:
        APP_VERSION = (
            f"v{int(_version_treffer.group(1))}.{int(_version_treffer.group(2))}."
            f"{int(_version_treffer.group(3) or 0)}"
        )
except OSError:
    pass

UPDATE_REPO = "Ize-dev/OmniVoice-Toolkit-Deutsch"
UPDATE_BRANCH = "main"
UPDATE_COMMIT_API_URL = (
    f"https://api.github.com/repos/{UPDATE_REPO}/commits/{UPDATE_BRANCH}"
)
UPDATE_BEREIT_DIR = DATEN_DIR / "update-bereit"
UPDATE_STATUS_DATEI = DATEN_DIR / "update-status.json"
UPDATE_PROTOKOLL_DATEI = PROTOKOLL_DIR / "update-anwenden.log"

EXIT_OK = 0
EXIT_OBERFLAECHE_FEHLT = 4      # meldet oberflaeche.py, wenn sie nicht startbar ist
EXIT_UPDATE_ANWENDEN = 20       # Bootstrap startet den vorbereiteten Updater
KEIN_FENSTER = 0x08000000 if os.name == "nt" else 0


def venv_python() -> Path:
    if os.name == "nt":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def venv_pip_cmd() -> list[str]:
    return [str(venv_python()), "-m", "pip"]


def whisper_python() -> Path:
    if os.name == "nt":
        return WHISPER_VENV_DIR / "Scripts" / "python.exe"
    return WHISPER_VENV_DIR / "bin" / "python"


def whisper_pip_cmd() -> list[str]:
    return [str(whisper_python()), "-m", "pip"]


# ------------------------------------------------------------
# Terminal / ANSI
# ------------------------------------------------------------

RESET = "\033[0m"
BOLD = "\033[1m"
FG_ROT = "\033[91m"
FG_GRUEN = "\033[92m"
FG_GELB = "\033[93m"
FG_MAGENTA = "\033[95m"
FG_CYAN = "\033[96m"
FG_WEISS = "\033[97m"
FG_GRAU = "\033[90m"
FG_NORMAL = "\033[37m"

CLEAR = "\033[2J"
HOME = "\033[H"
CURSOR_AUS = "\033[?25l"
CURSOR_AN = "\033[?25h"
ALT_AN = "\033[?1049h"
ALT_AUS = "\033[?1049l"


def aktiviere_ansi() -> None:
    if os.name != "nt":
        return
    try:
        kernel32 = ctypes.windll.kernel32
        for handle_id in (-11, -12):
            handle = kernel32.GetStdHandle(handle_id)
            modus = ctypes.c_uint32()
            if kernel32.GetConsoleMode(handle, ctypes.byref(modus)):
                kernel32.SetConsoleMode(handle, modus.value | 0x0004)
    except Exception:
        pass


try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, LookupError, ValueError):
    pass

aktiviere_ansi()


def terminal_groesse() -> tuple[int, int]:
    groesse = shutil.get_terminal_size((110, 40))
    return max(80, groesse.columns), max(20, groesse.lines)


def setze_fenstergroesse(spalten: int = FENSTER_SPALTEN, zeilen: int = FENSTER_ZEILEN) -> None:
    """
    Bittet das Terminal um eine passende Fenstergröße.

    Windows Terminal versteht die VT-Anweisung, kennt aber »mode con« nicht
    (das würde dort nur den Puffer verstellen und die Anzeige zerreißen).
    Die alte Konsole (conhost) versteht dafür »mode con« zuverlässig.
    Klappt beides nicht, passt sich die Anzeige selbst an - siehe zeichne().
    """
    modern = bool(os.environ.get("WT_SESSION") or os.environ.get("TERM_PROGRAM"))
    if os.name == "nt" and not modern:
        try:
            subprocess.run(f"mode con: cols={spalten} lines={zeilen}",
                           shell=True, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=10)
        except Exception:
            pass
    try:
        sys.stdout.write(f"\033[8;{zeilen};{spalten}t")
        sys.stdout.flush()
    except Exception:
        pass
    time.sleep(0.12)   # dem Terminal einen Moment zum Umschalten geben


# ------------------------------------------------------------
# Text- und Zahlenhilfen
# ------------------------------------------------------------

def kuerze(text: str, breite: int) -> str:
    if breite <= 0:
        return ""
    if len(text) <= breite:
        return text
    return text[: max(0, breite - 1)] + "…"


def fuelle(text: str, breite: int, ausrichtung: str = "links") -> str:
    text = kuerze(text, breite)
    if ausrichtung == "mitte":
        return text.center(breite)
    if ausrichtung == "rechts":
        return text.rjust(breite)
    return text.ljust(breite)


def zeile(text: str, breite: int, farbe: str = FG_NORMAL, ausrichtung: str = "links") -> str:
    innen = max(0, breite - 4)
    return (
        FG_CYAN + "║ " + RESET
        + farbe + fuelle(text, innen, ausrichtung) + RESET
        + FG_CYAN + " ║" + RESET
    )


def leerzeile(breite: int) -> str:
    return zeile("", breite)


def zeile_mit_leiste(text: str, breite: int, farbe: str = FG_NORMAL, marke: str = " ") -> str:
    """Wie zeile(), aber mit einem Bildlaufbalken in der letzten Spalte."""
    innen = max(1, breite - 4)
    return (
        FG_CYAN + "║ " + RESET
        + farbe + fuelle(text, innen - 1) + RESET
        + FG_CYAN + marke + " ║" + RESET
    )


def leisten_marken(gesamt: int, platz: int, start: int) -> list[str]:
    """Baut die Markierungen des Bildlaufbalkens für einen Ausschnitt."""
    if gesamt <= platz or platz <= 0:
        return [" "] * max(0, platz)
    daumen = max(1, round(platz * platz / gesamt))
    weg = max(1, gesamt - platz)
    pos = round((start / weg) * (platz - daumen))
    return ["█" if pos <= i < pos + daumen else "│" for i in range(platz)]


def zwei_spalten(links: str, rechts: str, breite: int) -> str:
    """Linksbündiger Text plus rechtsbündiger Zusatz innerhalb einer Zeile."""
    innen = max(1, breite - 4)
    frei = innen - len(links) - len(rechts)
    if frei < 1:
        return links
    return links + " " * frei + rechts


def rahmen_oben(breite: int) -> str:
    return FG_CYAN + "╔" + "═" * max(0, breite - 2) + "╗" + RESET


def rahmen_mitte(breite: int) -> str:
    return FG_CYAN + "╠" + "═" * max(0, breite - 2) + "╣" + RESET


def rahmen_unten(breite: int) -> str:
    return FG_CYAN + "╚" + "═" * max(0, breite - 2) + "╝" + RESET


def bytes_lesbar(wert: float) -> str:
    zahl = float(max(0.0, wert))
    for einheit in ("B", "KB", "MB", "GB", "TB"):
        if zahl < 1024.0 or einheit == "TB":
            if einheit == "B":
                return f"{zahl:.0f} B"
            return f"{zahl:.1f} {einheit}".replace(".", ",")
        zahl /= 1024.0
    return f"{zahl:.1f} TB".replace(".", ",")


def zeit_lesbar(sekunden: Optional[float]) -> str:
    if sekunden is None or sekunden != sekunden or sekunden < 0 or sekunden > 359_999:
        return "--:--"
    gesamt = int(sekunden)
    stunden, rest = divmod(gesamt, 3600)
    minuten, sek = divmod(rest, 60)
    if stunden:
        return f"{stunden:d}:{minuten:02d}:{sek:02d}"
    return f"{minuten:02d}:{sek:02d}"


def prozent(anteil: float) -> str:
    """Prozentangabe mit deutschem Dezimalkomma, feste Breite."""
    return f"{max(0.0, min(1.0, anteil)) * 100:5.1f}".replace(".", ",")


def balken(anteil: float, breite: int, voll: str = "█", halb: str = "▒", leer: str = "·") -> str:
    anteil = max(0.0, min(1.0, anteil))
    breite = max(4, breite)
    exakt = anteil * breite
    ganze = int(exakt)
    rest = exakt - ganze
    text = voll * ganze
    if ganze < breite and rest > 0.35:
        text += halb
        ganze += 1
    return text + leer * max(0, breite - ganze)


def umbruch(text: str, breite: int) -> list[str]:
    zeilen: list[str] = []
    aktuell = ""
    for wort in text.split():
        if aktuell and len(aktuell) + len(wort) + 1 > breite:
            zeilen.append(aktuell)
            aktuell = wort
        else:
            aktuell = (aktuell + " " + wort).strip()
    if aktuell:
        zeilen.append(aktuell)
    return zeilen or [""]


# ------------------------------------------------------------
# Tastatur
# ------------------------------------------------------------

class Tastatur:
    """Nicht blockierendes Lesen einzelner Tasten."""

    def __enter__(self) -> "Tastatur":
        self._alt = None
        if os.name != "nt":
            import termios
            import tty

            self._fd = sys.stdin.fileno()
            self._alt = termios.tcgetattr(self._fd)
            tty.setcbreak(self._fd)
        return self

    def __exit__(self, *_egal) -> None:
        if os.name != "nt" and self._alt is not None:
            import termios

            termios.tcsetattr(self._fd, termios.TCSADRAIN, self._alt)

    def taste(self) -> Optional[str]:
        if os.name == "nt":
            import msvcrt

            if not msvcrt.kbhit():
                return None
            erste = msvcrt.getwch()
            if erste in ("\x00", "\xe0"):
                zweite = msvcrt.getwch()
                return {
                    "H": "HOCH", "P": "RUNTER", "K": "LINKS", "M": "RECHTS",
                    "G": "ANFANG", "O": "ENDE", "I": "BILD_HOCH", "Q": "BILD_RUNTER",
                }.get(zweite)
            return {
                "\r": "ENTER", "\x1b": "ESC", " ": "LEER",
                "\t": "TAB", "\x08": "RUECK", "\x03": "ESC",
            }.get(erste, erste.lower())

        import select

        bereit, _, _ = select.select([sys.stdin], [], [], 0)
        if not bereit:
            return None
        erste = sys.stdin.read(1)
        if erste == "\x1b":
            bereit, _, _ = select.select([sys.stdin], [], [], 0.02)
            if not bereit:
                return "ESC"
            if sys.stdin.read(1) == "[":
                dritte = sys.stdin.read(1)
                return {
                    "A": "HOCH", "B": "RUNTER", "C": "RECHTS", "D": "LINKS",
                    "5": "BILD_HOCH", "6": "BILD_RUNTER",
                }.get(dritte, "ESC")
            return "ESC"
        return {"\n": "ENTER", "\r": "ENTER", " ": "LEER", "\x7f": "RUECK"}.get(erste, erste.lower())


# ------------------------------------------------------------
# Prozess- und Systemhilfen
# ------------------------------------------------------------

def lauf_kurz(befehl: list[str], timeout: float = 25.0) -> tuple[int, str]:
    """Führt einen Befehl aus und liefert (Rückgabecode, Ausgabe)."""
    try:
        ergebnis = subprocess.run(
            befehl,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            creationflags=KEIN_FENSTER,
        )
        text = ergebnis.stdout.decode("utf-8", "replace") if ergebnis.stdout else ""
        return ergebnis.returncode, text.strip()
    except FileNotFoundError:
        return 127, "Befehl nicht gefunden"
    except subprocess.TimeoutExpired:
        return 124, "Zeitüberschreitung"
    except Exception as fehler:
        return 1, f"{type(fehler).__name__}: {fehler}"


def beende_prozessbaum(prozess: Optional[subprocess.Popen]) -> None:
    if prozess is None or prozess.poll() is not None:
        return
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(prozess.pid)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=KEIN_FENSTER, timeout=15,
            )
        else:
            prozess.terminate()
    except Exception:
        try:
            prozess.kill()
        except Exception:
            pass


def freier_port(start: int = 7860, ende: int = 7899) -> Optional[int]:
    for port in range(start, ende + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as pruefer:
            try:
                pruefer.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return None


def internet_erreichbar(host: str = "pypi.org", port: int = 443, timeout: float = 5.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def ordner_bytes(pfad: Path) -> int:
    gesamt = 0
    try:
        for wurzel, _ordner, dateien in os.walk(pfad):
            for name in dateien:
                try:
                    gesamt += os.path.getsize(os.path.join(wurzel, name))
                except OSError:
                    pass
    except OSError:
        pass
    return gesamt


def arbeitsspeicher_gb() -> Optional[float]:
    if os.name != "nt":
        return None
    try:
        class Status(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_uint32), ("dwMemoryLoad", ctypes.c_uint32),
                ("ullTotalPhys", ctypes.c_uint64), ("ullAvailPhys", ctypes.c_uint64),
                ("ullTotalPageFile", ctypes.c_uint64), ("ullAvailPageFile", ctypes.c_uint64),
                ("ullTotalVirtual", ctypes.c_uint64), ("ullAvailVirtual", ctypes.c_uint64),
                ("ullAvailExtendedVirtual", ctypes.c_uint64),
            ]

        status = Status()
        status.dwLength = ctypes.sizeof(Status)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return status.ullTotalPhys / (1024 ** 3)
    except Exception:
        pass
    return None


def hub_modell_ordner(repo: str) -> Path:
    basis = os.environ.get("HF_HUB_CACHE") or os.environ.get("HF_HOME")
    if basis:
        wurzel = Path(basis)
        if wurzel.name != "hub":
            wurzel = wurzel / "hub"
    else:
        wurzel = Path.home() / ".cache" / "huggingface" / "hub"
    return wurzel / ("models--" + repo.replace("/", "--"))


def modell_ordner() -> Path:
    return hub_modell_ordner(MODELL_REPO)


def lade_config() -> Optional[dict]:
    try:
        if CONFIG_DATEI.exists():
            return json.loads(CONFIG_DATEI.read_text(encoding="utf-8"))
    except Exception:
        pass
    return None


# ------------------------------------------------------------
# Programm-Updates über GitHub
# ------------------------------------------------------------

@dataclass
class UpdateStand:
    zustand: str = "prueft"       # prueft | aktuell | verfuegbar | fehler
    lokal: str = APP_VERSION
    online: str = ""
    meldung: str = "GitHub wird geprüft …"
    commit: str = ""


def norm_version(text: str) -> str:
    """Normalisiert v1.2 / 1.2.0 auf v1.2.0 und lehnt Fremdtext ab."""
    treffer = re.fullmatch(r"\s*v?(\d+)\.(\d+)(?:\.(\d+))?\s*", str(text))
    if not treffer:
        raise ValueError(f"Ungültige Versionsnummer: {text!r}")
    teile = [int(treffer.group(1)), int(treffer.group(2)), int(treffer.group(3) or 0)]
    return "v" + ".".join(map(str, teile))


def version_schluessel(text: str) -> tuple[int, int, int]:
    return tuple(int(teil) for teil in norm_version(text)[1:].split("."))  # type: ignore[return-value]


def github_text(url: str, timeout: float = 8.0, maximum: int = 128_000) -> str:
    # raw.githubusercontent.com hält Branch-Dateien kurz im CDN-Cache. Eine
    # eindeutige Abfragekennung verhindert, dass direkt nach einem Release
    # noch die vorherige VERSION-Datei zurückkommt.
    trenner = "&" if "?" in url else "?"
    url = f"{url}{trenner}omnivoice_cache={time.time_ns()}"
    anfrage = urllib.request.Request(
        url,
        headers={
            "User-Agent": f"OmniVoice-Toolkit/{APP_VERSION}",
            "Accept": "text/plain, application/vnd.github.raw+json",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        },
    )
    with urllib.request.urlopen(anfrage, timeout=timeout) as antwort:
        daten = antwort.read(maximum + 1)
    if len(daten) > maximum:
        raise ValueError("Die Versionsantwort von GitHub ist unerwartet groß.")
    return daten.decode("utf-8-sig", "replace")


def github_api_json(url: str, timeout: float = 8.0, maximum: int = 1_000_000) -> dict:
    trenner = "&" if "?" in url else "?"
    url = f"{url}{trenner}omnivoice_cache={time.time_ns()}"
    anfrage = urllib.request.Request(
        url,
        headers={
            "User-Agent": f"OmniVoice-Toolkit/{APP_VERSION}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        },
    )
    with urllib.request.urlopen(anfrage, timeout=timeout) as antwort:
        roh = antwort.read(maximum + 1)
    if len(roh) > maximum:
        raise ValueError("Die Commit-Antwort von GitHub ist unerwartet groß.")
    daten = json.loads(roh.decode("utf-8-sig", "replace"))
    if not isinstance(daten, dict):
        raise ValueError("GitHub hat keinen gültigen Commit geliefert.")
    return daten


def entfernter_stand() -> tuple[str, str]:
    """Ermittelt zuerst den aktuellen Commit und liest danach dessen VERSION unveränderlich."""
    commit_daten = github_api_json(UPDATE_COMMIT_API_URL)
    commit = str(commit_daten.get("sha", "")).strip().lower()
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("GitHub hat keinen gültigen Commit-SHA geliefert.")

    version_url = f"https://raw.githubusercontent.com/{UPDATE_REPO}/{commit}/VERSION"
    skript_url = (
        f"https://raw.githubusercontent.com/{UPDATE_REPO}/{commit}/"
        "system/omnivoice_toolkit.py"
    )
    try:
        version = norm_version(github_text(version_url).splitlines()[0])
    except (urllib.error.HTTPError, IndexError, ValueError):
        quelltext = github_text(skript_url)
        treffer = re.search(
            r'(?m)^\s*APP_VERSION\s*=\s*["\'](v?\d+\.\d+(?:\.\d+)?)["\']',
            quelltext,
        )
        if not treffer:
            raise ValueError("Auf GitHub wurde keine gültige Versionsnummer gefunden.")
        version = norm_version(treffer.group(1))
    return version, commit


def pruefe_update_online() -> UpdateStand:
    lokal = norm_version(APP_VERSION)
    try:
        online, commit = entfernter_stand()
        if version_schluessel(online) > version_schluessel(lokal):
            return UpdateStand(
                "verfuegbar", lokal, online,
                f"Neue Version {online} ist auf GitHub verfügbar.",
                commit,
            )
        if version_schluessel(online) < version_schluessel(lokal):
            return UpdateStand(
                "aktuell", lokal, online,
                f"{lokal} ist neuer als die veröffentlichte Version {online}.",
                commit,
            )
        return UpdateStand("aktuell", lokal, online, f"{lokal} ist aktuell.", commit)
    except urllib.error.HTTPError as fehler:
        return UpdateStand(
            "fehler", lokal, "",
            f"GitHub antwortet mit HTTP {fehler.code}.",
        )
    except urllib.error.URLError as fehler:
        grund = getattr(fehler, "reason", fehler)
        return UpdateStand("fehler", lokal, "", f"GitHub ist nicht erreichbar: {grund}")
    except (OSError, ValueError) as fehler:
        return UpdateStand("fehler", lokal, "", f"Updateprüfung nicht möglich: {fehler}")


def update_pfad_erlaubt(relativ: PurePosixPath) -> bool:
    """Nur auslieferbare Programmdateien, niemals lokale Laufzeitdaten."""
    teile = relativ.parts
    if not teile or any(teil in ("", ".", "..") for teil in teile):
        return False
    if teile[0] in ("Bilder",):
        return "__pycache__" not in teile
    if teile[0] == "system":
        if len(teile) < 2 or teile[1] in ("daten", "umgebung", "whisper-umgebung"):
            return False
        return "__pycache__" not in teile and not relativ.name.endswith((".pyc", ".pyo"))
    return relativ.as_posix() in {"README.md", "STARTEN.bat", "VERSION"}


def powershell_literal(text: str | Path) -> str:
    return "'" + str(text).replace("'", "''") + "'"


def raeume_update_nach_neustart_auf() -> None:
    """Entfernt ein angewendetes Paket verzögert, nachdem dessen Helfer beendet ist."""
    try:
        status = json.loads(UPDATE_STATUS_DATEI.read_text(encoding="utf-8-sig"))
        if status.get("status") != "erfolgreich":
            return
    except Exception:
        return

    def arbeite() -> None:
        time.sleep(5)
        try:
            if UPDATE_BEREIT_DIR.exists():
                shutil.rmtree(UPDATE_BEREIT_DIR)
        except OSError:
            pass

    threading.Thread(target=arbeite, daemon=True).start()


# ------------------------------------------------------------
# Grafikkarte erkennen
# ------------------------------------------------------------

@dataclass
class Grafik:
    stufe: str = "CPU"            # CUDA | XPU | CPU
    name: str = "Keine GPU erkannt"
    treiber: str = ""
    vram_gb: float = 0.0
    hinweis: str = ""

    @property
    def beschriftung(self) -> str:
        if self.stufe == "CUDA":
            return f"NVIDIA CUDA 12.8 · {self.name}"
        if self.stufe == "XPU":
            return f"Intel Arc (XPU) · {self.name}"
        return f"Prozessor (CPU) · {self.name}"


def finde_nvidia_smi() -> Optional[str]:
    pfad = shutil.which("nvidia-smi")
    if pfad:
        return pfad
    standard = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "nvidia-smi.exe"
    if standard.exists():
        return str(standard)
    return None


def erkenne_grafik() -> Grafik:
    smi = finde_nvidia_smi()
    if smi:
        code, ausgabe = lauf_kurz(
            [smi, "--query-gpu=name,driver_version,memory.total",
             "--format=csv,noheader,nounits"], timeout=20,
        )
        if code == 0 and ausgabe:
            teile = [t.strip() for t in ausgabe.splitlines()[0].split(",")]
            name = teile[0] if teile else "NVIDIA GPU"
            treiber = teile[1] if len(teile) > 1 else "0"
            try:
                vram = float(teile[2]) / 1024.0 if len(teile) > 2 else 0.0
            except ValueError:
                vram = 0.0
            try:
                haupt = int(str(treiber).split(".")[0])
            except ValueError:
                haupt = 0
            if haupt >= MIN_TREIBER:
                return Grafik("CUDA", name, treiber, vram,
                              "CUDA-Beschleunigung wird genutzt – die schnellste Variante.")
            return Grafik(
                "CPU", name, treiber, vram,
                f"Der Grafiktreiber {treiber} ist zu alt für CUDA 12.8 (nötig ist {MIN_TREIBER} oder neuer). "
                "Bitte den NVIDIA-Treiber aktualisieren und danach im Menü »Reparieren« wählen.",
            )

    name = ""
    if os.name == "nt":
        code, ausgabe = lauf_kurz(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             "Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name"],
            timeout=25,
        )
        if code == 0 and ausgabe:
            for kandidat in ausgabe.splitlines():
                kandidat = kandidat.strip()
                if kandidat and not re.search(r"Microsoft|Basic Display|VMware|VirtualBox|Parsec|Remote", kandidat, re.I):
                    name = kandidat
                    break

    if name and re.search(r"Intel.*(Arc|Battlemage|Alchemist)", name, re.I):
        return Grafik("XPU", name, "", 0.0, "Intel-Arc-Beschleunigung (XPU) wird genutzt.")
    if name:
        return Grafik("CPU", name, "", 0.0,
                      "Für diese Grafikkarte gibt es keine unterstützte Beschleunigung – "
                      "OmniVoice läuft über den Prozessor und ist dadurch deutlich langsamer.")
    return Grafik("CPU", "Keine dedizierte Grafikkarte", "", 0.0,
                  "Es wurde keine unterstützte Grafikkarte gefunden – OmniVoice läuft über den Prozessor.")


# ------------------------------------------------------------
# Schritte und Aufgabenzustand
# ------------------------------------------------------------

@dataclass
class Schritt:
    key: str
    titel: str
    hinweis: str
    schaetzung: float
    status: str = "wartet"          # wartet | laeuft | fertig | fehler | uebersprungen
    begonnen: float = 0.0
    beendet: float = 0.0
    fortschritt: Optional[float] = None

    @property
    def laufzeit(self) -> float:
        if not self.begonnen:
            return 0.0
        return (self.beendet or time.time()) - self.begonnen

    def gewicht(self) -> float:
        if self.status in ("fertig", "uebersprungen", "fehler"):
            return max(1.0, self.laufzeit)
        if self.status == "laeuft":
            return max(self.schaetzung, self.laufzeit)
        return max(1.0, self.schaetzung)

    def anteil(self) -> float:
        if self.status in ("fertig", "uebersprungen"):
            return 1.0
        if self.status in ("wartet", "fehler"):
            return 0.0
        if self.fortschritt is not None:
            return max(0.0, min(1.0, self.fortschritt))
        return min(0.95, self.laufzeit / max(2.0, self.schaetzung))

    def restzeit(self) -> float:
        if self.status == "wartet":
            return max(1.0, self.schaetzung)
        if self.status != "laeuft":
            return 0.0
        anteil = self.anteil()
        if anteil > 0.04 and self.laufzeit > 5:
            return max(1.0, self.laufzeit * (1.0 - anteil) / anteil)
        return max(2.0, self.schaetzung - self.laufzeit)


class Abbruch(Exception):
    """Wird geworfen, wenn abgebrochen wurde."""


class Aufgabe:
    """Gemeinsamer Zustand zwischen Arbeitsthread und Anzeige."""

    def __init__(self) -> None:
        self.sperre = threading.RLock()
        self.titel = ""
        self.schritte: list[Schritt] = []
        self.aktiv = -1
        self.laeuft = False
        self.fertig = False
        self.fehler = False
        self.abgebrochen = False
        self.meldung = ""
        self.begonnen = 0.0
        self.beendet = 0.0
        self.datei = ""
        self.bytes_fertig = 0
        self.bytes_gesamt = 0
        self.tempo = 0.0
        self.logs: collections.deque = collections.deque(maxlen=600)
        self.log_scroll = 0
        self._proben: collections.deque = collections.deque(maxlen=30)
        self.protokoll = None

    # -- Protokolldatei -------------------------------------------
    def oeffne_protokoll(self, name: str) -> None:
        try:
            PROTOKOLL_DIR.mkdir(parents=True, exist_ok=True)
            stempel = time.strftime("%Y-%m-%d_%H-%M-%S")
            self.protokoll = open(PROTOKOLL_DIR / f"{name}_{stempel}.log", "a", encoding="utf-8")
        except OSError:
            self.protokoll = None

    def schliesse_protokoll(self) -> None:
        try:
            if self.protokoll:
                self.protokoll.close()
        except Exception:
            pass
        self.protokoll = None

    # -- Ausgaben --------------------------------------------------
    def log(self, text: str) -> None:
        text = str(text).rstrip()
        if not text:
            text = ""
        with self.sperre:
            for stueck in (text.splitlines() or [""]):
                self.logs.append(stueck[:400])
            if self.protokoll:
                try:
                    self.protokoll.write(time.strftime("[%H:%M:%S] ") + text + "\n")
                    self.protokoll.flush()
                except Exception:
                    pass

    def starte_schritt(self, index: int) -> None:
        with self.sperre:
            self.aktiv = index
            schritt = self.schritte[index]
            schritt.status = "laeuft"
            schritt.begonnen = time.time()
            schritt.fortschritt = None
            self.datei = ""
            self.bytes_fertig = 0
            self.bytes_gesamt = 0
            self.tempo = 0.0
            self._proben.clear()
        self.log("")
        self.log(f"── Schritt {index + 1}: {schritt.titel} ──")

    def beende_schritt(self, index: int, status: str = "fertig") -> None:
        with self.sperre:
            schritt = self.schritte[index]
            schritt.status = status
            schritt.beendet = time.time()
            if status in ("fertig", "uebersprungen"):
                schritt.fortschritt = 1.0
            self.datei = ""
        wort = {"fertig": "erledigt", "fehler": "fehlgeschlagen", "uebersprungen": "übersprungen"}.get(status, status)
        self.log(f"→ {schritt.titel}: {wort} ({zeit_lesbar(schritt.laufzeit)})")

    def setze_fortschritt(self, wert: Optional[float]) -> None:
        with self.sperre:
            if 0 <= self.aktiv < len(self.schritte):
                self.schritte[self.aktiv].fortschritt = wert

    def setze_bytes(self, fertig: int, gesamt: int, datei: str = "") -> None:
        jetzt = time.time()
        with self.sperre:
            self.bytes_fertig = fertig
            self.bytes_gesamt = gesamt
            if datei:
                self.datei = datei
            self._proben.append((jetzt, fertig))
            if len(self._proben) >= 2:
                t0, b0 = self._proben[0]
                dt = jetzt - t0
                if dt > 0.8:
                    self.tempo = max(0.0, (fertig - b0) / dt)

    # -- Auswertung ------------------------------------------------
    def gesamt_anteil(self) -> float:
        with self.sperre:
            gewichte = [s.gewicht() for s in self.schritte]
            summe = sum(gewichte) or 1.0
            erledigt = sum(g * s.anteil() for g, s in zip(gewichte, self.schritte))
            return max(0.0, min(1.0, erledigt / summe))

    def gesamt_restzeit(self) -> float:
        with self.sperre:
            if self.fertig or self.fehler:
                return 0.0
            return sum(s.restzeit() for s in self.schritte)

    def laufzeit(self) -> float:
        if not self.begonnen:
            return 0.0
        return (self.beendet or time.time()) - self.begonnen


# ------------------------------------------------------------
# pip-Fortschritt auswerten
# ------------------------------------------------------------

class PipFortschritt:
    """
    Wertet die Ausgabe von »pip install --progress-bar raw« aus.

    pip schreibt dabei Zeilen wie »Progress 12345 of 3461234567«
    (viermal pro Sekunde) sowie »Downloading <datei> (<größe>)«.
    Daraus entsteht echter Byte-Fortschritt inklusive Tempo und Restzeit.
    """

    RE_PROGRESS = re.compile(r"Progress (\d+) of (\d+)")
    RE_DOWNLOAD = re.compile(r"Downloading\s+(\S+)\s+\(([\d.]+)\s*([kKMGT]?B)\)")
    RE_CACHED = re.compile(r"Using cached\s+(\S+)")

    def __init__(self, aufgabe: Aufgabe, erwartet_bytes: int, einbau_sekunden: float) -> None:
        self.aufgabe = aufgabe
        self.erwartet = max(1, erwartet_bytes)
        self.einbau_sekunden = max(15.0, einbau_sekunden)
        self.basis = 0
        self.aktuell = 0
        self.aktuell_gesamt = 0
        self.phase = "download"
        self.einbau_start = 0.0
        self.begonnen = time.time()

    @staticmethod
    def _dateiname(roh: str) -> str:
        return urllib.parse.unquote(roh.rsplit("/", 1)[-1])

    def zeile(self, text: str) -> None:
        treffer = self.RE_PROGRESS.search(text)
        if treffer:
            self.aktuell = int(treffer.group(1))
            gesamt = int(treffer.group(2))
            if gesamt:
                self.aktuell_gesamt = gesamt
            self._melde()
            return

        treffer = self.RE_DOWNLOAD.search(text)
        if treffer:
            self.basis += self.aktuell
            self.aktuell = 0
            self.aktuell_gesamt = 0
            self.aufgabe.datei = self._dateiname(treffer.group(1))
            self._melde()
            return

        treffer = self.RE_CACHED.search(text)
        if treffer:
            self.aufgabe.datei = self._dateiname(treffer.group(1)) + "  (schon vorhanden)"
            return

        if "Installing collected packages" in text and self.phase == "download":
            self.phase = "einbau"
            self.basis += self.aktuell
            self.aktuell = 0
            self.einbau_start = time.time()
            self.aufgabe.datei = "Pakete werden entpackt und eingerichtet …"
            self._melde()

    def _melde(self) -> None:
        geladen = self.basis + self.aktuell
        if geladen > 0:
            self.aufgabe.setze_bytes(geladen, max(self.erwartet, geladen))
        if self.phase == "download":
            # Der Zeitanteil sorgt dafür, dass sich der Balken auch dann bewegt,
            # wenn pip keine Byte-Zahlen liefert oder alles aus dem Zwischenspeicher kommt.
            zeitanteil = (time.time() - self.begonnen) / max(30.0, self.erwartet / 8_000_000)
            anteil = max(min(geladen / self.erwartet, 1.0), min(zeitanteil, 1.0) * 0.6)
            self.aufgabe.setze_fortschritt(min(0.88, anteil * 0.88))
        else:
            vergangen = time.time() - self.einbau_start
            self.aufgabe.setze_fortschritt(min(0.99, 0.88 + 0.11 * min(1.0, vergangen / self.einbau_sekunden)))

    def tick(self) -> None:
        """Regelmäßig aufrufen, damit die Anzeige auch ohne neue Zeilen weiterläuft."""
        self._melde()

    def geladene_bytes(self) -> int:
        return self.basis + self.aktuell


# ------------------------------------------------------------
# Arbeitsthread: Installation / Reparatur / Modell
# ------------------------------------------------------------

class Arbeiter(threading.Thread):
    def __init__(self, aufgabe: Aufgabe, modus: str, grafik: Optional[Grafik]) -> None:
        super().__init__(daemon=True)
        self.aufgabe = aufgabe
        self.modus = modus                 # installieren | reparieren | modell
        self.grafik = grafik or Grafik()
        self.abbruch = threading.Event()
        self.prozess: Optional[subprocess.Popen] = None
        self.gemessenes_tempo = 0.0
        self.ergebnis: dict = {}
        # Nicht anhand einer vermeintlichen Versionsgrenze raten: Verschiedene
        # mit Python ausgelieferte pip-Builds bieten unterschiedliche Werte an.
        self.raw_fortschritt = False
        # Die getrennte Whisper-Umgebung kann eine andere (anfangs meist ältere)
        # pip-Version besitzen als die OmniVoice-Umgebung. Ihre Fähigkeit darf
        # deshalb nicht aus self.raw_fortschritt übernommen werden.
        self._pip_raw_nach_python: dict[str, bool] = {}

    # -- Steuerung -------------------------------------------------
    def stoppen(self) -> None:
        self.abbruch.set()
        beende_prozessbaum(self.prozess)

    def pruefe_abbruch(self) -> None:
        if self.abbruch.is_set():
            raise Abbruch()

    # -- Prozesse --------------------------------------------------
    def lauf_strom(
        self,
        befehl: list[str],
        auf_zeile: Optional[Callable[[str], None]] = None,
        env: Optional[dict] = None,
        takt: Optional[Callable[[], None]] = None,
    ) -> int:
        self.pruefe_abbruch()
        self.aufgabe.log("$ " + " ".join(str(t) for t in befehl))

        umgebung = dict(os.environ)
        umgebung.update({
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
            "PIP_DISABLE_PIP_VERSION_CHECK": "1",
            "PIP_NO_INPUT": "1",
        })
        if env:
            umgebung.update(env)

        try:
            self.prozess = subprocess.Popen(
                befehl,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                creationflags=KEIN_FENSTER,
                env=umgebung,
                bufsize=1,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except OSError as fehler:
            raise RuntimeError(f"Der Befehl ließ sich nicht starten: {fehler}") from fehler

        # Eigener Takt-Thread: Ein Download kann minutenlang ohne eine einzige
        # Ausgabezeile laufen - die Anzeige soll trotzdem weiterlaufen.
        schluss = threading.Event()
        if takt:
            def taktgeber() -> None:
                while not schluss.wait(0.5):
                    try:
                        takt()
                    except Exception:
                        pass

            threading.Thread(target=taktgeber, daemon=True).start()

        try:
            for roh in self.prozess.stdout:
                if self.abbruch.is_set():
                    beende_prozessbaum(self.prozess)
                    break
                text = roh.rstrip("\r\n")
                if auf_zeile:
                    auf_zeile(text)
                else:
                    self.aufgabe.log(text)
        finally:
            schluss.set()
            code = self.prozess.wait()
            self.prozess = None
        self.pruefe_abbruch()
        return code

    def pip(self, argumente: list[str], erwartet_bytes: int, einbau_sekunden: float,
            python: Optional[Path] = None) -> int:
        beobachter = PipFortschritt(self.aufgabe, erwartet_bytes, einbau_sekunden)
        stumm = re.compile(r"^\s*(Progress \d+ of \d+)?\s*$")

        def auf_zeile(text: str) -> None:
            beobachter.zeile(text)
            if not stumm.match(text):
                self.aufgabe.log(text)

        pip_befehl = [str(python), "-m", "pip"] if python else venv_pip_cmd()
        anzeige = "raw" if self.pip_raw_fuer(python) else "off"
        befehl = pip_befehl + ["install", "--progress-bar", anzeige, "--no-input"] + argumente
        code = self.lauf_strom(befehl, auf_zeile, takt=beobachter.tick)
        # Ein erfolgreiches »pip --upgrade« ändert genau die Information, die
        # gerade zwischengespeichert wurde. Beim nächsten Aufruf neu erkennen.
        if (code == 0 and python is not None
                and "--upgrade" in argumente and "pip" in argumente):
            self._pip_raw_nach_python.pop(str(Path(python).resolve()), None)

        geladen = beobachter.geladene_bytes()
        if geladen > 50_000_000:
            dauer = max(1.0, time.time() - beobachter.begonnen)
            self.gemessenes_tempo = max(self.gemessenes_tempo, geladen / dauer)
        return code

    def pip_raw_fuer(self, python: Optional[Path]) -> bool:
        """Prüft »raw« für genau die Umgebung, in der pip ausgeführt wird."""
        if python is None:
            return self.raw_fortschritt
        schluessel = str(Path(python).resolve())
        if schluessel in self._pip_raw_nach_python:
            return self._pip_raw_nach_python[schluessel]
        versionscode, ausgabe = lauf_kurz(
            [str(python), "-m", "pip", "--version"], timeout=90
        )
        treffer = re.search(r"pip\s+(\d+)\.(\d+)", ausgabe or "")
        erlaubt = self.pip_bietet_raw([str(python), "-m", "pip"])
        if versionscode == 0 and treffer:
            version = (int(treffer.group(1)), int(treffer.group(2)))
            self.aufgabe.log(
                f"pip {version[0]}.{version[1]} in der Whisper-Umgebung"
                + ("" if erlaubt else " (kompatible Fortschrittsanzeige)")
            )
        else:
            self.aufgabe.log(
                "Hinweis: pip-Version der Whisper-Umgebung nicht erkennbar; "
                "kompatible Fortschrittsanzeige wird verwendet."
            )
        self._pip_raw_nach_python[schluessel] = erlaubt
        return erlaubt

    @staticmethod
    def pip_bietet_raw(pip_befehl: list[str]) -> bool:
        """Fragt die echte Optionsliste ab, statt aus der Versionsnummer zu raten."""
        code, hilfe = lauf_kurz(
            pip_befehl + ["install", "--help"], timeout=90
        )
        if code != 0:
            return False
        return bool(re.search(
            r"--progress-bar[\s\S]{0,500}\braw\b", hilfe or "", re.IGNORECASE
        ))

    def erkenne_pip_faehigkeit(self) -> None:
        """Klärt, ob pip die maschinenlesbare Fortschrittsausgabe beherrscht."""
        code, ausgabe = lauf_kurz(venv_pip_cmd() + ["--version"], timeout=90)
        treffer = re.search(r"pip\s+(\d+)\.(\d+)", ausgabe or "")
        if code == 0 and treffer:
            version = (int(treffer.group(1)), int(treffer.group(2)))
            self.raw_fortschritt = self.pip_bietet_raw(venv_pip_cmd())
            self.aufgabe.log(f"pip {version[0]}.{version[1]} wird verwendet"
                             + ("" if self.raw_fortschritt else " (ohne genaue Byte-Anzeige)"))
        else:
            self.aufgabe.log("Hinweis: Die pip-Version ließ sich nicht bestimmen.")

    def tempo_schaetzung(self) -> float:
        """Bytes pro Sekunde – gemessen, sonst vorsichtig geschätzt."""
        return self.gemessenes_tempo if self.gemessenes_tempo > 500_000 else 12_000_000.0

    def passe_schaetzungen_an(self) -> None:
        """Restliche Schritte anhand des gemessenen Tempos neu einschätzen."""
        tempo = self.tempo_schaetzung()
        with self.aufgabe.sperre:
            for schritt in self.aufgabe.schritte:
                if schritt.status != "wartet":
                    continue
                if schritt.key == "torch":
                    schritt.schaetzung = self.torch_bytes() / tempo + self.torch_bytes() / 45_000_000
                elif schritt.key == "omnivoice":
                    schritt.schaetzung = 620_000_000 / tempo + 60
                elif schritt.key == "whisper":
                    schritt.schaetzung = 180_000_000 / tempo + 45
                elif schritt.key == "modell":
                    schritt.schaetzung = MODELL_BYTES / tempo + 20
                elif schritt.key == "whisper_modell":
                    schritt.schaetzung = WHISPER_MODELL_BYTES / tempo + 20

    # -- Ablauf ----------------------------------------------------
    def run(self) -> None:
        aufgabe = self.aufgabe
        aufgabe.begonnen = time.time()
        aufgabe.laeuft = True
        try:
            for index, schritt in enumerate(aufgabe.schritte):
                self.pruefe_abbruch()
                aufgabe.starte_schritt(index)
                getattr(self, "schritt_" + schritt.key)()
                aufgabe.beende_schritt(index)
            aufgabe.fertig = True
            aufgabe.meldung = "Fertig – OmniVoice ist einsatzbereit."
        except Abbruch:
            aufgabe.abgebrochen = True
            aufgabe.meldung = ("Abgebrochen. Beim nächsten Start wird dort weitergemacht, "
                               "wo es aufgehört hat – nichts geht verloren.")
            if 0 <= aufgabe.aktiv < len(aufgabe.schritte):
                aufgabe.beende_schritt(aufgabe.aktiv, "fehler")
        except Exception as fehler:
            aufgabe.fehler = True
            aufgabe.meldung = str(fehler)
            aufgabe.log("")
            aufgabe.log("FEHLER: " + str(fehler))
            if 0 <= aufgabe.aktiv < len(aufgabe.schritte):
                aufgabe.beende_schritt(aufgabe.aktiv, "fehler")
        finally:
            aufgabe.laeuft = False
            aufgabe.beendet = time.time()
            aufgabe.schliesse_protokoll()

    # -- Einzelschritte --------------------------------------------
    def schritt_aufraeumen(self) -> None:
        self.aufgabe.log("Die alte Installation wird entfernt …")
        if CONFIG_DATEI.exists():
            try:
                CONFIG_DATEI.unlink()
            except OSError:
                pass
        if VENV_DIR.exists():
            self.aufgabe.setze_fortschritt(0.3)
            shutil.rmtree(VENV_DIR, ignore_errors=True)
        if WHISPER_VENV_DIR.exists():
            self.aufgabe.setze_fortschritt(0.6)
            shutil.rmtree(WHISPER_VENV_DIR, ignore_errors=True)
        self.aufgabe.setze_fortschritt(1.0)
        self.aufgabe.log("Aufgeräumt. Die heruntergeladenen Sprachmodelle bleiben erhalten.")

    def schritt_python(self) -> None:
        version = sys.version_info[:3]
        self.aufgabe.log(f"Python {'.'.join(map(str, version))}")
        self.aufgabe.log(f"Ort: {sys.executable}")
        if version[:2] < PYTHON_MIN:
            raise RuntimeError(
                f"Python {version[0]}.{version[1]} ist zu alt. Benötigt wird mindestens "
                f"Python {PYTHON_MIN[0]}.{PYTHON_MIN[1]}. Bitte eine neuere Version von "
                "python.org installieren."
            )
        if version[:2] > PYTHON_MAX:
            raise RuntimeError(
                f"Python {version[0]}.{version[1]} ist zu neu – für diese Version gibt es noch "
                f"kein fertiges PyTorch. Bitte zusätzlich Python {PYTHON_MAX[0]}.{PYTHON_MAX[1]} "
                "von python.org installieren; das Studio benutzt danach automatisch die passende Version."
            )

        frei = shutil.disk_usage(str(SYSTEM_DIR)).free
        self.aufgabe.log(f"Freier Speicherplatz: {bytes_lesbar(frei)}")
        if frei < 15 * 1024 ** 3:
            raise RuntimeError(
                f"Zu wenig freier Speicherplatz ({bytes_lesbar(frei)}). "
                "Benötigt werden mindestens 15 GB auf diesem Laufwerk."
            )
        self.aufgabe.setze_fortschritt(0.6)
        if not internet_erreichbar():
            raise RuntimeError(
                "Es besteht keine Internetverbindung (pypi.org nicht erreichbar). "
                "Bitte Verbindung, Firewall oder VPN prüfen."
            )
        self.aufgabe.log("Internetverbindung: in Ordnung")
        self.aufgabe.setze_fortschritt(1.0)

    def schritt_umgebung(self) -> None:
        if venv_python().exists():
            code, ausgabe = lauf_kurz([str(venv_python()), "--version"], timeout=30)
            if code == 0:
                self.aufgabe.log(f"Vorhandene Arbeitsumgebung wird weiterverwendet ({ausgabe}).")
                self.aufgabe.setze_fortschritt(1.0)
                return
            self.aufgabe.log("Die vorhandene Arbeitsumgebung ist defekt und wird neu angelegt.")
            shutil.rmtree(VENV_DIR, ignore_errors=True)

        VENV_DIR.parent.mkdir(parents=True, exist_ok=True)
        code = self.lauf_strom([sys.executable, "-m", "venv", str(VENV_DIR)])
        if code != 0 or not venv_python().exists():
            raise RuntimeError(
                "Die Arbeitsumgebung konnte nicht angelegt werden. Vermutlich ist die "
                "Python-Installation unvollständig (Modul »venv« fehlt)."
            )
        self.aufgabe.log(f"Arbeitsumgebung angelegt: {VENV_DIR}")
        self.aufgabe.setze_fortschritt(1.0)

    def schritt_pip(self) -> None:
        # Bewusst ohne »raw«: die mitgelieferte pip-Version kann noch zu alt dafür sein.
        code = self.pip(["--upgrade", "pip", "setuptools", "wheel"], 12_000_000, 20.0)
        if code != 0:
            self.aufgabe.log("Hinweis: pip ließ sich nicht aktualisieren – es wird mit der "
                             "vorhandenen Version weitergearbeitet.")
        self.aufgabe.setze_fortschritt(0.9)
        self.erkenne_pip_faehigkeit()
        self.aufgabe.setze_fortschritt(1.0)

    def schritt_grafik(self) -> None:
        self.grafik = erkenne_grafik()
        self.aufgabe.log(f"Grafikkarte    : {self.grafik.name}")
        if self.grafik.treiber:
            self.aufgabe.log(f"Treiberversion : {self.grafik.treiber}")
        if self.grafik.vram_gb:
            self.aufgabe.log(f"Grafikspeicher : {self.grafik.vram_gb:.1f} GB")
        self.aufgabe.log(f"Betriebsart    : {self.grafik.beschriftung}")
        if self.grafik.hinweis:
            self.aufgabe.log(self.grafik.hinweis)
        if self.grafik.stufe == "CUDA" and 0 < self.grafik.vram_gb < 5.5:
            self.aufgabe.log("Hinweis: Unter 6 GB Grafikspeicher kann es bei langen Texten eng werden.")

        with self.aufgabe.sperre:
            for schritt in self.aufgabe.schritte:
                if schritt.key == "torch":
                    schritt.hinweis = {
                        "CUDA": "PyTorch mit CUDA 12.8 – ca. 3,6 GB",
                        "XPU": "PyTorch für Intel Arc – ca. 1,2 GB",
                    }.get(self.grafik.stufe, "PyTorch für den Prozessor – ca. 300 MB")
        self.passe_schaetzungen_an()
        self.aufgabe.setze_fortschritt(1.0)

    def torch_bytes(self) -> int:
        return {"CUDA": 3_600_000_000, "XPU": 1_300_000_000}.get(self.grafik.stufe, 320_000_000)

    def torch_versuche(self) -> list[list[str]]:
        """Erst exakt angepinnt, dann als Notfall mit offener Versionswahl."""
        if self.grafik.stufe == "CUDA":
            index = f"https://download.pytorch.org/whl/{CUDA_KANAL}"
            return [
                [f"torch=={TORCH_VERSION}+{CUDA_KANAL}", f"torchaudio=={TORCH_VERSION}+{CUDA_KANAL}",
                 "--index-url", index],
                ["torch", "torchaudio", "--index-url", index],
            ]
        if self.grafik.stufe == "XPU":
            return [["torch", "torchaudio", "--index-url", "https://download.pytorch.org/whl/xpu"]]
        index = "https://download.pytorch.org/whl/cpu"
        return [
            [f"torch=={TORCH_VERSION}", f"torchaudio=={TORCH_VERSION}", "--index-url", index],
            ["torch", "torchaudio", "--index-url", index],
        ]

    def schritt_torch(self) -> None:
        erwartet = self.torch_bytes()
        einbau = max(25.0, erwartet / 45_000_000)
        versuche = self.torch_versuche()
        letzter_code = 1

        for nummer, argumente in enumerate(versuche, start=1):
            self.pruefe_abbruch()
            if nummer > 1:
                self.aufgabe.log("")
                self.aufgabe.log(f"Zweiter Versuch mit offener Versionswahl …")
            letzter_code = self.pip(argumente, erwartet, einbau)
            if letzter_code == 0:
                self.aufgabe.setze_fortschritt(1.0)
                self.aufgabe.log("PyTorch wurde installiert.")
                self.passe_schaetzungen_an()
                return

        if self.grafik.stufe != "CPU":
            self.aufgabe.log("")
            self.aufgabe.log("Die GPU-Variante ließ sich nicht installieren – es wird auf die "
                             "Prozessor-Variante ausgewichen.")
            self.grafik = Grafik("CPU", self.grafik.name, self.grafik.treiber, self.grafik.vram_gb,
                                 "Die GPU-Variante ließ sich nicht installieren.")
            if self.pip(["torch", "torchaudio", "--index-url",
                         "https://download.pytorch.org/whl/cpu"], 320_000_000, 40.0) == 0:
                self.aufgabe.setze_fortschritt(1.0)
                self.passe_schaetzungen_an()
                return

        raise RuntimeError(
            f"PyTorch konnte nicht installiert werden (Fehlercode {letzter_code}). "
            "Meistens hilft: Internetverbindung prüfen und im Hauptmenü erneut starten."
        )

    def schritt_omnivoice(self) -> None:
        code = self.pip([PAKET_NAME], 620_000_000, 60.0)
        if code != 0:
            self.aufgabe.log("Der erste Versuch ist fehlgeschlagen – zweiter Versuch …")
            code = self.pip([PAKET_NAME], 620_000_000, 60.0)
        if code != 0:
            raise RuntimeError(
                f"Das Paket »{PAKET_NAME}« konnte nicht installiert werden (Fehlercode {code}). "
                "Bitte Internetverbindung prüfen und erneut versuchen."
            )
        self.aufgabe.log("")
        self.aufgabe.log("Zubehör wird eingerichtet: Download-Beschleunigung und "
                         "Auslastungsanzeige …")
        # hf_xet  = schnellere Hugging-Face-Downloads
        # psutil  = Werte für die Auslastungsanzeige in der Oberfläche.
        #           Kommt zwar meist über 'accelerate' mit, wird hier aber
        #           ausdrücklich angefordert, damit die Anzeige nicht von einer
        #           fremden Abhängigkeit abhängt.
        if self.pip(["hf_xet", "psutil"], 12_000_000, 15.0) != 0:
            self.aufgabe.log("Hinweis: Das Zubehör ließ sich nicht installieren. "
                             "OmniVoice läuft trotzdem – nur Downloads sind langsamer "
                             "und die Auslastungsanzeige bleibt leer.")
        self.passe_schaetzungen_an()
        self.aufgabe.setze_fortschritt(1.0)

    def schritt_whisper_umgebung(self) -> None:
        """Getrennte Umgebung: Faster-Whisper kann OmniVoice-Abhängigkeiten nicht verändern."""
        if whisper_python().exists():
            code, ausgabe = lauf_kurz([str(whisper_python()), "--version"], timeout=30)
            if code == 0:
                self.aufgabe.log(f"Whisper-Umgebung wird weiterverwendet ({ausgabe}).")
            else:
                self.aufgabe.log("Whisper-Umgebung ist defekt und wird neu angelegt.")
                shutil.rmtree(WHISPER_VENV_DIR, ignore_errors=True)
        if not whisper_python().exists():
            WHISPER_VENV_DIR.parent.mkdir(parents=True, exist_ok=True)
            code = self.lauf_strom(
                [sys.executable, "-m", "venv", str(WHISPER_VENV_DIR)]
            )
            if code != 0 or not whisper_python().exists():
                raise RuntimeError("Die getrennte Faster-Whisper-Umgebung ließ sich nicht anlegen.")
            self.aufgabe.log(f"Getrennte Whisper-Umgebung angelegt: {WHISPER_VENV_DIR}")

        # Die neue Umgebung hat anfangs oft ein altes pip. Hier ist die genaue
        # Byte-Anzeige noch nicht wichtig; danach kann Faster-Whisper sauber folgen.
        code = self.pip(
            ["--upgrade", "pip", "setuptools", "wheel"],
            12_000_000, 20.0, python=whisper_python(),
        )
        if code != 0:
            raise RuntimeError("pip ließ sich in der Whisper-Umgebung nicht aktualisieren.")
        self.aufgabe.setze_fortschritt(1.0)

    def schritt_whisper(self) -> None:
        self.aufgabe.log("Faster-Whisper wird ausschließlich in seiner eigenen Umgebung installiert.")
        self.aufgabe.log("Die OmniVoice-/PyTorch-Umgebung bleibt unverändert.")
        code = self.pip(
            [WHISPER_PAKET],
            180_000_000, 45.0, python=whisper_python(),
        )
        if code != 0:
            raise RuntimeError(
                f"Faster-Whisper konnte nicht installiert werden (Fehlercode {code})."
            )
        pruefcode, ausgabe = lauf_kurz(whisper_pip_cmd() + ["check"], timeout=120)
        if pruefcode != 0:
            raise RuntimeError(
                "Die Faster-Whisper-Umgebung enthält unvereinbare Pakete: " + ausgabe
            )
        version_code, version = lauf_kurz(
            [str(whisper_python()), "-c",
             "from importlib.metadata import version; print(version('faster-whisper'))"],
            timeout=30,
        )
        if version_code != 0:
            raise RuntimeError("Faster-Whisper ist nach der Installation nicht importierbar.")
        self.ergebnis["faster_whisper"] = version.strip()
        self.aufgabe.log(f"Faster-Whisper {version.strip()} ist bereit.")
        self.aufgabe.setze_fortschritt(1.0)

    def schritt_modell(self) -> None:
        helfer = HELFER_DIR / "lade_modell.py"
        if not helfer.exists():
            raise RuntimeError(f"Die Hilfsdatei fehlt: {helfer}")

        self.aufgabe.log(f"Sprachmodell: {MODELL_REPO} (ca. {bytes_lesbar(MODELL_BYTES)})")
        self.aufgabe.log(f"Ablage: {modell_ordner()}")
        self.aufgabe.log("Der Download kann jederzeit fortgesetzt werden – ein Abbruch ist ungefährlich.")

        def auf_zeile(text: str) -> None:
            if text.startswith("#FORTSCHRITT#"):
                try:
                    daten = json.loads(text[len("#FORTSCHRITT#"):])
                except ValueError:
                    return
                fertig = int(daten.get("fertig", 0))
                gesamt = int(daten.get("gesamt", 0)) or MODELL_BYTES
                self.aufgabe.setze_bytes(fertig, gesamt, daten.get("datei", ""))
                self.aufgabe.setze_fortschritt(min(0.99, fertig / max(1, gesamt)))
            else:
                self.aufgabe.log(text)

        spiegel = [None, "https://hf-mirror.com"]
        letzter_code = 1
        for nummer, endpunkt in enumerate(spiegel, start=1):
            self.pruefe_abbruch()
            env = {"HF_HUB_DISABLE_PROGRESS_BARS": "1", "HF_HUB_DISABLE_TELEMETRY": "1"}
            if endpunkt:
                env["HF_ENDPOINT"] = endpunkt
                self.aufgabe.log("")
                self.aufgabe.log(f"Neuer Versuch über den Spiegelserver {endpunkt} …")

            letzter_code = self.lauf_strom(
                [str(venv_python()), "-u", str(helfer), MODELL_REPO], auf_zeile, env=env)
            if letzter_code == 0:
                self.aufgabe.setze_fortschritt(1.0)
                if self.aufgabe.tempo > 500_000:
                    self.gemessenes_tempo = max(self.gemessenes_tempo, self.aufgabe.tempo)
                self.aufgabe.log("Das Sprachmodell ist vollständig geladen.")
                return
            if nummer < len(spiegel):
                self.aufgabe.log("Download fehlgeschlagen – der nächste Server wird versucht …")

        raise RuntimeError(
            f"Das Sprachmodell konnte nicht geladen werden (Fehlercode {letzter_code}). "
            "Bereits geladene Teile bleiben erhalten – einfach später erneut starten."
        )

    def schritt_whisper_modell(self) -> None:
        helfer = HELFER_DIR / "lade_modell.py"
        if not helfer.exists():
            raise RuntimeError(f"Die Hilfsdatei fehlt: {helfer}")

        self.aufgabe.log(
            f"Whisper-Modell: {WHISPER_REPO} (ca. {bytes_lesbar(WHISPER_MODELL_BYTES)})"
        )
        self.aufgabe.log(f"Ablage: {hub_modell_ordner(WHISPER_REPO)}")
        self.aufgabe.log(
            "Standard ist »medium«. Ein anderes Modell kann später in der WebUI gewählt werden."
        )

        def auf_zeile(text: str) -> None:
            if text.startswith("#FORTSCHRITT#"):
                try:
                    daten = json.loads(text[len("#FORTSCHRITT#"):])
                except ValueError:
                    return
                fertig = int(daten.get("fertig", 0))
                gesamt = int(daten.get("gesamt", 0)) or WHISPER_MODELL_BYTES
                self.aufgabe.setze_bytes(fertig, gesamt, daten.get("datei", ""))
                self.aufgabe.setze_fortschritt(min(0.99, fertig / max(1, gesamt)))
            else:
                self.aufgabe.log(text)

        spiegel = [None, "https://hf-mirror.com"]
        letzter_code = 1
        for nummer, endpunkt in enumerate(spiegel, start=1):
            self.pruefe_abbruch()
            env = {"HF_HUB_DISABLE_PROGRESS_BARS": "1", "HF_HUB_DISABLE_TELEMETRY": "1"}
            if endpunkt:
                env["HF_ENDPOINT"] = endpunkt
                self.aufgabe.log(f"Neuer Versuch über den Spiegelserver {endpunkt} …")
            letzter_code = self.lauf_strom(
                [str(whisper_python()), "-u", str(helfer), WHISPER_REPO,
                 str(WHISPER_MODELL_BYTES)],
                auf_zeile, env=env,
            )
            if letzter_code == 0:
                self.aufgabe.setze_fortschritt(1.0)
                self.aufgabe.log("Das Faster-Whisper-Modell »medium« ist vollständig geladen.")
                return
            if nummer < len(spiegel):
                self.aufgabe.log("Download fehlgeschlagen – Spiegelserver wird versucht …")
        raise RuntimeError(
            f"Das Faster-Whisper-Modell konnte nicht geladen werden (Fehlercode {letzter_code})."
        )

    def schritt_test(self) -> None:
        helfer = HELFER_DIR / "pruefe_umgebung.py"
        if not helfer.exists():
            raise RuntimeError(f"Die Hilfsdatei fehlt: {helfer}")

        def auf_zeile(text: str) -> None:
            if text.startswith("#ERGEBNIS#"):
                try:
                    self.ergebnis.update(json.loads(text[len("#ERGEBNIS#"):]))
                except ValueError:
                    pass
            else:
                self.aufgabe.log(text)

        code = self.lauf_strom([str(venv_python()), "-u", str(helfer)], auf_zeile)
        if code != 0 or not self.ergebnis.get("ok"):
            raise RuntimeError(
                "Die Installation ist unvollständig: "
                + str(self.ergebnis.get("fehler") or "unbekannte Ursache")
                + ". Bitte im Hauptmenü »Reparieren« wählen."
            )

        whisper_code, whisper_ausgabe = lauf_kurz(
            [
                str(whisper_python()), "-c",
                "from importlib.metadata import version; "
                "import faster_whisper, ctranslate2; "
                "print(version('faster-whisper')); print(ctranslate2.__version__)",
            ],
            timeout=60,
        )
        if whisper_code != 0:
            raise RuntimeError(
                "Die getrennte Faster-Whisper-Umgebung ist unvollständig: "
                + whisper_ausgabe
            )
        whisper_zeilen = whisper_ausgabe.splitlines()
        self.ergebnis["faster_whisper"] = whisper_zeilen[0] if whisper_zeilen else ""
        self.ergebnis["ctranslate2"] = whisper_zeilen[1] if len(whisper_zeilen) > 1 else ""

        self.aufgabe.log("")
        self.aufgabe.log(f"PyTorch      : {self.ergebnis.get('torch')}")
        self.aufgabe.log(f"OmniVoice    : {self.ergebnis.get('omnivoice')}")
        self.aufgabe.log(f"Transformers : {self.ergebnis.get('transformers')}")
        self.aufgabe.log(f"Faster-Whisper: {self.ergebnis.get('faster_whisper')} "
                         f"(CTranslate2 {self.ergebnis.get('ctranslate2')})")
        if self.ergebnis.get("cuda"):
            self.aufgabe.log(f"CUDA aktiv   : ja ({self.ergebnis.get('geraet')}, "
                             f"{self.ergebnis.get('vram_gb')} GB)")
        elif self.ergebnis.get("xpu"):
            self.aufgabe.log(f"Intel XPU    : ja ({self.ergebnis.get('geraet')})")
        else:
            self.aufgabe.log("Betriebsart  : Prozessor (CPU)")
            if self.grafik.stufe == "CUDA":
                self.aufgabe.log("Achtung: CUDA wurde installiert, ist aber nicht nutzbar. "
                                 "Bitte den Grafiktreiber aktualisieren.")
        self.aufgabe.setze_fortschritt(1.0)

    def schritt_abschluss(self) -> None:
        daten = {
            "version": APP_VERSION,
            "installiert_am": time.strftime("%d.%m.%Y %H:%M"),
            "stufe": "CUDA" if self.ergebnis.get("cuda") else ("XPU" if self.ergebnis.get("xpu") else "CPU"),
            "gpu": self.grafik.name,
            "treiber": self.grafik.treiber,
            "vram_gb": round(self.grafik.vram_gb, 1),
            "python": ".".join(map(str, sys.version_info[:3])),
            "torch": self.ergebnis.get("torch", ""),
            "omnivoice": self.ergebnis.get("omnivoice", ""),
            "faster_whisper": self.ergebnis.get("faster_whisper", ""),
            "whisper_modell": WHISPER_STANDARD_MODELL,
            "cuda": bool(self.ergebnis.get("cuda")),
            "modell": MODELL_REPO,
        }
        DATEN_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_DATEI.write_text(json.dumps(daten, indent=2, ensure_ascii=False), encoding="utf-8")
        self.aufgabe.log(f"Einstellungen gespeichert: {CONFIG_DATEI.name}")
        self.aufgabe.log("Ab jetzt startet STARTEN.bat OmniVoice direkt durch.")
        self.aufgabe.setze_fortschritt(1.0)

class UpdateArbeiter(threading.Thread):
    """Lädt ein geprüftes GitHub-Paket und bereitet die Anwendung nach Programmende vor."""

    MAX_ARCHIV_BYTES = 100 * 1024 * 1024

    def __init__(self, aufgabe: Aufgabe, ziel_version: str, ziel_commit: str) -> None:
        super().__init__(daemon=True)
        self.aufgabe = aufgabe
        self.ziel_version = norm_version(ziel_version)
        self.ziel_commit = str(ziel_commit).strip().lower()
        if not re.fullmatch(r"[0-9a-f]{40}", self.ziel_commit):
            raise ValueError("Für das Update fehlt ein gültiger GitHub-Commit.")
        self.archiv_url = (
            f"https://github.com/{UPDATE_REPO}/archive/{self.ziel_commit}.zip"
        )

    def _download(self, ziel: Path) -> None:
        anfrage = urllib.request.Request(
            self.archiv_url,
            headers={
                "User-Agent": f"OmniVoice-Toolkit/{APP_VERSION}",
                "Accept": "application/zip, application/octet-stream",
                "Cache-Control": "no-cache",
            },
        )
        with urllib.request.urlopen(anfrage, timeout=30) as antwort, open(ziel, "wb") as datei:
            try:
                gesamt = int(antwort.headers.get("Content-Length", "0"))
            except ValueError:
                gesamt = 0
            fertig = 0
            while True:
                block = antwort.read(128 * 1024)
                if not block:
                    break
                fertig += len(block)
                if fertig > self.MAX_ARCHIV_BYTES:
                    raise ValueError("Das GitHub-Archiv ist unerwartet groß.")
                datei.write(block)
                self.aufgabe.setze_bytes(fertig, gesamt or max(fertig, 1), "GitHub-Update")
        if fertig < 100:
            raise ValueError("Das heruntergeladene Update ist leer oder unvollständig.")

    def _paket_vorbereiten(self, archiv: Path) -> tuple[Path, Path, list[str]]:
        if UPDATE_BEREIT_DIR.exists():
            shutil.rmtree(UPDATE_BEREIT_DIR)
        payload = UPDATE_BEREIT_DIR / "payload"
        sicherung = UPDATE_BEREIT_DIR / "sicherung"
        payload.mkdir(parents=True)
        sicherung.mkdir(parents=True)

        dateien: list[PurePosixPath] = []
        entpackte_bytes = 0
        with zipfile.ZipFile(archiv) as paket:
            for info in paket.infolist():
                if info.is_dir():
                    continue
                pfad = PurePosixPath(info.filename)
                if pfad.is_absolute() or len(pfad.parts) < 2:
                    continue
                relativ = PurePosixPath(*pfad.parts[1:])
                if not update_pfad_erlaubt(relativ):
                    continue
                entpackte_bytes += max(0, info.file_size)
                if entpackte_bytes > self.MAX_ARCHIV_BYTES:
                    raise ValueError("Der entpackte Update-Inhalt ist unerwartet groß.")
                ziel = payload.joinpath(*relativ.parts)
                ziel.parent.mkdir(parents=True, exist_ok=True)
                with paket.open(info) as quelle, open(ziel, "wb") as ausgabe:
                    shutil.copyfileobj(quelle, ausgabe, length=128 * 1024)
                dateien.append(relativ)

        erforderlich = {
            "VERSION", "STARTEN.bat", "system/start.bat",
            "system/omnivoice_toolkit.py",
        }
        gefunden = {pfad.as_posix() for pfad in dateien}
        fehlt = sorted(erforderlich - gefunden)
        if fehlt:
            raise ValueError("Das Update-Paket ist unvollständig: " + ", ".join(fehlt))

        paket_version = norm_version((payload / "VERSION").read_text(encoding="utf-8-sig"))
        if paket_version != self.ziel_version:
            raise ValueError(
                f"Versionsprüfung fehlgeschlagen: erwartet {self.ziel_version}, "
                f"erhalten {paket_version}."
            )

        neu: list[str] = []
        for relativ in dateien:
            quelle = TOOLKIT_DIR.joinpath(*relativ.parts)
            backup = sicherung.joinpath(*relativ.parts)
            if quelle.is_file():
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(quelle, backup)
            else:
                neu.append(relativ.as_posix())
        (UPDATE_BEREIT_DIR / "neue-dateien.txt").write_text(
            "\n".join(neu), encoding="utf-8"
        )
        return payload, sicherung, neu

    def _schreibe_anwender(self, payload: Path, sicherung: Path) -> None:
        PROTOKOLL_DIR.mkdir(parents=True, exist_ok=True)
        skript = UPDATE_BEREIT_DIR / "anwenden.ps1"
        zeilen = [
            "$ErrorActionPreference = 'Stop'",
            "$Host.UI.RawUI.WindowTitle = 'OmniVoice Toolkit - Update'",
            f"$payload = {powershell_literal(payload)}",
            f"$ziel = {powershell_literal(TOOLKIT_DIR)}",
            f"$sicherung = {powershell_literal(sicherung)}",
            f"$neueDateien = {powershell_literal(UPDATE_BEREIT_DIR / 'neue-dateien.txt')}",
            f"$statusDatei = {powershell_literal(UPDATE_STATUS_DATEI)}",
            f"$protokoll = {powershell_literal(UPDATE_PROTOKOLL_DATEI)}",
            f"$version = {powershell_literal(self.ziel_version)}",
            "",
            "function Kopiere-Baum([string]$quelle, [string]$zielordner) {",
            "    Get-ChildItem -LiteralPath $quelle -Recurse -File | ForEach-Object {",
            "        $relativ = $_.FullName.Substring($quelle.Length).TrimStart('\\', '/')",
            "        $ausgabe = Join-Path $zielordner $relativ",
            "        $eltern = Split-Path -Parent $ausgabe",
            "        if ($eltern) { New-Item -ItemType Directory -Force -Path $eltern | Out-Null }",
            "        Copy-Item -LiteralPath $_.FullName -Destination $ausgabe -Force",
            "    }",
            "}",
            "",
            "Write-Host ''",
            "Write-Host '  OmniVoice Toolkit wird aktualisiert ...' -ForegroundColor Cyan",
            "Write-Host '  Ergebnisse, Daten und Python-Umgebung bleiben erhalten.'",
            "Start-Sleep -Seconds 2",
            "try {",
            "    Add-Content -LiteralPath $protokoll -Value "
            "('[' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + '] Update auf ' + $version)",
            "    Kopiere-Baum $payload $ziel",
            "    @{ status = 'erfolgreich'; version = $version } | ConvertTo-Json | "
            "Set-Content -LiteralPath $statusDatei -Encoding UTF8",
            "    Add-Content -LiteralPath $protokoll -Value 'Update erfolgreich angewendet.'",
            "    Write-Host ('  Fertig: ' + $version) -ForegroundColor Green",
            "    Start-Sleep -Seconds 1",
            "    Start-Process -FilePath (Join-Path $ziel 'STARTEN.bat') -WorkingDirectory $ziel",
            "} catch {",
            "    Add-Content -LiteralPath $protokoll -Value ('FEHLER: ' + $_.Exception.Message)",
            "    try {",
            "        Kopiere-Baum $sicherung $ziel",
            "        if (Test-Path -LiteralPath $neueDateien) {",
            "            Get-Content -LiteralPath $neueDateien | Where-Object { $_ } | ForEach-Object {",
            "                $neu = Join-Path $ziel $_",
            "                if (Test-Path -LiteralPath $neu -PathType Leaf) {",
            "                    Remove-Item -LiteralPath $neu -Force",
            "                }",
            "            }",
            "        }",
            "        Add-Content -LiteralPath $protokoll -Value 'Vorherige Dateien wiederhergestellt.'",
            "    } catch {",
            "        Add-Content -LiteralPath $protokoll -Value "
            "('ROLLBACK-FEHLER: ' + $_.Exception.Message)",
            "    }",
            "    @{ status = 'fehler'; version = $version } | ConvertTo-Json | "
            "Set-Content -LiteralPath $statusDatei -Encoding UTF8",
            "    Write-Host ''",
            "    Write-Host ('  Update fehlgeschlagen: ' + $_.Exception.Message) -ForegroundColor Red",
            "    Write-Host ('  Protokoll: ' + $protokoll)",
            "    Read-Host '  ENTER zum Schliessen'",
            "    exit 1",
            "}",
        ]
        skript.write_text("\n".join(zeilen) + "\n", encoding="utf-8-sig")
        UPDATE_STATUS_DATEI.write_text(
            json.dumps({"status": "bereit", "version": self.ziel_version}, ensure_ascii=False),
            encoding="utf-8",
        )

    def run(self) -> None:
        aufgabe = self.aufgabe
        aufgabe.laeuft = True
        aufgabe.begonnen = time.time()
        aufgabe.oeffne_protokoll("update")
        try:
            with tempfile.TemporaryDirectory(prefix="omnivoice-update-") as temp:
                archiv = Path(temp) / "update.zip"

                aufgabe.starte_schritt(0)
                stand = pruefe_update_online()
                if (
                    stand.zustand != "verfuegbar"
                    or stand.online != self.ziel_version
                    or stand.commit != self.ziel_commit
                ):
                    raise RuntimeError(
                        stand.meldung if stand.zustand == "fehler"
                        else "Die angebotene Version hat sich geändert. Bitte erneut prüfen."
                    )
                aufgabe.log(f"Installiert : {APP_VERSION}")
                aufgabe.log(f"Auf GitHub : {stand.online}")
                aufgabe.beende_schritt(0)

                aufgabe.starte_schritt(1)
                aufgabe.log(f"Quelle: GitHub-Commit {self.ziel_commit[:12]}")
                aufgabe.log(f"Archiv: {self.archiv_url}")
                self._download(archiv)
                aufgabe.beende_schritt(1)

                aufgabe.starte_schritt(2)
                payload, sicherung, neue = self._paket_vorbereiten(archiv)
                dateizahl = sum(1 for pfad in payload.rglob("*") if pfad.is_file())
                aufgabe.log(f"Paket geprüft · {dateizahl} Programmdateien")
                aufgabe.log(f"Neue Programmdateien: {len(neue)}")
                aufgabe.beende_schritt(2)

                aufgabe.starte_schritt(3)
                self._schreibe_anwender(payload, sicherung)
                aufgabe.log("Update ist bereit und wird nach dem Beenden sicher angewendet.")
                aufgabe.beende_schritt(3)

            aufgabe.fertig = True
            aufgabe.meldung = (
                f"{self.ziel_version} ist vorbereitet. ENTER installiert das Update "
                "und startet das Studio neu."
            )
        except Exception as fehler:
            if 0 <= aufgabe.aktiv < len(aufgabe.schritte):
                aufgabe.beende_schritt(aufgabe.aktiv, "fehler")
            aufgabe.fehler = True
            aufgabe.meldung = str(fehler)
            aufgabe.log(f"FEHLER: {fehler}")
        finally:
            aufgabe.laeuft = False
            aufgabe.beendet = time.time()
            aufgabe.schliesse_protokoll()


def baue_schritte(modus: str, grafik: Grafik) -> list[Schritt]:
    tempo = 12_000_000.0
    torch_bytes = {"CUDA": 3_600_000_000, "XPU": 1_300_000_000}.get(grafik.stufe, 320_000_000)

    voll = [
        Schritt("python", "System prüfen",
                "Python, Speicherplatz und Internet", 14),
        Schritt("umgebung", "Arbeitsumgebung anlegen",
                "abgeschotteter Python-Bereich", 35),
        Schritt("pip", "Paketverwaltung aktualisieren",
                "pip, setuptools und wheel", 30),
        Schritt("grafik", "Grafikkarte erkennen",
                "passende Beschleunigung wählen", 12),
        Schritt("torch", "KI-Motor PyTorch installieren",
                "der größte Brocken", torch_bytes / tempo + 60),
        Schritt("omnivoice", "OmniVoice installieren",
                "Programm samt Zubehör – ca. 600 MB", 620_000_000 / tempo + 60),
        Schritt("whisper_umgebung", "Whisper-Umgebung anlegen",
                "getrennt von OmniVoice – schützt dessen Pakete", 35),
        Schritt("whisper", "Faster-Whisper installieren",
                "Transkription und Qualitätsprüfung", 180_000_000 / tempo + 45),
        Schritt("modell", "Sprachmodell herunterladen",
                f"{MODELL_REPO} – ca. 3,3 GB", MODELL_BYTES / tempo + 20),
        Schritt("whisper_modell", "Whisper-Modell herunterladen",
                f"{WHISPER_STANDARD_MODELL} – ca. 1,5 GB", WHISPER_MODELL_BYTES / tempo + 20),
        Schritt("test", "Installation testen",
                "OmniVoice und Faster-Whisper prüfen", 60),
        Schritt("abschluss", "Abschließen",
                "Einstellungen sichern", 5),
    ]
    if modus == "reparieren":
        return [Schritt("aufraeumen", "Alte Installation entfernen",
                        "Arbeitsumgebung wird zurückgesetzt", 20)] + voll
    if modus == "modell":
        schluessel = {"modell", "whisper_modell", "test", "abschluss"}
        return [schritt for schritt in voll if schritt.key in schluessel]
    if modus == "whisper":
        schluessel = {"whisper_umgebung", "whisper", "whisper_modell", "test", "abschluss"}
        return [schritt for schritt in voll if schritt.key in schluessel]
    return voll


# ------------------------------------------------------------
# OmniVoice starten
# ------------------------------------------------------------

class ServerStarter(threading.Thread):
    def __init__(self, aufgabe: Aufgabe) -> None:
        super().__init__(daemon=True)
        self.aufgabe = aufgabe
        self.abbruch = threading.Event()
        self.prozess: Optional[subprocess.Popen] = None
        self.port: Optional[int] = None
        self.url = ""
        self.bereit = False
        self.browser_geoeffnet = False
        self.gestartet = time.time()
        self._bereit_sperre = threading.Lock()

    def stoppen(self) -> None:
        self.abbruch.set()
        beende_prozessbaum(self.prozess)

    def markiere_bereit(self) -> None:
        """Setzt den sichtbaren Zustand genau einmal und öffnet danach den Browser."""
        with self._bereit_sperre:
            if self.bereit:
                return
            self.bereit = True
            self.aufgabe.titel = "OMNIVOICE GESTARTET"
            self.aufgabe.meldung = (
                f"OmniVoice ist gestartet und unter {self.url} erreichbar."
            )
            self.aufgabe.log("OmniVoice ist vollständig gestartet – die WebUI ist bereit.")
        self.oeffne_browser()

    def warte_auf_webui(self) -> None:
        """Zusätzliche Bereitschaftsprüfung, falls Gradio seine URL nicht ausgibt."""
        ende = time.time() + 10 * 60
        while not self.abbruch.is_set() and time.time() < ende:
            prozess = self.prozess
            if prozess is None or prozess.poll() is not None:
                return
            try:
                with urllib.request.urlopen(self.url, timeout=0.8) as antwort:
                    if int(getattr(antwort, "status", 200)) < 500:
                        self.markiere_bereit()
                        return
            except (OSError, urllib.error.URLError):
                time.sleep(0.35)

    def starte_prozess(self, helfer: Path) -> int:
        """Startet eine Oberfläche und liest ihre Ausgabe mit."""
        aufgabe = self.aufgabe
        umgebung = dict(os.environ)
        umgebung.update({
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
            "GRADIO_ANALYTICS_ENABLED": "False",
            "HF_HUB_DISABLE_TELEMETRY": "1",
        })
        befehl = [str(venv_python()), "-u", str(helfer),
                  "--ip", "127.0.0.1", "--port", str(self.port)]
        if helfer.name == "oberflaeche.py":
            befehl += ["--ausgabe", str(ERGEBNIS_DIR),
                       "--einstellungen", str(DATEN_DIR / "oberflaeche.json")]

        self.prozess = subprocess.Popen(
            befehl,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            creationflags=KEIN_FENSTER,
            env=umgebung,
            bufsize=1,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        threading.Thread(target=self.warte_auf_webui, daemon=True).start()
        for roh in self.prozess.stdout:
            if self.abbruch.is_set():
                break
            text = roh.rstrip("\r\n")
            aufgabe.log(text)
            if not self.bereit and re.search(r"https?://(127\.0\.0\.1|localhost|0\.0\.0\.0):\d+", text):
                self.markiere_bereit()
        code = self.prozess.wait()
        self.prozess = None
        return code

    def run(self) -> None:
        aufgabe = self.aufgabe
        aufgabe.laeuft = True
        aufgabe.begonnen = time.time()
        try:
            if not venv_python().exists():
                raise RuntimeError("OmniVoice ist noch nicht installiert. "
                                   "Bitte zuerst im Hauptmenü »Installieren« wählen.")
            eigene = HELFER_DIR / "oberflaeche.py"
            standard = HELFER_DIR / "starte_demo.py"
            if not eigene.exists() and not standard.exists():
                raise RuntimeError(f"Die Hilfsdateien fehlen im Ordner {HELFER_DIR}")

            self.port = freier_port()
            if self.port is None:
                raise RuntimeError("Es ist kein freier Anschluss zwischen 7860 und 7899 verfügbar. "
                                   "Bitte andere Programme schließen.")
            self.url = f"http://127.0.0.1:{self.port}"
            ERGEBNIS_DIR.mkdir(parents=True, exist_ok=True)

            aufgabe.log(f"OmniVoice wird gestartet: {self.url}")
            aufgabe.log("Beim ersten Start wird das Sprachmodell in den Speicher geladen "
                        "– das dauert 1 bis 3 Minuten.")
            aufgabe.log(f"Fertige Aufnahmen landen in: {ERGEBNIS_DIR}")
            aufgabe.log("")

            code = self.starte_prozess(eigene) if eigene.exists() else 4
            if code == EXIT_OBERFLAECHE_FEHLT and not self.abbruch.is_set() and standard.exists():
                aufgabe.log("")
                aufgabe.log("Die deutsche Oberfläche ließ sich nicht starten – es wird auf die "
                            "mitgelieferte Standard-Oberfläche ausgewichen.")
                self.bereit = False
                self.browser_geoeffnet = False
                code = self.starte_prozess(standard)

            if self.abbruch.is_set():
                aufgabe.abgebrochen = True
                aufgabe.meldung = "OmniVoice wurde beendet."
            elif code != 0:
                aufgabe.fehler = True
                aufgabe.meldung = (f"OmniVoice wurde mit Fehlercode {code} beendet. "
                                   "Die letzten Zeilen im Protokoll nennen meist die Ursache.")
            else:
                aufgabe.fertig = True
                aufgabe.meldung = "OmniVoice wurde beendet."
        except Exception as fehler:
            aufgabe.fehler = True
            aufgabe.meldung = str(fehler)
            aufgabe.log("FEHLER: " + str(fehler))
        finally:
            aufgabe.laeuft = False
            aufgabe.beendet = time.time()
            self.prozess = None
            aufgabe.schliesse_protokoll()

    def oeffne_browser(self) -> None:
        if self.browser_geoeffnet or not self.url:
            return
        self.browser_geoeffnet = True
        self.aufgabe.log("")
        self.aufgabe.log(f"Der Browser wird geöffnet: {self.url}")
        try:
            webbrowser.open(self.url)
        except Exception as fehler:
            self.aufgabe.log(f"Der Browser ließ sich nicht öffnen ({fehler}). "
                             f"Bitte {self.url} von Hand aufrufen.")


# ------------------------------------------------------------
# Systemprüfung
# ------------------------------------------------------------

def sammle_systemdaten() -> list[tuple[str, str, str]]:
    """Liefert (Bezeichnung, Wert, Bewertung); Bewertung: ok | warn | schlecht."""
    zeilen: list[tuple[str, str, str]] = []
    zeilen.append(("Betriebssystem", f"{platform.system()} {platform.release()}", "ok"))

    version = sys.version_info
    if PYTHON_MIN <= version[:2] <= PYTHON_MAX:
        bewertung = "ok"
    elif version[:2] < PYTHON_MIN:
        bewertung = "schlecht"
    else:
        bewertung = "warn"
    zeilen.append(("Python", f"{version.major}.{version.minor}.{version.micro}", bewertung))

    ram = arbeitsspeicher_gb()
    if ram:
        zeilen.append(("Arbeitsspeicher", f"{ram:.0f} GB", "ok" if ram >= 15 else "warn"))
    zeilen.append(("Prozessorkerne", str(os.cpu_count() or "?"), "ok"))

    grafik = erkenne_grafik()
    zeilen.append(("Grafikkarte", grafik.name, "ok" if grafik.stufe != "CPU" else "warn"))
    if grafik.treiber:
        gut = grafik.stufe == "CUDA"
        zeilen.append(("Grafiktreiber",
                       grafik.treiber + ("" if gut else f"  (nötig: {MIN_TREIBER} oder neuer)"),
                       "ok" if gut else "warn"))
    if grafik.vram_gb:
        zeilen.append(("Grafikspeicher", f"{grafik.vram_gb:.1f} GB",
                       "ok" if grafik.vram_gb >= 6 else "warn"))
    zeilen.append(("Betriebsart", grafik.beschriftung, "ok" if grafik.stufe != "CPU" else "warn"))

    try:
        frei = shutil.disk_usage(str(SYSTEM_DIR)).free
        zeilen.append(("Freier Speicherplatz", bytes_lesbar(frei),
                       "ok" if frei > 15 * 1024 ** 3 else "schlecht"))
    except OSError:
        pass

    online = internet_erreichbar()
    zeilen.append(("Internetverbindung", "erreichbar" if online else "nicht erreichbar",
                   "ok" if online else "schlecht"))

    config = lade_config()
    if config:
        zeilen.append(("Installation", f"vorhanden (vom {config.get('installiert_am', '?')})", "ok"))
        if config.get("torch"):
            zeilen.append(("PyTorch", str(config.get("torch")), "ok"))
        if config.get("omnivoice"):
            zeilen.append(("OmniVoice", str(config.get("omnivoice")), "ok"))
        if config.get("faster_whisper") and whisper_python().exists():
            zeilen.append(("Faster-Whisper", str(config.get("faster_whisper")), "ok"))
        else:
            zeilen.append(("Faster-Whisper", "noch nicht eingerichtet", "warn"))
    else:
        zeilen.append(("Installation", "noch nicht vorhanden", "warn"))

    groesse = ordner_bytes(VENV_DIR)
    if groesse:
        zeilen.append(("Belegt vom Programm", bytes_lesbar(groesse), "ok"))
    modell = modell_ordner()
    if modell.exists():
        zeilen.append(("Belegt vom Sprachmodell", bytes_lesbar(ordner_bytes(modell)), "ok"))
    else:
        zeilen.append(("Sprachmodell", "noch nicht geladen", "warn"))
    whisper_modell = hub_modell_ordner(WHISPER_REPO)
    if whisper_modell.exists():
        zeilen.append((
            "Whisper-Modell medium", bytes_lesbar(ordner_bytes(whisper_modell)), "ok"
        ))
    else:
        zeilen.append(("Whisper-Modell medium", "noch nicht geladen", "warn"))
    return zeilen


# ------------------------------------------------------------
# Menü
# ------------------------------------------------------------

@dataclass
class MenuEintrag:
    taste: str
    titel: str
    beschreibung: str
    aktion: str


HILFE_TEXT = """\
## WAS IST DAS HIER?
OmniVoice ist ein KI-Programm zum Klonen von Stimmen: Du gibst eine kurze
Sprachaufnahme und einen Text vor – heraus kommt der Text, gesprochen mit
dieser Stimme. Alles läuft auf diesem PC. Es wird nichts hochgeladen.

Dieses Studio nimmt Dir die komplette Einrichtung ab.

## WAS PASSIERT BEI DER INSTALLATION?
 · Es wird geprüft, ob Python, Speicherplatz und Internet passen.
 · Ein eigener, abgeschotteter Python-Bereich wird angelegt. An Deinem
   System wird dabei nichts verändert.
 · PyTorch wird installiert – der KI-Motor. Mit NVIDIA-Grafikkarte die
    schnelle CUDA-Variante, sonst die Prozessor-Variante.
 · OmniVoice selbst wird installiert.
 · Das Sprachmodell (ca. 3,3 GB) wird von Hugging Face geladen.
 · Faster-Whisper kommt in einen zweiten, getrennten Python-Bereich. Dadurch
   kann es die OmniVoice-Pakete nicht verändern. Das Standardmodell »medium«
   (ca. 1,5 GB) wird gleich mitgeladen.
 · Zum Schluss wird alles getestet.

Gesamtbedarf: ungefähr 9 GB Speicherplatz.
Ein Abbruch ist ungefährlich – beim nächsten Start geht es weiter.

## WO LIEGT WAS?
 · Programmordner   {ordner}
 · Python-Bereich   {umgebung}
 · Sprachmodell     {modell}
 · Protokolle       {protokolle}
 · Modellquelle     {repo}

## WIE BENUTZE ICH OMNIVOICE?
Nach der Installation im Hauptmenü »OmniVoice starten« wählen. Es öffnet
sich der Browser mit der deutschen Bedienoberfläche. Die wichtigsten Reiter:

 · STIMME KLONEN     Sprachprobe hochladen oder mit dem Mikrofon aufnehmen
                     (5 bis 15 Sekunden genügen), Text eintippen, fertig.
                     Der Text darf in einer anderen Sprache sein als die
                     Sprachprobe – das Modell kann über 600 Sprachen.
 · ÜBERRASCHUNG      Das Modell sucht sich selbst eine Stimme aus.
 · LISTE ERZEUGEN     Audioordner transkribieren, englische Texte unscharf
                      zuordnen und per ID deutsche Texte in eine CSV übernehmen.
 · STAPEL            Ganze Projekte auf einmal vertonen – siehe unten.
                      Optional prüft Whisper jede Ausgabe und zeigt ein Rating.

Unter »Feineinstellung« lassen sich Qualität, Sprechtempo und eine feste
Länge einstellen – muss man aber nicht anfassen.

Ein Häkchen gibt es beim Klonen und im Stapel: »so lang wie die Sprachprobe«.
Damit bekommt die Ausgabe exakt die Länge der Vorlage – praktisch beim
Vertonen, wenn die deutsche Zeile ins Zeitfenster der englischen passen muss.

## STAPELBETRIEB: EIN GANZES PROJEKT VERTONEN
Der Reiter »Stapel« arbeitet eine CSV-Liste ab. Jede Zeile klont die Stimme
aus der englischen Audiodatei und spricht damit den deutschen Text:

    englische Audiodatei ; englischer Text ; deutscher Text

Getrennt wird mit Semikolon oder Komma, eine Kopfzeile darf drin sein, und
der mittlere Text darf fehlen – dann hört OmniVoice die Aufnahme selbst ab.

Wichtig ist der »Wurzelordner«: Er sagt, wo das Projekt anfängt. Der Teil
des Pfades unterhalb davon wird im Ausgabeordner nachgebaut. Beispiel:

    Wurzel  C:\\Projekte
    Quelle  C:\\Projekte\\habitat\\content\\audio\\wwise\\stimme.wav
    Ziel    ...\\Ergebnisse\\batch\\habitat\\content\\audio\\wwise\\stimme.wav

Bleibt das Feld leer, wird der gemeinsame Ordner aller Einträge genommen.
Vor dem Start lohnt sich »Liste prüfen«: das meldet fehlende Dateien und
zeigt einen Beispiel-Zielpfad, bevor Stunden ins Leere laufen.

Während des Laufs zeigt die Anzeige Fortschritt, verstrichene Zeit,
Restzeit, voraussichtliche Uhrzeit der Fertigstellung, Sekunden pro Datei,
Dateien pro Minute und die Zahl der Fehler. Am Ende entsteht im Ausgabe-
ordner ein Bericht als CSV mit einer Zeile je Eintrag.

Ein Abbruch ist ungefährlich: Mit »Bereits vorhandene Dateien überspringen«
macht der nächste Lauf genau dort weiter, wo der letzte aufgehört hat.

## SCHNELLER WERDEN: MEHRERE ARBEITER
Im Reiter »Einstellungen« lässt sich einstellen, wie viele Arbeiter der
Stapelbetrieb benutzt. Jeder Arbeiter ist ein eigener OmniVoice-Prozess mit
eigenem Modell im Grafikspeicher; die Dateien werden auf sie verteilt und
wirklich gleichzeitig berechnet.

 · 1 Arbeiter   rechnet im Hauptprozess, braucht keinen extra Speicher
 · ab 2         je Arbeiter rund 3,5 GB Grafikspeicher zusätzlich

Die Oberfläche schlägt anhand der erkannten Grafikkarte eine Obergrenze vor.
Die Arbeiter starten beim ersten Stapel von selbst und bleiben danach für
weitere Stapel bereit. »Arbeiter stoppen« gibt den Speicher wieder frei;
beim Schließen des Studios passiert das ohnehin automatisch.

Einstellungen (Arbeiterzahl, Qualität, Tempo, Ordner) lassen sich speichern
und stehen beim nächsten Start wieder bereit.

## WEITERE SCHALTER IN DEN EINSTELLUNGEN
 · Auslastung einblenden      kleines Fenster unten rechts mit Prozessor,
                              Arbeitsspeicher, Grafikkarte und Grafik-
                              speicher, alle zwei Sekunden aktualisiert
 · Signalton bei Stapelende   kurzer Dreiklang, wenn ein Stapel durch ist
 · Browser-Benachrichtigung   Meldung von Windows, auch wenn das Fenster
                              im Hintergrund liegt (fragt einmalig nach
                              Erlaubnis)
 · Browser-Tab blinken        der Reitertitel wechselt, bis das Fenster
                              wieder im Vordergrund ist

Diese drei Meldungen gelten nur für den Stapelbetrieb.

Im Stapel-Reiter gibt es außerdem ein Häkchen für den CSV-Bericht: aus
bedeutet, es wird am Ende keine Liste geschrieben. Im Reiter »Stimme klonen«
lässt sich einstellen, dass das Ergebnis sofort abgespielt wird – praktisch,
um schnell mehrere Texte hintereinander auszuprobieren.

Jede erzeugte Aufnahme wird automatisch gespeichert:
 · Ergebnisse       {ergebnisse}
Im Studio öffnet die Taste O diesen Ordner.

Für gute Klone: sauber aufgenommene Probe, kein Hall, keine Musik im
Hintergrund, nur eine sprechende Person.

Dieses Fenster muss dabei offen bleiben. Zum Beenden ESC drücken –
danach geht es von selbst zurück ins Hauptmenü.

## ES KLAPPT ETWAS NICHT
 · Kein Internet          Verbindung prüfen, Firewall oder VPN kurz aus.
 · Download bricht ab     Einfach erneut starten, es wird fortgesetzt.
 · Alles sehr langsam     Ohne NVIDIA-Grafikkarte rechnet der Prozessor.
                          Das ist normal, aber zäh.
 · CUDA nicht aktiv       NVIDIA-Treiber aktualisieren (Version 570 oder
                          neuer), danach »Reparieren« wählen.
 · Sonstige Fehler        »Reparieren« wählen. Hilft das nicht, im
                          Protokollordner die neueste Datei ansehen.

## PROGRAMM-UPDATES
Beim Start fragt das Studio im Hintergrund die Versionsdatei auf GitHub ab.
Der Status steht direkt im Hauptmenü. Liegt dort eine neuere Version, wird
Punkt [5] zum Update-Knopf.

Das Update ersetzt nur ausgelieferte Programmdateien. Ergebnisse,
Einstellungen, Protokolle und die eigene Python-Umgebung bleiben erhalten.
Vor dem Ersetzen wird eine Sicherung angelegt. Danach startet das Studio
automatisch mit der neuen Version neu.

## WIE WERDE ICH ALLES WIEDER LOS?
 · Den Ordner »toolkit« löschen – damit ist das Programm weg.
 · Für das Sprachmodell zusätzlich den oben genannten Modellordner
   löschen. Das sind die dicksten 3,3 GB.

## TASTEN
 · Pfeiltasten oder W und S   auswählen und blättern
 · Bild auf / Bild ab         seitenweise blättern
 · ENTER                      bestätigen
 · ESC                        zurück, abbrechen oder beenden
 · O                          Ergebnis-Ordner öffnen (während OmniVoice läuft)
 · Zifferntasten              Menüpunkte direkt aufrufen

## WER HAT DAS GEBAUT?
 · Deutsches Studio, Installer und Bedienoberfläche:   iZE
 · Sprachmodell OmniVoice:                             k2-fsa
 · Diese Fassung:                                      {version}

Das Studio selbst ist reines Python und nimmt sich nichts vom System:
alles Schwere liegt im Ordner »toolkit« und kann jederzeit gelöscht werden.

                                    iZE · lokal, deutsch, ohne Cloud
"""


# ------------------------------------------------------------
# Die Anwendung
# ------------------------------------------------------------

class Studio:
    FPS = 20
    SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def __init__(self, direkt_starten: bool = False) -> None:
        self.laeuft = True
        self.bildschirm = "menue"
        self.auswahl = 0
        self.frame = 0
        self.gestartet = time.perf_counter()
        self.status = "Bereit"
        self.blitz = ""
        self.blitz_bis = 0.0
        self.aufgabe = Aufgabe()
        self.arbeiter: Optional[Arbeiter] = None
        self.update_arbeiter: Optional[UpdateArbeiter] = None
        self.update_thread: Optional[threading.Thread] = None
        self.update_stand = UpdateStand()
        self.neustart_angefordert = False
        self.server: Optional[ServerStarter] = None
        self.grafik: Optional[Grafik] = None
        self.scan_zeilen: list[tuple[str, str, str]] = []
        self.hilfe_scroll = 0
        self.config = lade_config()
        self.frage: Optional[tuple[str, str, str]] = None    # (Titel, Text, Aktion)
        self._abschluss_gemeldet = False
        self._server_bereit_gemeldet = False
        self.kompakt = False
        self._rueckkehr_ab = 0.0    # Zeitpunkt, ab dem automatisch ins Menü gewechselt wird

        self.menue = [
            MenuEintrag("1", "OMNIVOICE INSTALLIEREN",
                        "Richtet alles vollautomatisch ein · ca. 9 GB · 15 bis 40 Minuten",
                        "installieren"),
            MenuEintrag("2", "OMNIVOICE STARTEN",
                        "Öffnet die Bedienoberfläche im Browser", "starten"),
            MenuEintrag("3", "SYSTEM PRÜFEN",
                        "Grafikkarte, Speicherplatz und Installation testen", "scan"),
            MenuEintrag("4", "REPARIEREN",
                        "Bei Problemen: Programm neu aufbauen, Sprachmodell bleibt erhalten",
                        "reparieren"),
            MenuEintrag("5", "UPDATE WIRD GEPRÜFT",
                        "Vergleicht diese Version im Hintergrund mit GitHub", "update"),
            MenuEintrag("6", "HILFE UND INFOS",
                        "Was passiert hier? Wo liegt was? Was tun bei Fehlern?", "hilfe"),
            MenuEintrag("0", "BEENDEN", "Fenster schließen", "beenden"),
        ]
        if self.config:
            whisper_fehlt = (
                not whisper_python().exists() or not self.config.get("faster_whisper")
            )
            if whisper_fehlt:
                self.menue[0].beschreibung = (
                    "Neu: Faster-Whisper und Modell medium ergänzen · OmniVoice bleibt erhalten"
                )
                self.auswahl = 0
            else:
                self.menue[0].beschreibung = (
                    "Bereits installiert · erneut ausführen bringt alles auf den neuesten Stand"
                )
                self.auswahl = 1

        threading.Thread(target=self._erkenne_grafik, daemon=True).start()
        self.starte_updatecheck()
        if direkt_starten:
            self.aktion_starten()

    def _erkenne_grafik(self) -> None:
        self.grafik = erkenne_grafik()

    def _aktualisiere_update_menue(self) -> None:
        eintrag = self.menue[4]
        stand = self.update_stand
        if stand.zustand == "verfuegbar":
            eintrag.titel = f"UPDATE AUF {stand.online} INSTALLIEREN"
            eintrag.beschreibung = "Programmdateien aktualisieren · Ergebnisse und Umgebung bleiben erhalten"
        elif stand.zustand == "prueft":
            eintrag.titel = "UPDATE WIRD GEPRÜFT"
            eintrag.beschreibung = "Vergleicht diese Version im Hintergrund mit GitHub"
        else:
            eintrag.titel = "NACH UPDATES SUCHEN"
            eintrag.beschreibung = (
                f"{stand.lokal} ist aktuell · Prüfung erneut starten"
                if stand.zustand == "aktuell"
                else "GitHub war nicht erreichbar · Prüfung erneut versuchen"
            )

    def starte_updatecheck(self, manuell: bool = False) -> None:
        if self.update_thread and self.update_thread.is_alive():
            if manuell:
                self.melde("Die Updateprüfung läuft bereits.")
            return
        self.update_stand = UpdateStand()
        self._aktualisiere_update_menue()
        if manuell:
            self.status = "GitHub wird nach einer neuen Version gefragt …"

        def arbeite() -> None:
            self.update_stand = pruefe_update_online()
            self._aktualisiere_update_menue()
            if manuell:
                self.status = "Bereit"
                self.melde(self.update_stand.meldung, 5.0)

        self.update_thread = threading.Thread(target=arbeite, daemon=True)
        self.update_thread.start()

    def melde(self, text: str, dauer: float = 3.0) -> None:
        self.blitz = text
        self.blitz_bis = time.time() + dauer

    # -- Aktionen --------------------------------------------------
    def aktion(self, name: str) -> None:
        if name == "installieren":
            if self.aufgabe.laeuft:
                return
            if self.config:
                if not whisper_python().exists() or not self.config.get("faster_whisper"):
                    self.frage = (
                        "Faster-Whisper ergänzen?",
                        "OmniVoice selbst bleibt dabei unverändert.\n"
                        "Nur die getrennte Whisper-Umgebung und das Modell medium werden ergänzt.\n"
                        "Benötigt werden ungefähr 2 GB zusätzlicher Speicherplatz.",
                        "whisper",
                    )
                else:
                    self.frage = (
                        "Erneut installieren?",
                        "OmniVoice ist bereits installiert.\n"
                        "Ein erneuter Durchlauf prüft alles und aktualisiert fehlende Teile.\n"
                        "Bereits geladene Daten werden nicht noch einmal heruntergeladen.",
                        "installieren",
                    )
                self.bildschirm = "frage"
            else:
                self.starte_arbeit("installieren")
        elif name == "reparieren":
            self.frage = (
                "Wirklich reparieren?",
                "Die installierten Programmteile werden gelöscht und neu aufgebaut.\n"
                "Die Sprachmodelle bleiben erhalten und werden nicht neu geladen.\n"
                "Dauer: ungefähr 10 bis 30 Minuten.",
                "reparieren",
            )
            self.bildschirm = "frage"
        elif name == "starten":
            self.aktion_starten()
        elif name == "scan":
            self.starte_scan()
        elif name == "update":
            if self.update_stand.zustand == "verfuegbar":
                self.frage = (
                    f"Auf {self.update_stand.online} aktualisieren?",
                    f"Installiert ist {self.update_stand.lokal}, auf GitHub liegt "
                    f"{self.update_stand.online}.\n"
                    "Aktualisiert werden nur die Programmdateien.\n"
                    "Ergebnisse, Einstellungen, Protokolle und die Python-Umgebung "
                    "bleiben erhalten.\n"
                    "Nach dem Download startet das Studio automatisch neu.",
                    "update",
                )
                self.bildschirm = "frage"
            else:
                self.starte_updatecheck(manuell=True)
        elif name == "hilfe":
            self.hilfe_scroll = 0
            self.bildschirm = "hilfe"
            self.status = "Hilfe"
        elif name == "beenden":
            self.laeuft = False

    def starte_update(self) -> None:
        if self.update_stand.zustand != "verfuegbar" or not self.update_stand.online:
            self.melde("Keine neuere Version vorgemerkt – bitte erneut prüfen.", 4.0)
            self.zurueck_zum_menue()
            return
        self.aufgabe = Aufgabe()
        self.aufgabe.titel = f"UPDATE AUF {self.update_stand.online}"
        self.aufgabe.schritte = [
            Schritt("version", "Version erneut prüfen", "GitHub-Stand bestätigen", 5),
            Schritt("download", "Update herunterladen", "komplettes Programmpaket", 15),
            Schritt("pruefen", "Paket prüfen und sichern", "lokale Daten ausschließen", 5),
            Schritt("anwender", "Neustart vorbereiten", "sicher außerhalb der laufenden App", 3),
        ]
        self.update_arbeiter = UpdateArbeiter(
            self.aufgabe, self.update_stand.online, self.update_stand.commit
        )
        self.update_arbeiter.start()
        self.bildschirm = "update"
        self.status = "Update wird heruntergeladen und geprüft …"

    def aktion_starten(self) -> None:
        if not venv_python().exists() or not self.config:
            self.melde("OmniVoice ist noch nicht installiert – bitte zuerst Punkt [1] wählen.", 4.0)
            self.auswahl = 0
            return
        self.aufgabe = Aufgabe()
        self.aufgabe.titel = "OMNIVOICE LÄUFT"
        self.aufgabe.oeffne_protokoll("start")
        self._server_bereit_gemeldet = False
        self.server = ServerStarter(self.aufgabe)
        self.server.start()
        self.bildschirm = "server"
        self.status = "OmniVoice startet …"

    def starte_arbeit(self, modus: str) -> None:
        if self.aufgabe.laeuft:
            return
        grafik = self.grafik or Grafik()
        self._abschluss_gemeldet = False
        self.aufgabe = Aufgabe()
        self.aufgabe.titel = {
            "installieren": "INSTALLATION LÄUFT",
            "reparieren": "REPARATUR LÄUFT",
            "modell": "SPRACHMODELL WIRD GELADEN",
            "whisper": "FASTER-WHISPER WIRD ERGÄNZT",
        }.get(modus, "ES WIRD GEARBEITET")
        self.aufgabe.schritte = baue_schritte(modus, grafik)
        self.aufgabe.oeffne_protokoll(modus)
        self.aufgabe.log(f"OmniVoice Studio {APP_VERSION} · {modus}")
        self.aufgabe.log(f"Ordner: {TOOLKIT_DIR}")
        self.arbeiter = Arbeiter(self.aufgabe, modus, grafik)
        self.arbeiter.start()
        self.bildschirm = "arbeit"
        self.status = "Es läuft – das Fenster darf offen bleiben"

    def starte_scan(self) -> None:
        self.bildschirm = "scan"
        self.scan_zeilen = []
        self.status = "Das System wird geprüft …"

        def arbeite() -> None:
            zeilen = sammle_systemdaten()
            self.scan_zeilen = zeilen
            self.status = "Systemprüfung abgeschlossen"

        threading.Thread(target=arbeite, daemon=True).start()

    def pruefe_rueckkehr(self) -> None:
        """Nach dem Beenden von OmniVoice von selbst ins Hauptmenü zurückgehen."""
        if self.bildschirm != "server":
            self._rueckkehr_ab = 0.0
            return
        if self.aufgabe.laeuft or self.aufgabe.fehler:
            self._rueckkehr_ab = 0.0
            return
        if not self._rueckkehr_ab:
            self._rueckkehr_ab = time.time() + 2.5
            self.status = "OmniVoice wurde beendet – zurück zum Hauptmenü"
        elif time.time() >= self._rueckkehr_ab:
            self._rueckkehr_ab = 0.0
            self.server = None
            self.zurueck_zum_menue()

    def zurueck_zum_menue(self) -> None:
        self.bildschirm = "menue"
        self.status = "Bereit"
        self._rueckkehr_ab = 0.0
        self.config = lade_config()
        if self.config:
            if whisper_python().exists() and self.config.get("faster_whisper"):
                self.menue[0].beschreibung = (
                    "Bereits installiert · erneut ausführen bringt alles auf den neuesten Stand"
                )
            else:
                self.menue[0].beschreibung = (
                    "Neu: Faster-Whisper und Modell medium ergänzen · OmniVoice bleibt erhalten"
                )

    # -- Tasten ----------------------------------------------------
    def taste(self, key: Optional[str]) -> None:
        if key is None:
            return
        if self.bildschirm == "menue":
            self.taste_menue(key)
        elif self.bildschirm == "arbeit":
            self.taste_arbeit(key)
        elif self.bildschirm == "server":
            self.taste_server(key)
        elif self.bildschirm == "update":
            self.taste_update(key)
        elif self.bildschirm == "scan":
            if key in ("ESC", "ENTER", "q"):
                self.zurueck_zum_menue()
            elif key == "r":
                self.starte_scan()
        elif self.bildschirm == "hilfe":
            if key in ("ESC", "ENTER", "q"):
                self.zurueck_zum_menue()
            elif key in ("RUNTER", "s"):
                self.hilfe_scroll += 1
            elif key in ("HOCH", "w"):
                self.hilfe_scroll = max(0, self.hilfe_scroll - 1)
            elif key == "BILD_RUNTER":
                self.hilfe_scroll += 10
            elif key == "BILD_HOCH":
                self.hilfe_scroll = max(0, self.hilfe_scroll - 10)
            elif key == "ANFANG":
                self.hilfe_scroll = 0
        elif self.bildschirm == "frage":
            if key in ("j", "z", "ENTER"):
                aktion = self.frage[2] if self.frage else ""
                self.frage = None
                if aktion == "update":
                    self.starte_update()
                elif aktion in ("installieren", "reparieren", "modell", "whisper"):
                    self.starte_arbeit(aktion)
                else:
                    self.zurueck_zum_menue()
            elif key in ("n", "ESC"):
                self.frage = None
                self.zurueck_zum_menue()

    def taste_menue(self, key: str) -> None:
        if key in ("RUNTER", "s"):
            self.auswahl = (self.auswahl + 1) % len(self.menue)
        elif key in ("HOCH", "w"):
            self.auswahl = (self.auswahl - 1) % len(self.menue)
        elif key == "ENTER":
            self.aktion(self.menue[self.auswahl].aktion)
        elif key == "ESC":
            self.laeuft = False
        else:
            for index, eintrag in enumerate(self.menue):
                if key == eintrag.taste:
                    self.auswahl = index
                    self.aktion(eintrag.aktion)
                    return

    def taste_update(self, key: str) -> None:
        if key in ("RUNTER", "s"):
            self.aufgabe.log_scroll = max(0, self.aufgabe.log_scroll - 1)
        elif key in ("HOCH", "w"):
            self.aufgabe.log_scroll += 1
        elif key == "BILD_RUNTER":
            self.aufgabe.log_scroll = max(0, self.aufgabe.log_scroll - 10)
        elif key == "BILD_HOCH":
            self.aufgabe.log_scroll += 10
        elif key == "ENTER" and self.aufgabe.fertig:
            self.neustart_angefordert = True
            self.laeuft = False
        elif key == "ESC":
            if self.aufgabe.laeuft:
                self.melde("Das Update wird gerade sicher vorbereitet und kann nicht abgebrochen werden.", 4.0)
            else:
                self.zurueck_zum_menue()
        elif key == "p" and not self.aufgabe.laeuft:
            self.oeffne_ordner(PROTOKOLL_DIR)

    def taste_arbeit(self, key: str) -> None:
        if key in ("RUNTER", "s"):
            self.aufgabe.log_scroll = max(0, self.aufgabe.log_scroll - 1)
        elif key in ("HOCH", "w"):
            self.aufgabe.log_scroll += 1
        elif key == "BILD_RUNTER":
            self.aufgabe.log_scroll = max(0, self.aufgabe.log_scroll - 10)
        elif key == "BILD_HOCH":
            self.aufgabe.log_scroll += 10
        elif key == "ENTER":
            if self.aufgabe.fertig:
                self.config = lade_config()
                self.aktion_starten()
            elif not self.aufgabe.laeuft:
                self.zurueck_zum_menue()
        elif key == "ESC":
            if self.aufgabe.laeuft and self.arbeiter:
                self.arbeiter.stoppen()
                self.melde("Wird abgebrochen – bitte einen Moment …", 4.0)
            else:
                self.zurueck_zum_menue()
        elif key == "p" and not self.aufgabe.laeuft:
            self.oeffne_ordner(PROTOKOLL_DIR)

    def taste_server(self, key: str) -> None:
        if key == "ESC":
            if self.aufgabe.laeuft and self.server:
                self.server.stoppen()
                self.melde("OmniVoice wird beendet …", 4.0)
            else:
                self.zurueck_zum_menue()
        elif key == "b" and self.server:
            self.server.browser_geoeffnet = False
            self.server.oeffne_browser()
        elif key == "o":
            self.oeffne_ordner(ERGEBNIS_DIR)
        elif key in ("HOCH", "w"):
            self.aufgabe.log_scroll += 1
        elif key in ("RUNTER", "s"):
            self.aufgabe.log_scroll = max(0, self.aufgabe.log_scroll - 1)
        elif key == "BILD_HOCH":
            self.aufgabe.log_scroll += 10
        elif key == "BILD_RUNTER":
            self.aufgabe.log_scroll = max(0, self.aufgabe.log_scroll - 10)
        elif key == "ENTER" and not self.aufgabe.laeuft:
            self.zurueck_zum_menue()

    def oeffne_ordner(self, pfad: Path) -> None:
        try:
            pfad.mkdir(parents=True, exist_ok=True)
            if os.name == "nt":
                os.startfile(str(pfad))
            self.melde(f"Ordner geöffnet: {pfad}")
        except Exception as fehler:
            self.melde(f"Der Ordner ließ sich nicht öffnen: {fehler}", 4.0)

    # -- Zeichnen --------------------------------------------------
    def spinner(self) -> str:
        return self.SPINNER[self.frame % len(self.SPINNER)]

    def welle(self, breite: int) -> str:
        zeichen = "▁▂▃▄▅▆▇█"
        aktiv = self.aufgabe.laeuft
        staerke = 1.0 if aktiv else 0.4
        werte = []
        for x in range(breite):
            a = math.sin((x + self.frame * 1.35) * 0.26)
            b = math.sin((x - self.frame * 0.7) * 0.11) * 0.55
            c = math.sin((x + self.frame * 0.3) * 0.05) * 0.3
            rauschen = random.uniform(-0.05, 0.05) if aktiv else 0.0
            wert = ((a + b + c + rauschen) * staerke + 1.95) / 3.9
            werte.append(zeichen[int(max(0.0, min(0.999, wert)) * len(zeichen))])
        return "".join(werte)

    def kopf(self, breite: int) -> list[str]:
        laufzeit = int(time.perf_counter() - self.gestartet)
        minuten, sekunden = divmod(laufzeit, 60)
        gpu = self.grafik.beschriftung if self.grafik else "Grafikkarte wird erkannt …"
        zustand = "installiert" if self.config else "noch nicht installiert"
        infos = f"{gpu}   ·   Zustand: {zustand}   ·   Laufzeit {minuten:02d}:{sekunden:02d}"

        if self.kompakt:
            # Kleines Fenster: Untertitel und Versionszeile entfallen.
            return [
                rahmen_oben(breite),
                zeile(f"{APP_NAME}    ·    {APP_MARKE}", breite, FG_MAGENTA + BOLD, "mitte"),
                zeile(self.welle(max(20, breite - 12)), breite, FG_CYAN, "mitte"),
                zeile(infos, breite, FG_GRAU, "mitte"),
                rahmen_mitte(breite),
            ]
        return [
            rahmen_oben(breite),
            zeile(APP_NAME, breite, FG_MAGENTA + BOLD, "mitte"),
            zeile(APP_UNTERTITEL, breite, FG_WEISS, "mitte"),
            zeile(f"{APP_VERSION}   ·   {APP_FUSS}", breite, FG_GRAU, "mitte"),
            rahmen_mitte(breite),
            zeile(self.welle(max(20, breite - 12)), breite, FG_CYAN, "mitte"),
            zeile(infos, breite, FG_GRAU, "mitte"),
            rahmen_mitte(breite),
        ]

    def fuss(self, breite: int) -> list[str]:
        hilfen = {
            "menue": "↑↓ auswählen   ·   ENTER öffnen   ·   Zifferntasten direkt   ·   ESC beenden",
            "arbeit": "↑↓ Bild↑↓ im Protokoll blättern   ·   ESC abbrechen bzw. zurück   ·   ENTER weiter",
            "update": "↑↓ Bild↑↓ im Protokoll   ·   ENTER Update anwenden   ·   ESC zurück",
            "server": "B Browser öffnen   ·   O Ergebnis-Ordner   ·   ↑↓ Protokoll   ·   ESC OmniVoice beenden",
            "scan": "R erneut prüfen   ·   ESC zurück",
            "hilfe": "↑↓ Bild↑↓ blättern   ·   ESC zurück",
            "frage": "J bestätigen   ·   N abbrechen",
        }
        text = self.blitz if time.time() < self.blitz_bis else self.status
        return [
            rahmen_mitte(breite),
            zeile(hilfen.get(self.bildschirm, "ESC zurück"), breite, FG_GRAU, "mitte"),
            zeile(text, breite, FG_GRUEN + BOLD, "mitte"),
            rahmen_unten(breite),
        ]

    def fuellen(self, zeilen: list[str], breite: int, hoehe: int) -> list[str]:
        if len(zeilen) > hoehe:
            return zeilen[:hoehe]
        while len(zeilen) < hoehe:
            zeilen.append(leerzeile(breite))
        return zeilen

    def zeichne_menue(self, breite: int, hoehe: int) -> list[str]:
        zeilen = [
            zeile("H A U P T M E N Ü", breite, FG_MAGENTA + BOLD, "mitte"),
            leerzeile(breite),
        ]
        for index, eintrag in enumerate(self.menue):
            gewaehlt = index == self.auswahl
            pfeil = "▶" if gewaehlt else " "
            zeilen.append(zeile(f"  {pfeil} [{eintrag.taste}]  {eintrag.titel}", breite,
                                (FG_CYAN + BOLD) if gewaehlt else FG_WEISS))
            zeilen.append(zeile(f"         {eintrag.beschreibung}", breite,
                                FG_WEISS if gewaehlt else FG_GRAU))
            zeilen.append(leerzeile(breite))

        stand = self.update_stand
        update_farbe = {
            "prueft": FG_CYAN,
            "aktuell": FG_GRUEN,
            "verfuegbar": FG_GELB + BOLD,
            "fehler": FG_GRAU,
        }.get(stand.zustand, FG_GRAU)
        update_symbol = {
            "prueft": self.spinner(),
            "aktuell": "✔",
            "verfuegbar": "!",
            "fehler": "·",
        }.get(stand.zustand, "·")
        zeilen.append(zeile(
            f"{update_symbol}  Update: {stand.meldung}",
            breite, update_farbe, "mitte",
        ))

        if self.config:
            zeilen.append(zeile(
                f"Installiert am {self.config.get('installiert_am', '?')}   ·   "
                f"Betriebsart {self.config.get('stufe', '?')}   ·   "
                f"PyTorch {self.config.get('torch', '?')}", breite, FG_GRUEN, "mitte"))
            zeilen.append(zeile("Tipp: Einfach ENTER drücken – OmniVoice startet sofort.",
                                breite, FG_GRAU, "mitte"))
        else:
            zeilen.append(zeile("Noch nichts installiert. Tipp: Einfach ENTER drücken.",
                                breite, FG_GELB + BOLD, "mitte"))
            zeilen.append(zeile("Gebraucht werden ungefähr 9 GB Speicherplatz und eine Internetverbindung.",
                                breite, FG_GRAU, "mitte"))
        return self.fuellen(zeilen, breite, hoehe)

    def zeichne_frage(self, breite: int, hoehe: int) -> list[str]:
        titel, text, _aktion = self.frage or ("", "", "")
        zeilen = [leerzeile(breite), zeile(titel, breite, FG_GELB + BOLD, "mitte"), leerzeile(breite)]
        for stueck in text.splitlines():
            zeilen.append(zeile(stueck, breite, FG_WEISS, "mitte"))
        zeilen.append(leerzeile(breite))
        zeilen.append(zeile("[ J ]  ja, los geht's          [ N ]  nein, zurück",
                            breite, FG_CYAN + BOLD, "mitte"))
        return self.fuellen(zeilen, breite, hoehe)

    def schritt_symbol(self, schritt: Schritt) -> tuple[str, str]:
        if schritt.status == "fertig":
            return "✔", FG_GRUEN
        if schritt.status == "laeuft":
            return self.spinner(), FG_CYAN + BOLD
        if schritt.status == "fehler":
            return "✖", FG_ROT
        if schritt.status == "uebersprungen":
            return "–", FG_GRAU
        return "·", FG_GRAU

    def zeichne_arbeit(self, breite: int, hoehe: int) -> list[str]:
        aufgabe = self.aufgabe
        ist_update = self.bildschirm == "update"
        knapp = hoehe < 26
        zeilen: list[str] = []

        if aufgabe.fertig:
            titel = (
                "UPDATE BEREIT  ·  NEUSTART ZUM ANWENDEN"
                if ist_update else "FERTIG  ·  OMNIVOICE IST EINSATZBEREIT"
            )
            farbe = FG_GRUEN + BOLD
        elif aufgabe.fehler:
            titel, farbe = "ES GAB EIN PROBLEM", FG_ROT + BOLD
        elif aufgabe.abgebrochen:
            titel, farbe = "ABGEBROCHEN", FG_GELB + BOLD
        else:
            titel, farbe = aufgabe.titel, FG_MAGENTA + BOLD
        zeilen.append(zeile(titel, breite, farbe, "mitte"))

        aktiv = aufgabe.schritte[aufgabe.aktiv] if 0 <= aufgabe.aktiv < len(aufgabe.schritte) else None
        if aktiv and aufgabe.laeuft:
            zeilen.append(zeile(f"Schritt {aufgabe.aktiv + 1} von {len(aufgabe.schritte)}: {aktiv.titel}",
                                breite, FG_WEISS + BOLD, "mitte"))
        else:
            zeilen.append(zeile(kuerze(aufgabe.meldung, breite - 6), breite, FG_WEISS, "mitte"))
        if not knapp:
            zeilen.append(leerzeile(breite))

        breite_balken = max(18, breite - 54)
        gesamt = aufgabe.gesamt_anteil()
        if aufgabe.fertig:
            rest_text = "fertig"
        elif aufgabe.fehler or aufgabe.abgebrochen:
            rest_text = "gestoppt"
        else:
            rest_text = "noch ca. " + zeit_lesbar(aufgabe.gesamt_restzeit())
        zeilen.append(zeile(
            f"GESAMT   [{balken(gesamt, breite_balken)}] {prozent(gesamt)} %   {rest_text}",
            breite, FG_MAGENTA + BOLD))

        anteil = aktiv.anteil() if aktiv else 0.0
        rest = ("noch ca. " + zeit_lesbar(aktiv.restzeit())) if (aktiv and aufgabe.laeuft) else ""
        zeilen.append(zeile(
            f"SCHRITT  [{balken(anteil, breite_balken, '▓', '▒', '░')}] {prozent(anteil)} %   {rest}",
            breite, FG_CYAN + BOLD))

        if aufgabe.bytes_fertig > 0 and aufgabe.laeuft:
            tempo = f"{bytes_lesbar(aufgabe.tempo)}/s" if aufgabe.tempo > 0 else "misst …"
            offen = max(0, aufgabe.bytes_gesamt - aufgabe.bytes_fertig)
            eta = zeit_lesbar(offen / aufgabe.tempo) if aufgabe.tempo > 100_000 else "--:--"
            zeilen.append(zeile(
                f"DATEN    {bytes_lesbar(aufgabe.bytes_fertig)} von {bytes_lesbar(aufgabe.bytes_gesamt)}"
                f"   ·   {tempo}   ·   noch ca. {eta}", breite, FG_GRUEN))
        else:
            zeilen.append(zeile(f"LAUFZEIT {zeit_lesbar(aufgabe.laufzeit())}", breite, FG_GRUEN))
        if not knapp:
            zeilen.append(zeile("DATEI    " + aufgabe.datei if aufgabe.datei else "", breite, FG_GRAU))

        schluss: list[str] = []
        if aufgabe.fertig:
            text = (
                "ENTER  =  Update anwenden und Studio neu starten     ESC  =  später"
                if ist_update
                else "ENTER  =  OmniVoice jetzt starten          ESC  =  zum Hauptmenü"
            )
            schluss.append(zeile(text, breite, FG_GRUEN + BOLD, "mitte"))
        elif aufgabe.fehler or aufgabe.abgebrochen:
            schluss.append(zeile("ESC  =  zum Hauptmenü          P  =  Protokollordner öffnen",
                                 breite, FG_WEISS, "mitte"))

        # Platz aufteilen: Schrittliste schrumpft zuerst, das Protokoll behält
        # immer mindestens drei Zeilen. So wird nie etwas abgeschnitten.
        frei = hoehe - len(zeilen) - len(schluss) - 1        # 1 = Protokollüberschrift
        platz_schritte = max(0, min(len(aufgabe.schritte), frei - 4 - (0 if knapp else 1)))
        if not knapp and platz_schritte > 0:
            zeilen.append(leerzeile(breite))
        zeilen.extend(self.schritt_liste(aufgabe, breite, platz_schritte))
        zeilen.extend(schluss)
        if not knapp and hoehe - len(zeilen) >= 6:
            zeilen.append(leerzeile(breite))
        zeilen.extend(self.protokoll_block(aufgabe, breite, hoehe - len(zeilen)))
        return self.fuellen(zeilen, breite, hoehe)

    def schritt_liste(self, aufgabe: Aufgabe, breite: int, platz: int) -> list[str]:
        """Schrittliste; bei wenig Platz nur ein Ausschnitt um den laufenden Schritt."""
        if platz <= 0:
            return []
        schritte = aufgabe.schritte
        von, bis = 0, len(schritte)
        if platz < len(schritte):
            mitte = max(0, aufgabe.aktiv)
            von = max(0, min(mitte - platz // 2, len(schritte) - platz))
            bis = von + platz

        zeilen = []
        for index in range(von, bis):
            schritt = schritte[index]
            symbol, farbe = self.schritt_symbol(schritt)
            if schritt.status in ("fertig", "laeuft"):
                dauer = zeit_lesbar(schritt.laufzeit)
            elif schritt.status == "fehler":
                dauer = "Fehler"
            else:
                dauer = "ca. " + zeit_lesbar(schritt.schaetzung)
            text = f"  {symbol}  {index + 1}. {schritt.titel:<32} {dauer:>9}   {schritt.hinweis}"
            if index == von and von > 0:
                text = f"  ▲  … {von} Schritte darüber"
                farbe = FG_GRAU
            elif index == bis - 1 and bis < len(schritte):
                text = f"  ▼  … noch {len(schritte) - bis + 1} Schritte"
                farbe = FG_GRAU
            zeilen.append(zeile(text, breite, farbe if schritt.status != "wartet" else FG_GRAU))
        return zeilen

    def protokoll_block(self, aufgabe: Aufgabe, breite: int, platz: int,
                        titel: str = "LIVE-PROTOKOLL") -> list[str]:
        """Überschrift mit Blätterhinweis, darunter das Protokoll mit Bildlaufbalken."""
        platz = max(3, platz - 1)
        with aufgabe.sperre:
            logs = list(aufgabe.logs)
        if not logs:
            logs = ["Es geht gleich los …"]

        max_scroll = max(0, len(logs) - platz)
        aufgabe.log_scroll = min(aufgabe.log_scroll, max_scroll)
        ende = len(logs) - aufgabe.log_scroll
        start = max(0, ende - platz)

        if len(logs) > platz:
            hinweis = f"▲▼ blättern · Zeile {start + 1}–{ende} von {len(logs)}"
            if aufgabe.log_scroll == 0:
                hinweis += " · am Ende"
        else:
            hinweis = f"{len(logs)} Zeilen"

        zeilen = [zeile(zwei_spalten(titel, hinweis, breite), breite, FG_MAGENTA + BOLD)]
        marken = leisten_marken(len(logs), platz, start)
        for nummer, text in enumerate(logs[start:ende]):
            gross = text.upper()
            if "FEHLER" in gross or "ERROR" in gross or "TRACEBACK" in gross:
                farbe = FG_ROT
            elif "SUCCESSFULLY" in gross or "ERLEDIGT" in gross or "127.0.0.1" in gross:
                farbe = FG_GRUEN
            elif text.startswith("$") or text.startswith("──"):
                farbe = FG_CYAN
            elif "WARN" in gross or "HINWEIS" in gross or "ACHTUNG" in gross:
                farbe = FG_GELB
            else:
                farbe = FG_NORMAL
            marke = marken[nummer] if nummer < len(marken) else " "
            zeilen.append(zeile_mit_leiste(text, breite, farbe, marke))
        return zeilen

    def zeichne_server(self, breite: int, hoehe: int) -> list[str]:
        aufgabe = self.aufgabe
        server = self.server
        zeilen: list[str] = []

        if aufgabe.fehler:
            zeilen.append(zeile("OMNIVOICE KONNTE NICHT GESTARTET WERDEN", breite, FG_ROT + BOLD, "mitte"))
        elif server and server.bereit and aufgabe.laeuft:
            zeilen.append(zeile("OMNIVOICE GESTARTET · WEBUI LÄUFT",
                                breite, FG_GRUEN + BOLD, "mitte"))
        elif aufgabe.laeuft:
            zeilen.append(zeile("OMNIVOICE STARTET …", breite, FG_MAGENTA + BOLD, "mitte"))
        else:
            zeilen.append(zeile("OMNIVOICE WURDE BEENDET", breite, FG_GELB + BOLD, "mitte"))
        zeilen.append(leerzeile(breite))

        if server and server.url:
            zeilen.append(zeile(f"Adresse im Browser:  {server.url}", breite, FG_CYAN + BOLD, "mitte"))
        if server and aufgabe.laeuft and not server.bereit:
            wartezeit = time.time() - server.gestartet
            zeilen.append(zeile(
                f"{self.spinner()}  Das Sprachmodell wird in den Speicher geladen …  {zeit_lesbar(wartezeit)}",
                breite, FG_WEISS, "mitte"))
            zeilen.append(zeile("Beim ersten Mal dauert das 1 bis 3 Minuten, danach geht es schneller.",
                                breite, FG_GRAU, "mitte"))
        elif server and server.bereit and aufgabe.laeuft:
            zeilen.append(zeile("Der Browser sollte sich geöffnet haben. Falls nicht: Taste B drücken.",
                                breite, FG_GRAU, "mitte"))
            zeilen.append(zeile(f"Fertige Aufnahmen landen in:  {ERGEBNIS_DIR}", breite, FG_GRAU, "mitte"))
            zeilen.append(zeile("Dieses Fenster bitte offen lassen, solange OmniVoice benutzt wird.",
                                breite, FG_GRAU, "mitte"))
        if not aufgabe.laeuft:
            for stueck in umbruch(aufgabe.meldung, breite - 8):
                zeilen.append(zeile(stueck, breite, FG_GELB, "mitte"))
            if not aufgabe.fehler:
                zeilen.append(zeile("Zurück zum Hauptmenü …", breite, FG_GRAU, "mitte"))
            else:
                zeilen.append(zeile("ESC oder ENTER  =  zurück zum Hauptmenü", breite, FG_WEISS, "mitte"))

        zeilen.append(leerzeile(breite))
        zeilen.extend(self.protokoll_block(aufgabe, breite, hoehe - len(zeilen), "PROTOKOLL"))
        return self.fuellen(zeilen, breite, hoehe)

    def zeichne_scan(self, breite: int, hoehe: int) -> list[str]:
        zeilen = [zeile("S Y S T E M P R Ü F U N G", breite, FG_MAGENTA + BOLD, "mitte"),
                  leerzeile(breite)]
        if not self.scan_zeilen:
            zeilen.append(zeile(f"{self.spinner()}  Hardware, Speicherplatz und Internet werden geprüft …",
                                breite, FG_CYAN, "mitte"))
            return self.fuellen(zeilen, breite, hoehe)

        for name, wert, bewertung in self.scan_zeilen:
            punkte = "." * max(3, 28 - len(name))
            farbe = {"ok": FG_GRUEN, "warn": FG_GELB, "schlecht": FG_ROT}.get(bewertung, FG_NORMAL)
            symbol = {"ok": "✔", "warn": "!", "schlecht": "✖"}.get(bewertung, "·")
            zeilen.append(zeile(f"  {symbol}  {name} {punkte} {wert}", breite, farbe))

        zeilen.append(leerzeile(breite))
        if self.grafik and self.grafik.hinweis:
            for stueck in umbruch(self.grafik.hinweis, breite - 10):
                zeilen.append(zeile("  " + stueck, breite, FG_GELB))
            zeilen.append(leerzeile(breite))
        zeilen.append(zeile(f"Programmordner : {TOOLKIT_DIR}", breite, FG_GRAU))
        zeilen.append(zeile(f"Sprachmodell   : {modell_ordner()}", breite, FG_GRAU))
        zeilen.append(zeile(f"Protokolle     : {PROTOKOLL_DIR}", breite, FG_GRAU))
        return self.fuellen(zeilen, breite, hoehe)

    def zeichne_hilfe(self, breite: int, hoehe: int) -> list[str]:
        text = HILFE_TEXT.format(
            ordner=TOOLKIT_DIR, modell=modell_ordner(), protokolle=PROTOKOLL_DIR,
            umgebung=VENV_DIR, repo=MODELL_REPO, ergebnisse=ERGEBNIS_DIR,
            version=APP_VERSION,
        ).splitlines()
        platz = max(1, hoehe - 2)
        max_scroll = max(0, len(text) - platz)
        self.hilfe_scroll = min(self.hilfe_scroll, max_scroll)
        if max_scroll:
            anteil = self.hilfe_scroll / max_scroll
            hinweis = f"▲▼ blättern · {anteil * 100:3.0f} %"
            if self.hilfe_scroll == 0:
                hinweis = "▼ weiter blättern mit Pfeil ab"
            elif self.hilfe_scroll >= max_scroll:
                hinweis = "▲ Ende erreicht"
        else:
            hinweis = ""
        titel = "H I L F E   U N D   I N F O S".center(max(1, breite - 6 - len(hinweis)))
        zeilen = [zeile(zwei_spalten(titel, hinweis, breite), breite, FG_MAGENTA + BOLD),
                  leerzeile(breite)]
        marken = leisten_marken(len(text), platz, self.hilfe_scroll)
        for nummer, stueck in enumerate(text[self.hilfe_scroll:self.hilfe_scroll + platz]):
            farbe = FG_CYAN + BOLD if stueck.startswith("##") else FG_NORMAL
            if stueck.startswith("##"):
                stueck = stueck[2:].strip()
            marke = marken[nummer] if nummer < len(marken) else " "
            zeilen.append(zeile_mit_leiste(stueck, breite, farbe, marke))
        return self.fuellen(zeilen, breite, hoehe)

    def zeichne(self) -> None:
        spalten, reihen = terminal_groesse()
        breite = max(80, min(spalten, 122))
        self.kompakt = reihen < 38
        kopf = self.kopf(breite)
        fuss = self.fuss(breite)
        hoehe = max(6, reihen - len(kopf) - len(fuss) - 1)

        if self.bildschirm == "menue":
            inhalt = self.zeichne_menue(breite, hoehe)
        elif self.bildschirm in ("arbeit", "update"):
            inhalt = self.zeichne_arbeit(breite, hoehe)
        elif self.bildschirm == "server":
            inhalt = self.zeichne_server(breite, hoehe)
        elif self.bildschirm == "scan":
            inhalt = self.zeichne_scan(breite, hoehe)
        elif self.bildschirm == "frage":
            inhalt = self.zeichne_frage(breite, hoehe)
        else:
            inhalt = self.zeichne_hilfe(breite, hoehe)

        rand = " " * max(0, (spalten - breite) // 2)
        bild = "\n".join(rand + z for z in (kopf + inhalt + fuss))
        sys.stdout.write(HOME + bild + "\033[0J")
        sys.stdout.flush()

    # -- Hauptschleife ---------------------------------------------
    def aktualisiere_serverstatus(self) -> None:
        """Übernimmt den Thread-Zustand in die dauerhaft sichtbare Statuszeile."""
        if self.bildschirm != "server" or not self.server:
            return
        if (self.server.bereit and self.aufgabe.laeuft
                and not self._server_bereit_gemeldet):
            self._server_bereit_gemeldet = True
            self.status = "OmniVoice gestartet · WebUI läuft"
        elif not self.aufgabe.laeuft and self._server_bereit_gemeldet:
            self.status = self.aufgabe.meldung or "OmniVoice wurde beendet"

    def schleife(self) -> int:
        takt = 1.0 / self.FPS
        sys.stdout.write(ALT_AN + CLEAR + HOME + CURSOR_AUS)
        sys.stdout.flush()
        try:
            with Tastatur() as tastatur:
                while self.laeuft:
                    beginn = time.perf_counter()
                    self.taste(tastatur.taste())
                    self.frame += 1
                    if self.bildschirm == "arbeit" and self.aufgabe.fertig and not self._abschluss_gemeldet:
                        self._abschluss_gemeldet = True
                        self.config = lade_config()
                        self.status = "Fertig – OmniVoice ist einsatzbereit"
                    self.aktualisiere_serverstatus()
                    self.pruefe_rueckkehr()
                    self.zeichne()
                    vergangen = time.perf_counter() - beginn
                    if vergangen < takt:
                        time.sleep(takt - vergangen)
        except KeyboardInterrupt:
            pass
        finally:
            if self.bildschirm == "arbeit" and self.arbeiter and self.aufgabe.laeuft:
                self.arbeiter.stoppen()
            if self.server and self.server.prozess:
                self.server.stoppen()
            sys.stdout.write(CURSOR_AN + ALT_AUS)
            sys.stdout.flush()
        return EXIT_UPDATE_ANWENDEN if self.neustart_angefordert else EXIT_OK


# ------------------------------------------------------------
# Start
# ------------------------------------------------------------

def main() -> int:
    DATEN_DIR.mkdir(parents=True, exist_ok=True)
    PROTOKOLL_DIR.mkdir(parents=True, exist_ok=True)
    raeume_update_nach_neustart_auf()
    if os.name == "nt":
        try:
            ctypes.windll.kernel32.SetConsoleTitleW("OmniVoice Studio · iZE")
        except Exception:
            pass
    setze_fenstergroesse()
    direkt = any(arg.lower() in ("--starten", "--start", "-s") for arg in sys.argv[1:])
    return Studio(direkt_starten=direkt).schleife()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.stdout.write(CURSOR_AN + ALT_AUS)
        sys.stdout.flush()
        import traceback

        traceback.print_exc()
        try:
            PROTOKOLL_DIR.mkdir(parents=True, exist_ok=True)
            with open(PROTOKOLL_DIR / "absturz.log", "a", encoding="utf-8") as datei:
                datei.write(time.strftime("\n=== %Y-%m-%d %H:%M:%S ===\n"))
                traceback.print_exc(file=datei)
        except Exception:
            pass
        print("\nEs ist ein unerwarteter Fehler aufgetreten (siehe oben).")
        input("Zum Schließen ENTER drücken … ")
        sys.exit(1)
