#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Laufende Messwerte des Rechners fuer die kleine Anzeige in der Oberflaeche:
Prozessor, Arbeitsspeicher, Grafikkarte und Grafikspeicher.

Gemessen wird in einem eigenen Thread alle zwei Sekunden. Die Oberflaeche
holt sich nur den zuletzt gemessenen Stand ab - so kostet die Anzeige selbst
nichts und nichts blockiert, auch wenn nvidia-smi mal traege ist.

Ohne NVIDIA-Karte fehlen einfach die GPU-Werte, alles andere laeuft weiter.
"""

import os
import shutil
import subprocess
import threading
import time
from pathlib import Path

KEIN_FENSTER = 0x08000000 if os.name == "nt" else 0
TAKT = 2.0

_werte: dict = {}
_sperre = threading.Lock()
_laeuft = False


# ------------------------------------------------------------
# Quellen
# ------------------------------------------------------------

def finde_nvidia_smi():
    pfad = shutil.which("nvidia-smi")
    if pfad:
        return pfad
    standard = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "nvidia-smi.exe"
    return str(standard) if standard.exists() else None


NVIDIA_SMI = finde_nvidia_smi()


def prozessor_und_speicher() -> dict:
    werte = {}
    try:
        import psutil

        werte["cpu"] = psutil.cpu_percent(interval=None)
        speicher = psutil.virtual_memory()
        werte["ram_prozent"] = speicher.percent
        werte["ram_benutzt"] = speicher.used / 1024 ** 3
        werte["ram_gesamt"] = speicher.total / 1024 ** 3
    except Exception:
        pass
    return werte


def grafikkarte() -> dict:
    werte = {}
    if NVIDIA_SMI:
        try:
            ergebnis = subprocess.run(
                [NVIDIA_SMI, "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu",
                 "--format=csv,noheader,nounits"],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                creationflags=KEIN_FENSTER, timeout=8,
            )
            zeile = ergebnis.stdout.decode("utf-8", "replace").strip().splitlines()
            if ergebnis.returncode == 0 and zeile:
                teile = [t.strip() for t in zeile[0].split(",")]
                werte["gpu"] = float(teile[0])
                werte["vram_benutzt"] = float(teile[1]) / 1024.0
                werte["vram_gesamt"] = float(teile[2]) / 1024.0
                werte["vram_prozent"] = (werte["vram_benutzt"] / werte["vram_gesamt"] * 100.0
                                         if werte["vram_gesamt"] else 0.0)
                if len(teile) > 3 and teile[3].isdigit():
                    werte["temperatur"] = float(teile[3])
                return werte
        except Exception:
            pass
    # Rueckfallebene: wenigstens der Grafikspeicher ueber PyTorch
    try:
        import torch

        if torch.cuda.is_available():
            frei, gesamt = torch.cuda.mem_get_info()
            werte["vram_benutzt"] = (gesamt - frei) / 1024 ** 3
            werte["vram_gesamt"] = gesamt / 1024 ** 3
            werte["vram_prozent"] = (gesamt - frei) / gesamt * 100.0
    except Exception:
        pass
    return werte


def _messen() -> None:
    while True:
        werte = {"zeit": time.time()}
        werte.update(prozessor_und_speicher())
        werte.update(grafikkarte())
        with _sperre:
            _werte.clear()
            _werte.update(werte)
        time.sleep(TAKT)


def starten() -> None:
    """Startet den Messthread einmalig."""
    global _laeuft
    if _laeuft:
        return
    _laeuft = True
    try:
        import psutil

        psutil.cpu_percent(interval=None)     # ersten Aufruf verwerfen
    except Exception:
        pass
    threading.Thread(target=_messen, daemon=True).start()


def hole() -> dict:
    with _sperre:
        return dict(_werte)


# ------------------------------------------------------------
# Anzeige
# ------------------------------------------------------------

def _balken(prozent: float, farbe: str) -> str:
    prozent = max(0.0, min(100.0, float(prozent)))
    return (
        "<div style='height:5px;border-radius:3px;background:rgba(255,255,255,.10);"
        "overflow:hidden;margin-top:4px'>"
        f"<div style='height:100%;width:{prozent:.1f}%;border-radius:3px;background:{farbe};"
        f"box-shadow:0 0 8px {farbe}88'></div></div>"
    )


def _kachel(titel: str, wert: str, prozent, farbe: str, zusatz: str = "") -> str:
    balken = _balken(prozent, farbe) if prozent is not None else ""
    return (
        "<div style='flex:1 1 84px;min-width:84px'>"
        f"<div style='font-size:10px;letter-spacing:.10em;opacity:.55'>{titel}</div>"
        f"<div style='font-size:15px;font-weight:800;color:#eaf2ff;line-height:1.3'>{wert}</div>"
        f"{balken}"
        + (f"<div style='font-size:10px;opacity:.45;margin-top:3px'>{zusatz}</div>" if zusatz else "")
        + "</div>"
    )


def monitor_html(geraetename: str = "", sichtbar: bool = True) -> str:
    """Kleines, schwebendes Fenster unten rechts mit den aktuellen Werten."""
    if not sichtbar:
        return ""
    werte = hole()
    if not werte:
        starten()
        werte = hole()

    kacheln = []
    if "cpu" in werte:
        kacheln.append(_kachel("PROZESSOR", f"{werte['cpu']:.0f} %".replace(".", ","),
                               werte["cpu"], "#ff4fd8"))
    if "ram_prozent" in werte:
        kacheln.append(_kachel(
            "ARBEITSSPEICHER", f"{werte['ram_prozent']:.0f} %".replace(".", ","),
            werte["ram_prozent"], "#4d9bff",
            f"{werte['ram_benutzt']:.1f} von {werte['ram_gesamt']:.0f} GB".replace(".", ",")))
    if "gpu" in werte:
        zusatz = f"{werte['temperatur']:.0f} °C" if "temperatur" in werte else ""
        kacheln.append(_kachel("GRAFIKKARTE", f"{werte['gpu']:.0f} %".replace(".", ","),
                               werte["gpu"], "#22e0ff", zusatz))
    if "vram_prozent" in werte:
        kacheln.append(_kachel(
            "GRAFIKSPEICHER", f"{werte['vram_prozent']:.0f} %".replace(".", ","),
            werte["vram_prozent"], "#46e08a",
            f"{werte['vram_benutzt']:.1f} von {werte['vram_gesamt']:.0f} GB".replace(".", ",")))

    if not kacheln:
        kacheln.append(_kachel("MESSWERTE", "–", None, "#888", "nicht verfügbar"))

    name = geraetename or "dieser Rechner"
    return (
        "<div id='ize-monitor' style=\"position:fixed;right:16px;bottom:16px;z-index:950;"
        "width:min(430px,44vw);padding:11px 14px 12px 14px;border-radius:13px;"
        "border:1px solid rgba(34,224,255,.30);"
        "background:rgba(11,13,21,.93);backdrop-filter:blur(7px);"
        "box-shadow:0 8px 30px rgba(0,0,0,.55),0 0 22px rgba(77,155,255,.18);"
        "font-family:system-ui,-apple-system,Segoe UI,sans-serif;color:#dbe3f4\">"
        "<div style='display:flex;justify-content:space-between;align-items:baseline;"
        "margin-bottom:8px'>"
        "<span style='font-size:10.5px;font-weight:800;letter-spacing:.20em;color:#4d9bff'>"
        "AUSLASTUNG</span>"
        f"<span style='font-size:10px;opacity:.45;overflow:hidden;text-overflow:ellipsis;"
        f"white-space:nowrap;max-width:60%'>{name}</span></div>"
        "<div style='display:flex;gap:12px;flex-wrap:wrap'>" + "".join(kacheln) + "</div></div>"
    )
