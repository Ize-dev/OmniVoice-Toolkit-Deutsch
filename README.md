# OmniVoice Studio

> **Deutsche Ein-Klick-Installation für lokale Stimmklonung.**
> Eine Datei anklicken – Python, PyTorch, OmniVoice und das Sprachmodell richten sich von allein ein.
> Alles läuft auf dem eigenen Rechner: keine Cloud, kein Konto, keine Telemetrie.

Von **iZE**. Sprachmodell: [k2-fsa/OmniVoice](https://huggingface.co/k2-fsa/OmniVoice).

---

## Inhalt

**Für Anwender**

- [Was ist das?](#was-ist-das)
- [Voraussetzungen](#voraussetzungen)
- [Loslegen](#loslegen)
- [Die Oberfläche](#die-oberfläche)
- [Stapelbetrieb: ein ganzes Projekt vertonen](#stapelbetrieb-ein-ganzes-projekt-vertonen)
- [Mehrere Arbeiter](#mehrere-arbeiter)
- [Einstellungen](#einstellungen)
- [Wo liegt was?](#wo-liegt-was)
- [Wenn etwas klemmt](#wenn-etwas-klemmt)
- [Wieder loswerden](#wieder-loswerden)

**Technische Notizen**

- [Aufbau](#aufbau)
- [Ablauf der Installation](#ablauf-der-installation)
- [Fenstergröße und Anzeige](#fenstergröße-und-anzeige)
- [Die Web-Oberfläche: Umsetzung](#die-web-oberfläche-umsetzung)
- [Stapelbetrieb: Umsetzung](#stapelbetrieb-umsetzung)
- [Arbeiter: Umsetzung](#arbeiter-umsetzung)
- [Länge aus der Sprachprobe](#länge-aus-der-sprachprobe)
- [Auslastungsanzeige: Umsetzung](#auslastungsanzeige-umsetzung)
- [Benachrichtigung nach dem Stapel](#benachrichtigung-nach-dem-stapel)
- [Sprache der Oberfläche](#sprache-der-oberfläche)
- [Gradio-Fallstricke](#gradio-fallstricke)
- [Bewusste Festlegungen](#bewusste-festlegungen)
- [Neu installieren](#neu-installieren)

---

## Was ist das?

OmniVoice klont Stimmen: Du gibst eine kurze Sprachaufnahme und einen Text vor – heraus kommt
der Text, gesprochen mit dieser Stimme. Das Modell beherrscht über 600 Sprachen, die Vorlage
darf also englisch sein und der Text deutsch.

Dieses Studio nimmt die komplette Einrichtung ab und legt eine deutsche Bedienoberfläche
darüber. Es gibt genau **eine Datei zum Anklicken**: `STARTEN.bat`. Beim ersten Mal richtet
sie alles ein, danach startet sie OmniVoice direkt durch.

```
╔══════════════════════════════════════════════════════════════════════════════════════════════╗
║                         O M N I V O I C E   S T U D I O    ·    iZE                          ║
║     ▅▅▅▄▄▄▃▃▃▃▃▄▄▅▅▆▇▇██████▇▇▆▆▅▅▄▄▃▃▃▃▃▄▄▄▅▅▆▆▆▆▆▆▅▅▄▄▃▃      ║
║ NVIDIA CUDA 12.8 · NVIDIA GeForce RTX 5090   ·   Zustand: noch nicht installiert   ·   00:12 ║
╠══════════════════════════════════════════════════════════════════════════════════════════════╣
║                                      H A U P T M E N Ü                                       ║
║                                                                                              ║
║   ▶ [1]  OMNIVOICE INSTALLIEREN                                                             ║
║          Richtet alles vollautomatisch ein · ca. 7 GB · 15 bis 40 Minuten                    ║
║                                                                                              ║
║     [2]  OMNIVOICE STARTEN                                                                   ║
║          Öffnet die Bedienoberfläche im Browser                                              ║
║                                                                                              ║
║     [3]  SYSTEM PRÜFEN                                                                       ║
║          Grafikkarte, Speicherplatz und Installation testen                                  ║
║                                                                                              ║
║     [4]  REPARIEREN                                                                          ║
║          Bei Problemen: Programm neu aufbauen, Sprachmodell bleibt erhalten                  ║
║                                                                                              ║
║     [5]  HILFE UND INFOS                                                                     ║
║          Was passiert hier? Wo liegt was? Was tun bei Fehlern?                               ║
║                                                                                              ║
║     [0]  BEENDEN                                                                             ║
║                                                                                              ║
║                    Noch nichts installiert. Tipp: Einfach ENTER drücken.                     ║
╠══════════════════════════════════════════════════════════════════════════════════════════════╣
║        ↑↓ auswählen   ·   ENTER öffnen   ·   Zifferntasten direkt   ·   ESC beenden          ║
║                                            Bereit                                            ║
╚══════════════════════════════════════════════════════════════════════════════════════════════╝
```

---

## Voraussetzungen

| | |
|---|---|
| **Betriebssystem** | Windows 10 oder 11 |
| **Python** | 3.10 bis 3.13 – fehlt es, bietet das Studio an, es selbst einzurichten |
| **Speicherplatz** | ungefähr 7 GB (Programm ~3,7 GB, Sprachmodell ~3,3 GB) |
| **Internet** | nur für die Installation |
| **Grafikkarte** | optional. NVIDIA mit Treiber 570+ → CUDA 12.8, Intel Arc → XPU, sonst Prozessor |

Ohne Grafikkarte läuft alles über den Prozessor – funktioniert, ist aber deutlich langsamer.

---

## Loslegen

1. Ordner `toolkit` herunterladen und irgendwohin entpacken
2. **`STARTEN.bat` doppelklicken**
3. Im Menü <kbd>ENTER</kbd> drücken und warten (15 bis 40 Minuten, je nach Leitung)

Ab dem zweiten Mal führt dieselbe Datei direkt ins Menü, in dem »OmniVoice starten« schon
vorgewählt ist – <kbd>ENTER</kbd> genügt.

Ein Abbruch ist ungefährlich: Beim nächsten Start wird dort weitergemacht, wo es aufgehört
hat. Jeder Schritt zeigt Fortschritt, Tempo und Restzeit, dazu eine Gesamtrestzeit, die sich
am tatsächlich gemessenen Download-Tempo nachjustiert.

```
╔══════════════════════════════════════════════════════════════════════════════════════════════╗
║                                      INSTALLATION LÄUFT                                      ║
║                        Schritt 5 von 9: KI-Motor PyTorch installieren                        ║
║                                                                                              ║
║ GESAMT   [██████████▒·······························]  24,8 %   noch ca. 14:43               ║
║ SCHRITT  [▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▒░░░░░░░░░░░░░░░░░░░░░░░░]  42,0 %   noch ca. 06:54               ║
║ DATEN    1,4 GB von 3,4 GB   ·   32,6 MB/s   ·   noch ca. 01:00                              ║
║ DATEI    torch-2.8.0+cu128-cp312-cp312-win_amd64.whl                                         ║
║                                                                                              ║
║   ✔  1. System prüfen                        00:18   Python, Speicherplatz und Internet      ║
║   ✔  2. Arbeitsumgebung anlegen              00:24   abgeschotteter Python-Bereich           ║
║   ✔  3. Paketverwaltung aktualisieren        00:31   pip, setuptools und wheel               ║
║   ✔  4. Grafikkarte erkennen                 00:02   passende Beschleunigung wählen          ║
║   ⠧  5. KI-Motor PyTorch installieren        05:00   der größte Brocken                      ║
║   ·  6. OmniVoice installieren           ca. 01:51   Programm samt Zubehör – ca. 600 MB      ║
║   ·  7. Sprachmodell herunterladen       ca. 04:52   k2-fsa/OmniVoice – ca. 3,3 GB           ║
║   ·  8. Installation testen              ca. 01:00   läuft alles, läuft die Grafikkarte?     ║
║   ·  9. Abschließen                      ca. 00:05   Einstellungen sichern                   ║
║                                                                                              ║
║ LIVE-PROTOKOLL                                    ▲▼ blättern · Zeile 53–60 von 60 · am Ende ║
║ Downloading torch-2.8.0+cu128-cp312-cp312-win_amd64.whl (3461.4 MB)                        │ ║
║ Installing collected packages: mpmath, typing-extensions, sympy, networkx …                █ ║
╚══════════════════════════════════════════════════════════════════════════════════════════════╝
```

---

## Die Oberfläche

Nach der Installation öffnet sich der Browser mit einer deutschen Oberfläche. Drei Reiter:

### 🎤 Stimme klonen

Sprachprobe hochladen oder direkt per Mikrofon aufnehmen, Text eintippen, fertig.
Der Referenztext ist optional – fehlt er, hört OmniVoice die Aufnahme selbst ab.

Zwei Häkchen:

- **Ausgabe genauso lang wie die Sprachprobe** – die Aufnahme bekommt exakt die Länge der
  Vorlage. Gedacht fürs Vertonen, wenn die Zeile ins selbe Zeitfenster passen muss.
- **Ergebnis sofort abspielen** – praktisch, um schnell mehrere Texte durchzuprobieren.

> **Für gute Klone:** 5 bis 15 Sekunden Probe genügen, sauber aufgenommen, ohne Hall,
> ohne Musik im Hintergrund, nur eine sprechende Person.

### 🎲 Überraschung

Ohne Vorgabe – das Modell sucht sich selbst eine Stimme aus. Gut zum schnellen Ausprobieren.

### 📦 Stapel

Ganze Projekte auf einmal. Siehe nächster Abschnitt.

Jede erzeugte Aufnahme landet automatisch als 24-kHz-WAV im Ordner `Ergebnisse`.

---

## Stapelbetrieb: ein ganzes Projekt vertonen

Der Stapel arbeitet eine CSV-Liste ab. Jede Zeile klont die Stimme aus der englischen
Audiodatei und spricht damit den deutschen Text.

### Format der Liste

```csv
englische Audiodatei;englischer Text;deutscher Text
C:\Projekte\habitat\content\audio\wwise\stimme.wav;Hello there, traveler.;Sei gegrüßt, Reisender.
C:\Projekte\habitat\content\audio\wwise\falle.wav;Watch out, it's a trap!;Vorsicht, eine Falle!
```

- Trennzeichen **Semikolon oder Komma** – wird selbst erkannt
- Kopfzeile darf drin sein, wird erkannt und übersprungen
- Kodierung UTF‑8 oder Windows‑1252 (also auch ein Excel-Export)
- Der mittlere Text ist optional. Bei nur zwei Spalten gilt die zweite als deutscher Text.

### Wohin die Dateien kommen

Die Ausgabe **spiegelt den Quellpfad** unterhalb des angegebenen Wurzelordners:

| | |
|---|---|
| Wurzelordner | `C:\Projekte` |
| Quelle | `C:\Projekte\habitat\content\audio\wwise\stimme.wav` |
| **Ziel** | `Ergebnisse\batch\habitat\content\audio\wwise\stimme.wav` |

Der Wurzelordner beantwortet also die Frage *„wo fängt das Projekt an?"*. Bleibt das Feld leer,
wird der gemeinsame Ordner aller Einträge genommen. Liegt eine Datei außerhalb der Wurzel,
landet sie flach unter ihrem Dateinamen.

> **Tipp:** Vor dem Start »Liste prüfen« drücken. Das meldet fehlende Dateien und zeigt einen
> Beispiel-Zielpfad – bevor Stunden ins Leere laufen.

### Während des Laufs

Fortschrittsbalken plus Kennzahlen, die nach jeder Datei aktualisiert werden:

| erledigt | geschafft | vergangen | Restzeit | fertig gegen | Arbeiter | pro Datei | Dateien/Min | Echtzeit | Fehler |
|---|---|---|---|---|---|---|---|---|---|
| 128 / 302 | 42,4 % | 12:41 | 17:23 | 21:15 Uhr | 4 / 4 | 5,9 s | 10,2 | 6,3× | 3 |

Fehlerhafte Zeilen brechen den Stapel **nicht** ab – sie werden gezählt und protokolliert.
Am Ende gibt es auf Wunsch einen CSV-Bericht mit Status je Zeile, dazu Signalton,
Systembenachrichtigung und blinkenden Browser-Tab.

Solange ein Stapel läuft, sind »Liste prüfen« und ein zweiter Start gesperrt.

Mit »Bereits vorhandene Dateien überspringen« setzt ein neuer Lauf genau dort fort,
wo der letzte aufgehört hat.

---

## Mehrere Arbeiter

Ein Arbeiter ist ein eigener OmniVoice-Prozess mit eigenem Modell im Grafikspeicher.
Der Stapel verteilt die Dateien darauf und rechnet dadurch wirklich parallel.

| Einstellung | Was passiert | Grafikspeicher |
|---|---|---|
| **1 Arbeiter** | rechnet im Hauptprozess, eine Datei nach der anderen | keiner zusätzlich |
| **ab 2** | eigene Prozesse, echte Parallelität | rund 3,5 GB je Arbeiter |

Die Oberfläche schlägt anhand des erkannten Grafikspeichers eine Obergrenze vor. Die Arbeiter
starten beim ersten Stapel von selbst und bleiben danach bereit – der nächste Stapel beginnt
also ohne erneutes Modell-Laden. »Arbeiter stoppen« gibt den Speicher wieder frei; beim
Schließen des Studios passiert das ohnehin.

Stirbt ein Arbeiter mitten im Auftrag, wird die betroffene Zeile als Fehler vermerkt und der
Stapel läuft mit den übrigen weiter.

---

## Einstellungen

| Einstellung | Wirkung |
|---|---|
| Arbeiter | Anzahl paralleler OmniVoice-Prozesse für den Stapel |
| Qualitätsstufe | mehr Rechenschritte = besser und langsamer (Vorgabe 32) |
| Sprechtempo | 1,0 ist normal |
| Feste Länge | Ausgabelänge in Sekunden, 0 = automatisch |
| Länge wie Sprachprobe | übernimmt die Länge der Vorlage (hat Vorrang vor »feste Länge«) |
| Auslastung einblenden | kleines Fenster unten rechts: Prozessor, Arbeitsspeicher, Grafikkarte, Grafikspeicher |
| Signalton | kurzer Dreiklang, wenn ein Stapel fertig ist |
| Browser-Benachrichtigung | Systemmeldung, auch wenn das Fenster im Hintergrund liegt |
| Browser-Tab blinken | Reitertitel wechselt, bis das Fenster wieder vorn ist |
| CSV-Bericht | Liste mit Status je Zeile im Ausgabeordner |
| Ergebnis sofort abspielen | spielt frisch erzeugte Aufnahmen automatisch ab |

Alles wird gespeichert und beim nächsten Start wieder eingesetzt.

---

## Wo liegt was?

```
toolkit/
├── STARTEN.bat               ← die einzige Datei zum Anklicken
├── README.md                 ← diese Datei
├── Ergebnisse/               ← alle erzeugten Aufnahmen
│   └── batch/                ← Stapel-Ausgaben, Pfade wie im Projekt
└── system/                   ← Innereien, muss niemand anfassen
```

Das Sprachmodell liegt im üblichen Hugging-Face-Zwischenspeicher
(`%USERPROFILE%\.cache\huggingface\hub`), damit andere Programme es mitbenutzen können.
`HF_HOME` und `HF_HUB_CACHE` werden beachtet.

---

## Wenn etwas klemmt

| Problem | Lösung |
|---|---|
| „Kein Internet" | Verbindung prüfen, Firewall oder VPN kurz aus |
| Download bricht ab | einfach erneut starten, es wird fortgesetzt |
| Alles sehr langsam | ohne NVIDIA-Grafikkarte rechnet der Prozessor – normal, aber zäh |
| CUDA nicht aktiv | NVIDIA-Treiber auf 570 oder neuer aktualisieren, danach »Reparieren« |
| Grafikspeicher voll | Arbeiterzahl senken oder Qualitätsstufe reduzieren |
| Sonstige Fehler | »Reparieren« im Hauptmenü; hilft das nicht, die neueste Datei in `system/daten/protokolle` ansehen |

---

## Wieder loswerden

- Ordner `toolkit` löschen – damit ist das Programm weg
- Für das Sprachmodell zusätzlich `%USERPROFILE%\.cache\huggingface\hub\models--k2-fsa--OmniVoice`
  löschen (die dicksten 3,3 GB)

Am System selbst wird nichts verändert; alles liegt im Ordner.

> **Verschieben statt löschen?** Der Ordner lässt sich nicht einfach woandershin schieben –
> die Python-Umgebung in `system/umgebung` enthält absolute Pfade. Nach einem Umzug einmal
> »Reparieren« wählen, dann stimmt wieder alles.

---
---

# Technische Notizen

Ab hier geht es darum, **wie** die Sachen umgesetzt sind und **warum** so – vor allem die
Stellen, an denen der naheliegende Weg nicht funktioniert.

---

## Aufbau

```
toolkit/
├── STARTEN.bat                 ← die einzige Datei zum Anklicken
├── README.md                   diese Datei
├── Ergebnisse/                 alle erzeugten Aufnahmen (Taste O im Studio)
│   └── batch/                  Stapel-Ausgaben, Pfade wie im Projekt
└── system/
    ├── start.bat               Bootstrap: sucht Python, installiert es notfalls
    ├── omnivoice_toolkit.py    die Konsolenoberfläche (nur Standardbibliothek)
    ├── helfer/
    │   ├── oberflaeche.py      die deutsche Web-Oberfläche  (läuft in der venv)
    │   ├── motor.py            Modell laden, generate(), WAV schreiben
    │   ├── arbeiter.py         ein Arbeiter-Prozess für den Stapelbetrieb
    │   ├── pool.py             Verwaltung der Arbeiter (starten, verteilen, stoppen)
    │   ├── messwerte.py        Auslastung von CPU, RAM, GPU und Grafikspeicher
    │   ├── lade_modell.py      Modell-Download mit Byte-Fortschritt
    │   ├── pruefe_umgebung.py  Abschlusstest der Installation
    │   └── starte_demo.py      Rückfallebene: OmniVoices eigene Oberfläche
    ├── umgebung/               die virtuelle Python-Umgebung (entsteht beim Installieren)
    └── daten/
        ├── installation.json   Zustandsdatei; fehlt sie, gilt alles als nicht installiert
        ├── oberflaeche.json    gespeicherte Einstellungen der Web-Oberfläche
        └── protokolle/         ein Protokoll je Durchlauf
```

Die Konsolenoberfläche läuft mit dem **System-Python** und benutzt ausschließlich die
Standardbibliothek – es muss also nichts vorinstalliert sein außer Python selbst.
Alles Schwere (PyTorch, OmniVoice, Gradio, huggingface_hub) landet in `system/umgebung`
und wird über die Helferskripte angesprochen.

---

## Ablauf der Installation

| # | Schritt | Fortschrittsquelle |
|---|---|---|
| 1 | System prüfen | Python-Version, freier Platz, Socket-Test auf pypi.org |
| 2 | venv anlegen | zeitbasiert |
| 3 | pip aktualisieren | zeitbasiert, danach Versionsabfrage |
| 4 | Grafikkarte erkennen | `nvidia-smi`, sonst `Win32_VideoController` |
| 5 | PyTorch | echte Bytes aus `pip --progress-bar raw` |
| 6 | OmniVoice (+ `hf_xet`, `psutil`) | echte Bytes aus `pip --progress-bar raw` |
| 7 | Sprachmodell | Ordnergröße im HF-Cache gegen Repo-Größe |
| 8 | Test | Import von torch, CUDA-Abfrage, Paketversionen |
| 9 | Abschluss | schreibt `installation.json` |

Gesamt-ETA = Restzeit des laufenden Schritts + Schätzungen der übrigen Schritte.
Die Schätzungen werden nach jedem Download mit dem **gemessenen** Tempo neu berechnet,
deshalb wird die Anzeige mit der Zeit genauer.

Ein eigener Takt-Thread ruft die Fortschrittsberechnung alle 0,5 s auf. Ohne den würde
der Balken während eines minutenlangen Downloads ohne Ausgabezeile einfrieren.

Zwei Stolpersteine, die dabei umgangen werden:

- **`--progress-bar raw` erst nach Versionsprüfung.** pip 21.2 (Beigabe von Python 3.10)
  kennt die Option nicht und bricht mit Fehler ab. Deshalb läuft Schritt 3 ohne sie, danach
  entscheidet die ermittelte pip-Version.
- **`python -m pip` statt `pip.exe`** – letzteres kann sich unter Windows nicht selbst
  aktualisieren.

---

## Fenstergröße und Anzeige

`start.bat` setzt bewusst **kein** `mode con`: Windows Terminal verstellt damit nur den
Puffer, nicht das Fenster – die Anzeige wird dadurch abgeschnitten. Stattdessen fragt
`setze_fenstergroesse()` das Terminal per VT-Sequenz (`CSI 8 ; Zeilen ; Spalten t`) und
benutzt `mode con` nur in der alten Konsole.

Zusätzlich ist die Anzeige anpassungsfähig:

- unter 38 Zeilen entfallen Untertitel und Versionszeile im Kopf
- unter 26 Zeilen zusätzlich die Leerzeilen und die Dateizeile
- die Schrittliste schrumpft auf einen Ausschnitt um den laufenden Schritt (mit ▲/▼)
- das Protokoll behält immer mindestens drei Zeilen

Geprüft von 80×20 bis 150×50: alle Zeilen gleich breit, kein Überlauf.

---

## Die Web-Oberfläche: Umsetzung

`helfer/oberflaeche.py` baut die deutsche Oberfläche mit drei Reitern – **Stimme klonen**
(`ref_audio` + optional `ref_text`), **Überraschung** (ohne Vorgabe) und **Stapel** – plus
einem Reiter für Einstellungen.

Startet sie nicht, etwa weil eine unerwartete Gradio-Fassung installiert ist, beendet sie
sich mit **Rückgabecode 4**. Das Studio wechselt dann automatisch auf `starte_demo.py`, also
OmniVoices eigene Oberfläche – bedienbar bleibt es in jedem Fall. Deren Startpunkt wird über
die Paketinformationen ermittelt statt über eine fest verdrahtete `omnivoice-demo.exe`.

Der freie Netzwerkanschluss wird per Socket-Test ermittelt, und der Browser öffnet erst,
wenn die URL-Zeile in der Ausgabe erscheint – das Laden des Modells dauert beim ersten Start
deutlich länger als eine feste Wartezeit vertragen würde.

Gradio hört ausschließlich auf `127.0.0.1`, Telemetrie ist abgeschaltet.

---

## Stapelbetrieb: Umsetzung

Kodierung wird über UTF‑8, UTF‑8‑BOM, CP1252 und Latin‑1 durchprobiert, das Trennzeichen über
`csv.Sniffer` erkannt. Ohne Wurzelangabe wird `os.path.commonpath` aller Einträge benutzt.
Die Endung des Ziels ist immer `.wav` (24 kHz Mono).

Die Kernlogik (`lies_csv`, `erkenne_wurzel`, `zielpfad`, `stapel_arbeiten`) liegt bewusst
auf Modulebene und ist damit **ohne Browser und ohne Modell testbar**. `stapel_arbeiten` ist
ein Generator und liefert nach jeder fertigen Datei – und mindestens zweimal pro Sekunde –
`(Anzeige, Protokoll, Bericht)`. Daher die Live-Anzeige mit Restzeit, voraussichtlicher
Uhrzeit, Sekunden pro Datei, Dateien pro Minute und Echtzeitfaktor.

Der Bericht wird am Ende in der ursprünglichen Zeilenreihenfolge geschrieben, obwohl die
Ergebnisse bei mehreren Arbeitern durcheinander eintreffen.

### Sperre während eines Laufs

`stapel_durchlauf` ist eine Klammer um `stapel_arbeiten`, die ein `threading.Event` setzt
und im `finally` wieder löscht – auch beim Anhalten mitten im Lauf. Solange es gesetzt ist:

- meldet »Liste prüfen« nur, dass gerade ein Stapel läuft
- blockt ein zweiter Start mit klarer Meldung ab

Der Zustand hängt am Server, gilt also auch für ein zweites Browserfenster. Zusätzlich
werden »Liste prüfen« und »Stapel starten« ausgegraut; freigegeben wird am Ende des Laufs
**und** beim Anhalten, weil die Ereigniskette dort abbricht.

---

## Arbeiter: Umsetzung

Der Stapel verteilt seine Aufträge über einen »Betrieb« – zwei Umsetzungen hinter derselben
Schnittstelle (`freier()`, `sende()`, `antwort()`):

| Einstellung | Umsetzung | Grafikspeicher |
|---|---|---|
| 1 Arbeiter | `LokalerBetrieb` – ein Thread im Hauptprozess | keiner zusätzlich |
| ab 2 | `ArbeiterPool` – je ein `arbeiter.py`-Prozess | ~3,5 GB je Arbeiter |

`arbeiter.py` ist bewusst simpel: JSON-Zeile rein über stdin, JSON-Zeile raus über stdout,
ein Auftrag nach dem anderen. Alles, was **nicht** mit `{` beginnt, gilt als Protokolltext –
PyTorch-Warnungen können den Ablauf also nicht durcheinanderbringen. Modell und
`generate()`-Aufruf kommen für Hauptprozess und Arbeiter aus derselben Datei (`motor.py`),
damit Einzelstück und Stapel garantiert dasselbe tun.

**Robustheit.** Stirbt ein Arbeiter mitten im Auftrag, erkennt der Lesethread das Dateiende,
meldet den offenen Auftrag als Fehler zurück und markiert den Arbeiter als tot – der Stapel
läuft mit den übrigen weiter statt zu hängen. Fallen alle aus, bricht er mit klarer Meldung
ab. Beim Anhalten sammelt ein Hintergrund-Thread die noch laufenden Antworten ein, damit die
Arbeiter danach wieder frei sind.

Der Pool überlebt einen Stapel und wird beim nächsten wiederverwendet (kein erneutes
Modell-Laden). `VERWALTUNG.stoppen()` läuft beim Beenden der Oberfläche in einem `finally`,
damit keine Prozesse Grafikspeicher belegen.

Geprüft mit einer Arbeiter-Attrappe, die dasselbe Protokoll spricht, aber kein Modell lädt:
echte Parallelität (0,7 s statt 2,1 s seriell), Wiederverwendung des Pools über zwei Stapel
und der Absturzfall.

---

## Länge aus der Sprachprobe

Das Häkchen »so lang wie die Sprachprobe« setzt OmniVoices `duration` auf die per
`soundfile.info()` gemessene Länge der Referenzaufnahme. Umgesetzt in
`motor.baue_argumente()`, gilt also für Einzelstück, Hauptprozess-Betrieb und
Arbeiter-Prozesse gleichermaßen.

Eine ausdrücklich gesetzte feste Länge hat Vorrang; ohne Sprachprobe passiert nichts. Kennt
die installierte OmniVoice-Fassung `duration` nicht, wird der Parameter still weggelassen.

---

## Auslastungsanzeige: Umsetzung

`messwerte.py` misst in einem eigenen Thread alle zwei Sekunden: CPU und RAM über `psutil`,
GPU-Last, Grafikspeicher und Temperatur über `nvidia-smi` (Rückfallebene
`torch.cuda.mem_get_info`). Die Oberfläche liest per `gr.Timer` nur den zuletzt gemessenen
Stand – ein hängendes `nvidia-smi` kann die Anzeige also nicht blockieren.

`psutil` kommt zwar ohnehin über `accelerate` mit, wird aber in Schritt 6 **ausdrücklich**
mitinstalliert, damit die Anzeige nicht an einer fremden Abhängigkeit hängt. `nvidia-smi`
gehört zum Grafiktreiber und braucht keine Installation. Fehlt `psutil` trotzdem, bleiben nur
die betroffenen Kacheln leer; ohne NVIDIA-Karte entfallen die GPU-Kacheln.

Das Fenster ist ein `position:fixed`-Kasten unten rechts, sämtliche Farben und Maße stehen
inline (siehe [Gradio-Fallstricke](#gradio-fallstricke)). Ein/Aus in den Einstellungen
schaltet zugleich den Timer ab, damit im Aus-Zustand nichts gemessen und nichts übertragen
wird.

---

## Benachrichtigung nach dem Stapel

Signalton, Systemmeldung und blinkender Reitertitel laufen komplett im Browser: ein `.then()`
am Stapel-Ereignis mit `js=MELDUNG_JS` und **ohne** Python-Funktion. Der Ton wird per WebAudio
als Dreiklang erzeugt – so muss keine Tondatei mitgeliefert werden. Der Text der Meldung ist
die `FERTIG:`-Zeile aus dem Protokoll.

Die Erlaubnis für Benachrichtigungen wird beim Einschalten des Häkchens abgefragt, also
innerhalb einer echten Nutzeraktion – aus einem Hintergrund-Ereignis heraus lehnen Browser
die Abfrage ab.

Das Blinken startet nur, wenn der Tab gerade **nicht** im Vordergrund ist, und endet bei
`focus`, bei `visibilitychange` oder spätestens nach zwei Minuten; der ursprüngliche Titel
wird wiederhergestellt.

---

## Sprache der Oberfläche

Gradio wählt seine Sprache allein über `navigator.language`; eine Einstellung dafür gibt es
nicht. `SPRACHE_HEAD` wird deshalb per `launch(head=…)` in den `<head>` gehängt und
überschreibt `navigator.language`/`languages` auf `de-DE`, **bevor** Gradios Programmteil
startet. Damit ist die mitgelieferte deutsche Übersetzung auch auf einem englischsprachigen
System aktiv.

Zwei Texte sind im Frontend fest verdrahtet und über keine Übersetzung erreichbar:
`processing |` und `queue: n/m |`. Die ersetzt `UEBERSETZUNG_JS` (per `launch(js=…)`) mit
einem MutationObserver im laufenden Betrieb durch »wird berechnet |« und
»Warteschlange: n/m |«. Beide Bausteine sind mit `node --check` und gegen einen DOM-Ersatz
getestet.

---

## Gradio-Fallstricke

Entwickelt und geprüft gegen **Gradio 6.20**:

- Ab Gradio 6 gehören `css` und `theme` an `launch()`, nicht mehr an `Blocks()`. Im
  Konstruktor werden sie stillschweigend ignoriert – das Design wäre spurlos verschwunden.
  `gradio_hauptversion()` entscheidet, wohin sie gehen.
- `show_api` gibt es bei `launch()` nicht mehr. `passende_argumente()` gleicht alle Argumente
  gegen die tatsächliche Signatur ab und lässt Unbekanntes weg, statt an einem `TypeError`
  zu scheitern.
- `show_download_button` (Audio) und `show_copy_button` (Textbox) sind entfallen. Deshalb
  werden **alle** Komponenten über `mach()` gebaut: die Funktion liest den unbekannten
  Parameternamen aus der `TypeError`-Meldung, lässt ihn weg und versucht es erneut. Gleiches
  gilt für `model.generate()` mit `duration`, `speed` und `num_step`.
- Die volle Fensterbreite kommt aus `fill_width=True` plus `max-width: 100%` im CSS –
  sonst zentriert Gradio auf knapp 1200 px.
- **Eingebettetes CSS greift nicht überall.** Der Fortschrittsbalken blieb dadurch farblos.
  Konsequenz: Balken und Auslastungsanzeige tragen Geometrie *und* Farbe inline am Element;
  die CSS-Klasse liefert nur noch die Animation als Zugabe. `var()`-Aufrufe haben feste
  Rückfallwerte.

---

## Bewusste Festlegungen

- PyTorch ist auf `2.8.0+cu128` festgenagelt (nötig für RTX 50xx/Blackwell). Schlägt das
  fehl, wird ohne Versionsangabe erneut versucht, danach CPU.
- NVIDIA-Treiber ab **570** gelten als CUDA-12.8-tauglich, darunter CPU-Modus mit Hinweis
  auf ein Treiber-Update.
- Für Nicht-NVIDIA-Karten gibt es keine DirectML-Variante: OmniVoice kennt nur `cuda`, `mps`
  und `xpu`. Intel Arc läuft über XPU, alles andere ehrlich über den Prozessor.
- Python 3.10 bis 3.13 – darüber gibt es (noch) kein PyTorch-Rad, das wird vor der
  Installation geprüft statt mitten im Download.
- Das Sprachmodell landet im normalen Hugging-Face-Cache
  (`%USERPROFILE%\.cache\huggingface\hub`), damit andere Programme es mitbenutzen können.
  `HF_HOME` bzw. `HF_HUB_CACHE` werden respektiert.
- Der Gerätename ist nirgends fest verdrahtet: er kommt aus `torch.cuda.get_device_name(0)`
  bzw. `torch.xpu.get_device_name(0)`, sonst steht dort »Prozessor (CPU)«.
- Einstellungen liegen in `daten/oberflaeche.json`; der Pfad kommt per `--einstellungen`
  vom Studio.

---

## Neu installieren

`system/daten/installation.json` löschen (dann gilt alles als nicht installiert) oder im Menü
»Reparieren« wählen – das entfernt `system/umgebung` und baut neu auf, ohne das 3,3 GB große
Sprachmodell erneut zu laden.

---
