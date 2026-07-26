#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ein OmniVoice-Arbeiter: eigener Prozess mit eigenem Modell im Grafikspeicher.

Wird vom Stapelbetrieb der Oberflaeche gestartet und ueber die Standardein-
und -ausgabe gesteuert. Ein Auftrag je Zeile, eine Antwort je Zeile:

    ->  {"id": 7, "text": "...", "ref_audio": "...", "ref_text": "...",
         "num_step": 32, "speed": 1.0, "ziel": "C:\\...\\datei.wav"}
    <-  {"typ": "ergebnis", "id": 7, "ok": true, "sekunden": 4.2, "ton": 3.1}

Beim Start meldet der Arbeiter {"typ": "bereit"}, sobald das Modell geladen ist.
Schliesst die Oberflaeche die Standardeingabe, beendet sich der Arbeiter selbst.

Alles, was kein JSON ist, wird von der Oberflaeche als Protokolltext behandelt -
Warnungen von PyTorch stoeren den Ablauf also nicht.
"""

import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from motor import MOTOR, fuehre_auftrag_aus  # noqa: E402


def antworte(**werte) -> None:
    sys.stdout.write(json.dumps(werte, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main() -> int:
    nummer = 0
    for wert in sys.argv[1:]:
        if wert.startswith("--nummer="):
            nummer = int(wert.split("=", 1)[1])

    try:
        MOTOR.laden(still=True)
    except Exception as fehler:
        traceback.print_exc()
        antworte(typ="tot", nummer=nummer, fehler=f"{type(fehler).__name__}: {fehler}")
        return 1

    antworte(typ="bereit", nummer=nummer, geraet=MOTOR.geraetename)

    for zeile in sys.stdin:
        zeile = zeile.strip()
        if not zeile:
            continue
        if zeile == "ENDE":
            break
        try:
            auftrag = json.loads(zeile)
        except ValueError:
            continue
        ergebnis = fuehre_auftrag_aus(auftrag)
        ergebnis["typ"] = "ergebnis"
        ergebnis["nummer"] = nummer
        antworte(**ergebnis)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
