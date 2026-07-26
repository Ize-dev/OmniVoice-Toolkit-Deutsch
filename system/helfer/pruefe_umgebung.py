#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Prueft die fertige Installation INNERHALB der Arbeitsumgebung (venv).

Gibt lesbaren Text fuers Protokoll aus und am Ende eine Zeile

    #ERGEBNIS#{"ok": true, "torch": "2.8.0+cu128", ...}

fuer das OmniVoice Studio.

Rueckgabecode: 0 = brauchbar, 1 = etwas fehlt.
"""

import importlib.util
import json
import sys


def sag(text: str) -> None:
    sys.stdout.write(text + "\n")
    sys.stdout.flush()


def paketversion(name: str) -> str:
    try:
        from importlib import metadata

        return metadata.version(name)
    except Exception:
        return ""


def main() -> int:
    ergebnis = {
        "ok": False, "torch": "", "omnivoice": "", "transformers": "",
        "cuda": False, "xpu": False, "geraet": "", "vram_gb": 0.0, "fehler": "",
    }
    maengel = []

    sag("Pruefe die Installation …")

    # --- PyTorch -------------------------------------------------
    try:
        import torch

        ergebnis["torch"] = torch.__version__
        sag(f"PyTorch {torch.__version__}")
        try:
            if torch.cuda.is_available():
                ergebnis["cuda"] = True
                ergebnis["geraet"] = torch.cuda.get_device_name(0)
                ergebnis["vram_gb"] = round(
                    torch.cuda.get_device_properties(0).total_memory / 1024 ** 3, 1)
                sag(f"CUDA aktiv: {ergebnis['geraet']} mit {ergebnis['vram_gb']} GB "
                    f"(CUDA {torch.version.cuda})")
            elif hasattr(torch, "xpu") and torch.xpu.is_available():
                ergebnis["xpu"] = True
                ergebnis["geraet"] = torch.xpu.get_device_name(0)
                sag(f"Intel XPU aktiv: {ergebnis['geraet']}")
            else:
                sag("Keine GPU-Beschleunigung aktiv - es rechnet der Prozessor.")
        except Exception as fehler:
            sag(f"Hinweis: GPU-Pruefung nicht moeglich ({type(fehler).__name__}: {fehler})")
    except Exception as fehler:
        maengel.append(f"PyTorch laesst sich nicht laden ({type(fehler).__name__})")
        sag(f"FEHLER: PyTorch laesst sich nicht laden: {fehler}")

    # --- OmniVoice ------------------------------------------------
    version = paketversion("omnivoice")
    if version:
        ergebnis["omnivoice"] = version
        sag(f"OmniVoice {version}")
    else:
        maengel.append("Das Paket omnivoice ist nicht installiert")
        sag("FEHLER: Das Paket omnivoice wurde nicht gefunden.")

    if importlib.util.find_spec("omnivoice") is None:
        maengel.append("Die OmniVoice-Programmdateien fehlen")
        sag("FEHLER: Die OmniVoice-Programmdateien wurden nicht gefunden.")

    # --- Zubehoer -------------------------------------------------
    for name in ("transformers", "gradio", "soundfile", "huggingface_hub"):
        version = paketversion(name)
        if version:
            if name == "transformers":
                ergebnis["transformers"] = version
            sag(f"{name} {version}")
        else:
            maengel.append(f"Das Paket {name} fehlt")
            sag(f"FEHLER: Das Paket {name} fehlt.")

    # Nicht zwingend noetig - ohne psutil fehlen nur Werte in der Anzeige.
    version = paketversion("psutil")
    if version:
        sag(f"psutil {version}")
    else:
        sag("Hinweis: psutil fehlt – die Auslastungsanzeige bleibt dann leer.")

    # --- Startbefehl ----------------------------------------------
    try:
        from importlib import metadata

        namen = [e.name for e in metadata.entry_points().select(group="console_scripts")]
        if "omnivoice-demo" in namen:
            sag("Startbefehl omnivoice-demo ist vorhanden.")
        else:
            sag("Hinweis: omnivoice-demo wurde nicht als Startbefehl gefunden - "
                "es wird der direkte Aufruf benutzt.")
    except Exception:
        pass

    ergebnis["ok"] = not maengel
    ergebnis["fehler"] = "; ".join(maengel)
    sag("")
    sag("Ergebnis: " + ("alles vorhanden" if ergebnis["ok"] else "; ".join(maengel)))
    sys.stdout.write("#ERGEBNIS#" + json.dumps(ergebnis, ensure_ascii=False) + "\n")
    sys.stdout.flush()
    return 0 if ergebnis["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
