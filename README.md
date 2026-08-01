# OmniVoice Studio

> **Deutsche Ein-Klick-Installation für lokale Stimmklonung.**
> Eine Datei anklicken – Python, PyTorch, OmniVoice, Faster-Whisper und die Standardmodelle
> richten sich von allein ein.
> Alles rechnet auf dem eigenen Rechner: keine Audio-Cloud, keine Telemetrie.

Von **iZE**. Sprachmodell: [k2-fsa/OmniVoice](https://huggingface.co/k2-fsa/OmniVoice).

---

## Inhalt

**Für Anwender**

- [Was ist das?](#was-ist-das)
- [Voraussetzungen](#voraussetzungen)
- [Loslegen](#loslegen)
- [Die Oberfläche](#die-oberfläche)
- [Lange Szenen und Cutscenes](#lange-szenen-und-cutscenes)
- [CSV-Listen aus Audioordnern erzeugen](#csv-listen-aus-audioordnern-erzeugen)
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
- [Länge und Klang](#länge-und-klang)
- [Erweiterte Ansicht: Umsetzung](#erweiterte-ansicht-umsetzung)
- [Szenen-Editor: Umsetzung](#szenen-editor-umsetzung)
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
║     ▅▅▅▄▄▄▃▃▃▃▃▄▄▅▅▆▇▇██████▇▇▆▆▅▅▄▄▃▃▃▃▃▄▄▄▅▅▆▆▆▆▆▆▅▅▄▄▃▃▂▂▂▂   ║
║ NVIDIA CUDA 12.8 · NVIDIA GeForce RTX 5090   ·   Zustand: noch nicht installiert   ·   00:12 ║
╠══════════════════════════════════════════════════════════════════════════════════════════════╣
║                                      H A U P T M E N Ü                                       ║
║                                                                                              ║
║   ▶ [1]  OMNIVOICE INSTALLIEREN                                                             ║
║          Richtet alles vollautomatisch ein · ca. 12–16 GB · 20 bis 60 Minuten                ║
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
║     [5]  NACH UPDATES SUCHEN                                                                 ║
║          Programmversion mit GitHub vergleichen                                              ║
║                                                                                              ║
║     [6]  HILFE UND INFOS                                                                     ║
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
| **Python** | 3.10 bis 3.13 – fehlt eine passende Version, richtet das Studio Python 3.12 zusätzlich ein; vorhandenes Python 3.14+ bleibt unberührt |
| **Speicherplatz** | ungefähr 12 bis 16 GB inklusive OmniVoice, Whisper, Pyannote und Demucs; zur Installation sollten mindestens 22 GB frei sein |
| **Internet** | nur für Installation und Updateprüfung |
| **Grafikkarte** | optional. NVIDIA mit Treiber 570+ → CUDA 12.8, Intel Arc → XPU, sonst Prozessor |

Ohne Grafikkarte läuft alles über den Prozessor – funktioniert, ist aber deutlich langsamer.

---

## Loslegen

1. Ordner `toolkit` herunterladen und irgendwohin entpacken
2. **`STARTEN.bat` doppelklicken**
3. Im Menü <kbd>ENTER</kbd> drücken und warten (20 bis 60 Minuten, je nach Leitung und Gerät)

Ab dem zweiten Mal führt dieselbe Datei direkt ins Menü, in dem »OmniVoice starten« schon
vorgewählt ist – <kbd>ENTER</kbd> genügt.

Bei einer bestehenden Installation ohne Faster-Whisper oder Cutscene-Werkzeuge wird einmalig
**„Sprach- und Cutscene-Werkzeuge ergänzen“** vorgewählt. Dieser Ergänzungslauf fasst die
vorhandene OmniVoice-/PyTorch-Umgebung nicht an und richtet die getrennten Whisper- und
Szenen-Umgebungen ein.

Ein Abbruch ist ungefährlich: Beim nächsten Start wird dort weitergemacht, wo es aufgehört
hat. Jeder Schritt zeigt Fortschritt, Tempo und Restzeit, dazu eine Gesamtrestzeit, die sich
am tatsächlich gemessenen Download-Tempo nachjustiert.

```
╔══════════════════════════════════════════════════════════════════════════════════════════════╗
║                                      INSTALLATION LÄUFT                                      ║
║                        Schritt 5 von 12: KI-Motor PyTorch installieren                       ║
║                                                                                              ║
║ GESAMT   [██████████▒·······························]  24,8 %   noch ca. 14:43               ║
║ SCHRITT  [▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▒░░░░░░░░░░░░░░░░░░░░░░░░]  42,0 %   noch ca. 06:54               ║
║ DATEN    1,4 GB von 3,4 GB   ·   32,6 MB/s   ·   noch ca. 01:00                              ║
║ DATEI    torch-2.8.0+cu128-cp312-cp312-win_amd64.whl                                         ║
║                                                                                              ║
║   ✔  1. System prüfen                        00:18   Python, Speicherplatz und Internet     ║
║   ✔  2. Arbeitsumgebung anlegen              00:24   abgeschotteter Python-Bereich          ║
║   ✔  3. Paketverwaltung aktualisieren        00:31   pip, setuptools und wheel              ║
║   ✔  4. Grafikkarte erkennen                 00:02   passende Beschleunigung wählen         ║
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

<a>
  <img
    src="Bilder/UI.png"
    alt="OmniVoice Toolkit Deutsch"
    width="700"
  >
</a>

Nach der Installation öffnet sich der Browser mit einer deutschen Oberfläche.

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

## Lange Szenen und Cutscenes

Für lange Aufnahmen – Cutscenes, Dialogszenen, alles über ein paar Sekunden – gibt es den
**Szenen-Editor**. Er ist kein eigener Reiter, sondern öffnet sich als Vollbildfenster über
dem Stapel-Reiter: entweder oben über **🎬 Szenen-Editor öffnen** oder direkt aus einer Zeile
der erweiterten Liste über **🎬 Szene**. Steht in einer Zeile schon eine begonnene Szene,
zeigt die Liste ein 🎬 vor dem Dateinamen und der Knopf heißt **🎬 Szene ›**.

Der Editor zeigt zwei Spuren mit gemeinsamer Zeitachse: oben das englische Original, unten
die deutsche Spur, die dabei entsteht.

**Der Arbeitsablauf**

1. Aufnahme laden (Pfad eintippen oder aus der Liste heraus öffnen).
2. Optional **✨ Automatisch vorbefüllen**: Whisper hört sich die Szene an und legt für jeden
   Sprechabschnitt ein Segment mit Zeiten und englischem Text an. Der deutsche Text bleibt
   leer – übersetzt wird nichts.
3. Einen Bereich mit der Maus ziehen, dann **Rechtsklick**:
   - **🎤 Text sprechen lassen** – ein Textfeld erscheint direkt an der Maus. OmniVoice nimmt
     genau diesen Bereich als Stimmvorlage und erzeugt die Aufnahme mit exakt dieser Länge.
   - **⧉ Original übernehmen** – der englische Abschnitt wandert unverändert in die deutsche
     Spur (für Schreie, Gelächter, Atmer).
   - **♪ Auswahl anhören** (Englisch oder Deutsch) – der Abspielkopf springt an den Anfang der
     Auswahl und läuft von dort normal weiter.
4. Fertige Segmente lassen sich per Rechtsklick oder über die Segmentliste weiterbearbeiten:
   Text ändern, neu erzeugen, stumm schalten, löschen, durch das Original ersetzen.

**Segmente bearbeiten**

- **Größe ändern:** ein ausgewähltes Segment hat links und rechts einen Ziehgriff.
- **Verschieben:** Segment anklicken (wählt aus), dann ein zweites Mal anfassen und ziehen.
  Bleibt die Länge gleich, bleibt die Aufnahme gültig – nur die Position ändert sich.
- **✂ Teilen:** oben auf die Zeitachse klicken, damit der Cursor mitten im Segment steht, dann
  **✂** in der Segmentliste oder im Rechtsklickmenü. Beide Hälften behalten ihren Ton, sodass
  sich einzelne Teile anschließend löschen lassen.

**Abspielen und Abspielmarke**

▶ Englisch, ▶ Deutsch oder ▶ Beides spielen ab der Marke. Die zuletzt gewählte Spur ist am
Knopf grün markiert, und die **Leertaste** nimmt genau diese wieder – startet und stoppt also
das, womit du gerade arbeitest, nicht immer beide Spuren gleichzeitig.

Die Marke lässt sich auf drei Wegen setzen:

- **Klick auf die Zeitachse** oben. Läuft gerade etwas, geht es sofort ab dieser Stelle weiter.
- **Gedrückt halten und ziehen** auf der Zeitachse – die Marke folgt der Maus, gehört wird
  erst beim Loslassen.
- **← und →** für die Feinarbeit: 50 ms je Druck, mit **Strg** 10 ms, mit **Umschalt** eine
  halbe Sekunde. Läuft gerade etwas, setzt die Wiedergabe kurz nach dem letzten Tastendruck
  an der neuen Stelle wieder ein.

**Esc** schließt das Fenster. Jede Spur lässt sich einzeln stumm schalten.

**Speichern**

**💾 In den Stapel übernehmen** (oben in der Kopfzeile) beziehungsweise **💾 Deutsche Spur
speichern** (unten) mischen alle nicht stummen Segmente zu einer Datei. Beide Knöpfe tun
dasselbe; der obere ist immer sichtbar, auch wenn das Fenster klein ist. Bleibt das Zielfeld
leer, landet die Datei genau dort, wo der Stapel sie erwartet – die zugehörige Zeile in der
Liste springt danach automatisch auf **fertig** um.

Der Zwischenstand wird **nach jeder Änderung automatisch gesichert**, in einem eigenen Ordner
je Quelldatei unter `Ergebnisse\szenen`. Wird dieselbe Aufnahme später erneut geladen, ist die
Arbeit vollständig wieder da. **Projekt sichern / laden** legt zusätzlich eine Kopie an einer
frei gewählten Stelle ab.

### 🧾 Liste erzeugen

Zeigt auf einen Ordner mit englischen Audiodateien und nimmt je eine englische und deutsche
Lookup-Liste entgegen. Faster-Whisper transkribiert die Audios, sucht den ähnlichsten
englischen Text und übernimmt über dessen ID den deutschen Text. Fortschritt und Restzeit
laufen live mit. Die fertige Semikolon-CSV wird automatisch in den Stapel-Tab übernommen.

Die Listen dürfen beispielsweise `identifier=text`, CSV/TSV, JSON oder ein eigenes Format
haben. Aufbau, Trennzeichen, ID-/Textspalte und regulärer Ausdruck sind für Englisch und
Deutsch getrennt konfigurierbar.

### 📦 Stapel

<a>
  <img
    src="Bilder/Stapel.png"
    alt="OmniVoice Toolkit Deutsch Stapelmodus"
    width="700"
  >
</a>

Ganze Projekte auf einmal. Siehe nächster Abschnitt.

Optional transkribiert Faster-Whisper jede fertige deutsche Aufnahme und vergleicht sie mit
dem verlangten Text. Das Rating erscheint in Prozent in Bericht und erweiterter Tabelle.
Ratings lassen sich filtern sowie auf- und absteigend sortieren.

In der erweiterten Tabelle öffnet **„✎ Text“** einen Editor für die jeweilige Zeile.
Englische und deutsche Lookup-Liste können dort durchsucht werden. Ein ausgewählter Treffer
übernimmt automatisch das zusammengehörige Sprachpaar; beide Texte lassen sich anschließend
weiterhin frei überschreiben. Die Änderung wird direkt in der aktiven CSV gespeichert.

Jede erzeugte Aufnahme landet automatisch als 24-kHz-WAV im Ordner `Ergebnisse`.

---

## CSV-Listen aus Audioordnern erzeugen

Aus etwa `C:\modding\elden ring\audios\10\10.wav` wird eine Zeile wie:

```csv
C:\modding\elden ring\audios\10\10.wav;This is the English text.;Das ist der deutsche Text.
```

Der Ablauf je Audiodatei:

1. Faster-Whisper transkribiert die englische Aufnahme.
2. Fuzzy Matching sucht den ähnlichsten Eintrag in der englischen Lookup-Liste.
3. Dessen Identifier sucht den passenden Eintrag in der deutschen Lookup-Liste.
4. Der absolute Audiopfad und beide Lookup-Texte werden als Semikolon-CSV gespeichert.

Standard ist das Whisper-Modell `medium`. Unter **Einstellungen** kann später ein anderes
Modell sowie **Automatisch**, **CPU/INT8** oder **NVIDIA CUDA/FP16** gewählt werden. Ein noch
nicht vorhandenes Modell lädt Faster-Whisper beim ersten Einsatz in den Modell-Cache.
Automatisch versucht CUDA und fällt bei einer ungeeigneten GPU-, Treiber- oder
Bibliothekskonstellation auf CPU/INT8 zurück.

Im Listengenerator sind **1 bis 8 Whisper-Arbeiter** einstellbar. Jeder davon ist ein eigener
Prozess mit einem eigenen Modell im RAM beziehungsweise VRAM; `1` ist deshalb die sichere
Voreinstellung. Zusätzliche Arbeiter werden nach der fertigen CSV automatisch beendet.
Schlägt die Transkription einer einzelnen Datei fehl, bleibt deren absoluter Pfad mit leeren
Textspalten in der CSV erhalten, statt unbemerkt aus der Liste zu verschwinden.

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

Mit **„Mit Whisper prüfen“** folgt nach der Erzeugung ein Qualitätslauf. Der erkannte Text
und das Rating stehen im CSV-Bericht; in der erweiterten Ansicht zeigt ein farbiger
Prozentwert das Ergebnis. Die Bewertung wird anhand Dateigröße, Änderungszeit und Solltext
zwischengespeichert und nur neu berechnet, wenn sich wirklich etwas geändert hat.
Der Stapel verwendet dafür unabhängig von der Listengenerator-Einstellung höchstens einen
Whisper-Arbeiter; bei ausgeschalteter Prüfung wird keiner gestartet. Die Tabellenknöpfe
**„erzeugen“** und **„neu“** bewerten ihre einzelne Ausgabe dagegen immer unmittelbar.

Solange ein Stapel läuft, sind »Liste prüfen« und ein zweiter Start gesperrt.

Mit »Bereits vorhandene Dateien überspringen« setzt ein neuer Lauf genau dort fort,
wo der letzte aufgehört hat. Ausgeschaltet ist es der Überschreibmodus: Dann wird
alles neu erzeugt, auch was schon da ist.

### Klangbearbeitung

Gilt für den Stapel **und** für einzelne Zeilen aus der Tabelle:

| Einstellung | Wirkung |
|---|---|
| **Versatz zur Länge** | −5 bis +5 Sekunden auf die Länge der Vorlage. Nur zusammen mit »so lang wie die Aufnahme«. Minus = knapper, Plus = mehr Luft. |
| **So lang wie das Original** | Die Ausgabe bekommt **exakt** die Länge der Vorlage (plus Versatz). Zu lang Erzeugtes wird sauber abgeschnitten, zu kurzes mit Stille aufgefüllt – wie viel korrigiert wurde, steht im Protokoll. |
| **Stille am Anfang entfernen** | schneidet die Ruhe vor dem ersten Wort weg (Schwelle −45 dB, 30 ms Vorlauf bleiben) |
| **Lautstärke anpassen** | »feste Verstärkung« in Dezibel oder »an das Original angleichen« – letzteres bringt die Aufnahme auf die Lautheit der englischen Vorlage. Übersteuerung wird in beiden Fällen abgefangen. |

### Alle Zeilen im Überblick

Steht direkt unter der Fortschrittsanzeige – vor dem Protokoll, das eingeklappt
ganz unten sitzt. Jede Zeile der Liste mit **beiden Wellenformen**, beiden Texten,
beiden Dauern, der Abweichung und einem Knopf zum einzelnen Neuerzeugen:

| # | Datei | Englisch | Deutsch | Status | |
|---|---|---|---|---|---|
| 2 | `trap_warning.wav` | ▁▃█▇▂ 1,80 s · „Watch out, it's a trap!" | ▂▇█▅▃ 3,10 s · „Vorsicht, das ist eine Falle …" | **länger** +1,30 s | ↻ neu |

Darüber ein Zählwerk über den **gesamten** Bestand: Zeilen, erzeugt, noch offen,
deutsch länger, deutsch kürzer, fehlende Dateien, ohne Text und die Gesamtspielzeit
beider Sprachen.

**Anhören:** Ein Klick auf eine Wellenform spielt die Datei ab – und zwar **genau
ab der angeklickten Stelle**. Die laufende Spur ist blau umrandet. Das gilt für die
englische Vorlage wie für das deutsche Ergebnis.

Lange englische Originale – mehrkanalige 48-kHz-Aufnahmen von mehreren Minuten – werden
nicht am Stück in den Browser geschoben, sondern in Minutenabschnitten geliefert, die
automatisch aneinanderhängen. Für dich ändert sich nichts: klicken, hören, es läuft durch.

**Endlos blättern:** Die Liste hat keine Seiten. Beim Scrollen werden automatisch
weitere Zeilen nachgeladen, bis alles da ist.

**Filter**

- Freitextsuche über deutschen Text, englischen Text oder Dateinamen – wahlweise
  alles auf einmal. Mit `*` und `?` als Platzhalter, sonst wird automatisch überall
  im Text gesucht.
- Zustand: noch offen · fertig · deutsch länger · deutsch kürzer ·
  englische Datei fehlt · ohne deutschen Text
- Sortierung nach Zeile, Dateiname und Abweichung sowie – jeweils auf- und absteigend –
  nach englischer Dauer, deutscher Dauer und Whisper-Rating. Beim aufsteigenden Sortieren
  nach Dauer stehen Zeilen ohne Datei hinten statt vorne; eine Dauer von 0 wäre sonst
  immer der erste Treffer

**Texte neu zuordnen oder überschreiben:** **„✎ Text“** öffnet den Zeileneditor. Eine Suche
in der englischen oder deutschen Lookup-Liste zeigt passende Einträge; ein Klick übernimmt
automatisch beide Sprachen aus demselben Lookup-Paar. Für Sonderfälle können Englisch und
Deutsch auch unabhängig manuell geändert werden. Speichern aktualisiert die aktive CSV und
setzt ein altes Whisper-Rating zurück, weil es nicht mehr zum neuen Solltext gehört.
Englisches Original und bereits erzeugtes deutsches Ergebnis lassen sich direkt im
zentrierten Editor abspielen, ohne das Fenster wieder schließen zu müssen.

**Einzelne Zeile neu erzeugen:** Knopf in der Zeile drücken. Es gelten dieselben
Einstellungen wie für den Stapel; danach werden Dauer, Wellenform und Status der
Zeile sofort aktualisiert. Auf Wunsch wird das Ergebnis gleich abgespielt.

**Nur die gefilterten Zeilen erzeugen:** Der Knopf »⚡ Gefilterte erzeugen« schickt
genau das, was gerade im Filter steht, durch den Stapelbetrieb – mit derselben
Fortschrittsanzeige, denselben Arbeitern und demselben Bericht. So lassen sich
gezielt „alle zu langen" oder „alle noch offenen" nacharbeiten.

**Fehlende englische Texte nachtragen:** »🎧 Englische Texte per Whisper« läuft über alle
gefilterten Zeilen, bei denen die zweite Spalte leer ist, transkribiert deren Aufnahme und
schreibt das Ergebnis in die aktive CSV. OmniVoice hört die Vorlage sonst bei jedem Lauf
selbst ab – steht der Text erst einmal in der Liste, ist das Ergebnis stabiler und außerdem
les- und korrigierbar.

**Im Szenen-Editor öffnen:** »🎬 Szene« lädt die englische Aufnahme dieser Zeile in den
[Szenen-Editor](#lange-szenen-und-cutscenes). Ein 🎬 vor dem Dateinamen zeigt, dass dazu
bereits eine Szene angefangen wurde.

Während ein Stapel läuft, sind Einzelerzeugung, Prüfen und Starten gesperrt.

### Projektstand

Ganz oben im Stapel-Reiter steht eine **Projektdatei**. »💾 Projekt speichern« schreibt Liste,
Projektstart, Ausgabeordner und sämtliche Erzeugungs- und Klangeinstellungen in eine
`.omniprojekt.json`; »📂 Projekt laden« setzt alles wieder ein. Beim nächsten Start ist der
zuletzt benutzte Pfad schon eingetragen.

Die Datei enthält nur Pfade und Einstellungen, keine Audiodaten. Angefangene Szenen bleiben in
ihren eigenen Ordnern unter `Ergebnisse\szenen` und werden im Projekt nur mitgeführt.

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
| Versatz, Stille, Lautstärke | siehe [Klangbearbeitung](#klangbearbeitung) |
| Zeilen je Seite | Seitengröße der erweiterten Ansicht |
| Globale Textersetzungen | eine Regel je Zeile im Format `Suchen => Ersetzen`; gilt vor jeder Einzel- und Stapelerzeugung |
| Oberflächen-Theme | Alphabetisch sortiert: `Crimson`, `Darkmore`, `Default`, `Dracula`, `Fallout`, `Flashbang`, `Hyrule`, `Nordic`, `Pixel`, `Retro` oder `Scene`; wechselt sofort und wird automatisch gespeichert |

Bei Textersetzungen bedeutet eine leere rechte Seite oder `""`, dass der Suchtext entfernt
wird. Die Schreibweisen `\r`, `\n` und `\t` stehen für Wagenrücklauf, Zeilenumbruch und
Tabulator. Beispielsweise entfernt `\n => ""` Zeilenumbrüche, während
`ehrgeiz => ehrgeitz` nur die Aussprache-Eingabe für das Sprachmodell anpasst. CSV und
angezeigter Originaltext bleiben dabei unverändert.

Alles wird gespeichert und beim nächsten Start wieder eingesetzt.

---

## Wo liegt was?

```
toolkit/
├── STARTEN.bat               ← die einzige Datei zum Anklicken
├── VERSION                   ← lokale Programmversion für den GitHub-Abgleich
├── README.md                 ← diese Datei
├── Ergebnisse/               ← alle erzeugten Aufnahmen
│   └── batch/                ← Stapel-Ausgaben, Pfade wie im Projekt
└── system/                   ← Innereien, muss niemand anfassen
```

Das Sprachmodell liegt im üblichen Hugging-Face-Zwischenspeicher
(`%USERPROFILE%\.cache\huggingface\hub`), damit andere Programme es mitbenutzen können.
`HF_HOME` und `HF_HUB_CACHE` werden beachtet.

---

## Programm-Updates

Beim Start prüft die Kommandozeilen-Oberfläche im Hintergrund die Datei `VERSION` auf
GitHub. Im Hauptmenü steht danach, ob die installierte Version aktuell ist. Ist eine
neuere Version verfügbar, wird Menüpunkt `[5]` zum Update-Knopf.

Das Update lädt den aktuellen Stand von `main`, prüft Versionsnummer und Dateipfade,
sichert die vorhandenen Programmdateien und startet das Studio danach neu. Nicht
angetastet werden:

- `Ergebnisse/`
- `system/daten/` mit Einstellungen und Protokollen
- `system/umgebung/` mit der installierten Python-Umgebung
- `system/whisper-umgebung/` mit der getrennten Faster-Whisper-Umgebung
- `system/szenen-umgebung/` mit Pyannote, Demucs und ihrem getrennten PyTorch

Für eine neue Veröffentlichung muss die Versionsnummer in `VERSION` erhöht und zusammen
mit den Änderungen auf GitHub gepusht werden.

---

## Wenn etwas klemmt

| Problem | Lösung |
|---|---|
| „Kein Internet" | Verbindung prüfen, Firewall oder VPN kurz aus |
| Download bricht ab | einfach erneut starten, es wird fortgesetzt |
| Alles sehr langsam | ohne NVIDIA-Grafikkarte rechnet der Prozessor – normal, aber zäh |
| CUDA nicht aktiv | NVIDIA-Treiber auf 570 oder neuer aktualisieren, danach »Reparieren« |
| Grafikspeicher voll | Arbeiterzahl senken oder Qualitätsstufe reduzieren |
| Whisper meldet `progress-bar: invalid choice: raw` | aktuelle Toolkit-Version verwenden und Installation erneut starten; die unvollständige Whisper-Umgebung wird sicher weiterverwendet |
| OGG wird als „Invalid file type“ abgelehnt | aktuelle Toolkit-Version verwenden; `.ogg`, `.oga` und `.opus` werden unabhängig vom Windows-MIME-Mapping erkannt |
| Nur Python 3.14 oder neuer installiert | aktuelle Toolkit-Version starten und die angebotene Python-3.12-Installation bestätigen; beide Versionen können parallel bleiben |
| Szenen-Editor lässt sich nicht teilen (»Cursor mitten ins Segment setzen«) | zuerst oben auf die Zeitachse klicken – der grüne Abspielkopf muss innerhalb des Segments stehen, mit mindestens 0,15 s Abstand zu beiden Rändern |
| Segment lässt sich nicht verschieben | einmal anklicken wählt nur aus; erst beim zweiten Anfassen wird gezogen. An den Rändern sitzen die Griffe zum Ändern der Länge |
| Gespeicherte Szene taucht im Stapel nicht als fertig auf | das Zielfeld im Editor leer lassen, dann landet die Spur automatisch dort, wo der Stapel sie erwartet. Sonst hilft »🔄 Auffrischen« über der Liste |
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
    │   ├── tabelle.py          erweiterte Ansicht: Modell, Filter, Wellenformen
    │   ├── listengenerator.py  Lookup-Parser, Audio-Suche, Fuzzy-Zuordnung, CSV
    │   ├── whisper_dienst.py   langlebiger Whisper-Prozess und Rating-Speicher
    │   ├── whisper_worker.py   Transkription in der getrennten Umgebung
    │   ├── szenen_editor.py    Szenen-Editor: Segmente, Schnitt, Mischung, Autosicherung
    │   ├── szenen_editor_html.py  dessen Aussehen und Bedienung (Leinwand, Menüs)
    │   ├── projekt.py          Projektdatei des Stapels (Pfade und Einstellungen)
    │   ├── messwerte.py        Auslastung von CPU, RAM, GPU und Grafikspeicher
    │   ├── lade_modell.py      Modell-Download mit Byte-Fortschritt
    │   ├── pruefe_umgebung.py  Abschlusstest der Installation
    │   └── starte_demo.py      Rückfallebene: OmniVoices eigene Oberfläche
    ├── umgebung/               die virtuelle Python-Umgebung (entsteht beim Installieren)
    ├── whisper-umgebung/       nur Faster-Whisper/CTranslate2 (entsteht beim Installieren)
    ├── szenen-umgebung/        Pyannote/Demucs (wird zurzeit von keinem Reiter benutzt)
    └── daten/
        ├── installation.json   Zustandsdatei; fehlt sie, gilt alles als nicht installiert
        ├── oberflaeche.json    gespeicherte Einstellungen der Web-Oberfläche
        └── protokolle/         ein Protokoll je Durchlauf
```

Die Konsolenoberfläche benötigt zum ersten Start ein kleines **Bootstrap-Python** zwischen
3.10 und 3.13 und benutzt dort ausschließlich die Standardbibliothek. Fehlt eine passende
Version – auch wenn bereits Python 3.14+ installiert ist –, bietet der Starter automatisch
Python 3.12 zusätzlich an. PyTorch, OmniVoice, Gradio und deren Zubehör landen anschließend
isoliert in `system/umgebung`.
Faster-Whisper und CTranslate2 landen getrennt in `system/whisper-umgebung`;
Pyannote und Demucs in `system/szenen-umgebung`. Alle drei Bereiche werden über
schmale Helferskripte angesprochen und können ihre Paketversionen nicht gegenseitig verändern.

> `system/szenen-umgebung` stammt aus der früheren Cutscene-Trennung mit Demucs und Pyannote.
> Seit der Szenen-Editor an ihre Stelle getreten ist, wird sie von der Oberfläche nicht mehr
> angesprochen. Die Installation legt sie weiterhin an – wer die Zeit und den Platz sparen
> will, kann diesen Schritt aus `omnivoice_toolkit.py` entfernen.

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
| 7 | Whisper-Umgebung | zweites, isoliertes venv |
| 8 | Faster-Whisper | eigene Paketprüfung mit `pip check` |
| 9 | Szenen-Umgebung | drittes, isoliertes venv |
| 10 | Szenen-PyTorch | dieselbe CUDA-/XPU-/CPU-Auswahl in eigener Umgebung |
| 11 | Pyannote und Demucs | Paketinstallation und `pip check` |
| 12 | Audiomischer | gekapseltes FFmpeg für den finalen Mix |
| 13 | OmniVoice-Sprachmodell | Ordnergröße im HF-Cache gegen Repo-Größe |
| 14 | Whisper-Modell `medium` | Ordnergröße im HF-Cache gegen Repo-Größe |
| 15 | Test | Imports aller drei Umgebungen, Geräteabfrage, Paketversionen |
| 16 | Abschluss | schreibt `installation.json` |

Gesamt-ETA = Restzeit des laufenden Schritts + Schätzungen der übrigen Schritte.
Die Schätzungen werden nach jedem Download mit dem **gemessenen** Tempo neu berechnet,
deshalb wird die Anzeige mit der Zeit genauer.

Ein eigener Takt-Thread ruft die Fortschrittsberechnung alle 0,5 s auf. Ohne den würde
der Balken während eines minutenlangen Downloads ohne Ausgabezeile einfrieren.

Zwei Stolpersteine, die dabei umgangen werden:

- **`--progress-bar raw` erst nach Optionsprüfung – getrennt für jede Umgebung.**
  Ältere mit Python ausgelieferte pip-Builds kennen den Wert nicht und brechen damit ab. Die
  OmniVoice- und Whisper-Umgebung prüfen deshalb jeweils ihre echte Optionsliste. Der erste
  Whisper-Bootstrap nutzt die kompatible Anzeige; nach dem Upgrade wird erneut geprüft.
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

`helfer/oberflaeche.py` baut die deutsche Oberfläche mit vier Arbeitsreitern –
**Stimme klonen** (`ref_audio` + optional `ref_text`), **Überraschung** (ohne Vorgabe),
**Liste erzeugen** (Whisper/Fuzzy/Lookup) und **Stapel** – plus einem Reiter für Einstellungen.

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

## Länge und Klang

Das Häkchen »so lang wie die Sprachprobe« setzt OmniVoices `duration` auf die per
`soundfile.info()` gemessene Länge der Referenzaufnahme, zuzüglich des eingestellten
Versatzes. Umgesetzt in `motor.baue_argumente()`, gilt also für Einzelstück,
Hauptprozess-Betrieb und Arbeiter-Prozesse gleichermaßen.

**Die Vorgabe allein genügt nicht.** OmniVoice trifft sie nur ungefähr, weil seine eigene
Nachbearbeitung (`postprocess_output`, standardmäßig an) zweierlei tut: sie hängt je
`pad_duration` **0,1 s Stille an jede Seite** – die Datei ist damit systematisch 0,2 s zu
lang – und sie schneidet erzeugte Stille weg, wodurch andere Dateien deutlich zu kurz
werden. Deshalb:

1. `pad_duration=0.0` wird mitgegeben, sobald eine Länge vorgegeben ist.
2. `motor.laenge_erzwingen()` bringt die Aufnahme danach auf **exakt** die Zielsamplezahl:
   zu lang wird mit 15 ms Ausblendung abgeschnitten (sonst knackt der Schnitt), zu kurz mit
   Stille aufgefüllt.

Zu lang darf eine Vertonung nie sein – sie passt sonst nicht in ihren Platz. Wie viel
korrigiert wurde, steht im Protokoll, in der Statusmeldung der Einzelzeile und in der
Spalte »Meldung« des CSV-Berichts. Große Kürzungen sind das Signal, den deutschen Text zu
straffen.

Eine ausdrücklich gesetzte feste Länge hat Vorrang; ohne Sprachprobe passiert nichts.

Stille-Entfernung und Lautstärke laufen als `motor.nachbearbeiten()` **nach** dem Erzeugen
und **vor** dem Schreiben – ebenfalls im gemeinsamen Motor, damit Stapel und Einzelzeile
dasselbe Ergebnis liefern. Die Schwelle für Stille liegt relativ zum lautesten Punkt der
Aufnahme (−45 dB), ist also unabhängig von der Gesamtlautstärke. Beim Angleichen wird der
Effektivwert der Vorlage getroffen und danach die Spitze auf 0,99 begrenzt.

---

## Erweiterte Ansicht: Umsetzung

`tabelle.py` hält das Modell (`Eintrag` je CSV-Zeile), berechnet Zustände und baut die
Tabelle als HTML – bewusst ohne Gradio-Komponenten. Eine Gradio-Tabelle kann weder zwei
Wellenformen noch einen Knopf je Zeile aufnehmen; als reines HTML passt beliebig viel
hinein, und die ganze Logik bleibt ohne Browser testbar. Ein echtes `<table>`-Element sorgt
dafür, dass die Ansicht auch ohne Stylesheet lesbar bleibt.

**Bedienung über `gr.HTML(server_functions=…)`.** Gradio 6 erlaubt es, Python-Funktionen
direkt aus dem `js_on_load`-Code der Komponente aufzurufen. Neben Neuerzeugung, Ton und
Nachladen laufen darüber auch Texteditor, Lookup-Suche und Speichern. Wichtig dabei: **ein** Argument kommt
unverändert in Python an, mehrere werden zu einer Liste zusammengefasst – deshalb wird immer
genau ein Objekt übergeben. Diese Aufrufe laufen am normalen Ereignisweg vorbei und kennen
die Bedienelemente nicht; Bestand und aktuelle Einstellungen liegen darum in zwei
Wörterbüchern, die bei jeder Änderung nachgeführt werden.

Die Ereignisse hängen an der Wurzel der Komponente, nicht an den Zeilen. Dadurch überleben
sie jedes Neuzeichnen, und nachgeladene Zeilen sind sofort bedienbar.

**Wellenformen** entstehen als kleines SVG (ein gefüllter Pfad aus 70 Hüllkurvenpunkten)
direkt aus den Abtastwerten. Zwischengespeichert wird nach Pfad, Änderungszeit und Größe –
nach dem Neuerzeugen einer Datei ändert sich der Schlüssel also von selbst. Gezeichnet wird
nur, was sichtbar ist; Dauern kommen aus `sf.info()` und sind billig.

**Abspielen ab Klickposition:** Der Anteil der Klickstelle an der Breite geht an den Server,
der daraus die Startsekunde berechnet und die Datei als `data:`-Adresse zurückgibt (bis
12 MB). Der Umweg über die Adresse statt über eine Datei-URL ist Absicht: Die englischen
Vorlagen liegen irgendwo im Projekt des Anwenders und wären für Gradio sonst gar nicht
erreichbar. Gesetzt wird `currentTime` erst nach `loadedmetadata`, sonst ignorieren Browser
den Sprung.

**Große Originale in Abschnitten.** Englische Spielaufnahmen sind oft mehrkanalig, 48 kHz
und minutenlang und sprengen die 12 MB deutlich – deutsche Ergebnisse dagegen sind Mono mit
24 kHz und bleiben winzig. Genau deshalb ging vorher nur die deutsche Seite. Statt das
Abspielen zu verweigern, liest `ausschnitt_uri()` über `sf.SoundFile.seek()` **nur den
gebrauchten Bereich**, mischt ihn auf Mono, rechnet ihn auf 24 kHz herunter und liefert
60 Sekunden als kleine Adresse (rund 3,7 MB statt 44 MB für die ganze Datei). Die Antwort
enthält zusätzlich `weiter` – die Sekunde, an der es danach losgeht. Der Browser holt das
nächste Stück im `ended`-Ereignis nach, sodass eine lange Szene ohne Unterbrechung
durchläuft. Kleine Dateien gehen weiterhin komplett hinüber, damit sich frei spulen lässt.

**Endloses Nachladen:** Der Rahmen scrollt selbst (`max-height`), am Ende steht eine Marke
mit dem nächsten Startindex. Ein Scroll-Ereignis nahe am Ende holt die nächsten 40 Zeilen
und hängt sie an – kein Neuaufbau, die Scrollposition bleibt also stehen. Eine Sperre am
Rahmen verhindert doppeltes Laden.

**Filter** arbeiten mit `fnmatch`; ohne `*` oder `?` wird das Suchwort automatisch in
Platzhalter eingefasst. Der Zustand einer Zeile ergibt sich aus Vorhandensein der Dateien,
Text und Längenabweichung (Toleranz 0,30 s).

**»Gefilterte erzeugen«** schreibt die gefilterten Zeilen in eine Zwischendatei und schickt
sie durch denselben Stapelbetrieb. Dadurch gelten Überspringen, Arbeiterzahl, Bericht und
Fortschrittsanzeige unverändert, und die Ziele bleiben garantiert dieselben.

Geprüft wurde die Liste im echten Browser gegen Gradio 6.20: Zeilenknopf ersetzt die Zeile,
Wellenform-Klick springt an die richtige Stelle und spielt bis zum Ende, Nachladen hängt die
nächsten Zeilen an, und auch nachgeladene Zeilen reagieren.

---

## Szenen-Editor: Umsetzung

Zwei Dateien, sauber getrennt: `szenen_editor.py` ist der Motor und kennt kein Gradio,
`szenen_editor_html.py` enthält nur Aussehen und Bedienung. Dadurch ist die gesamte Logik –
Schneiden, Teilen, Verschieben, Mischen – ohne Browser prüfbar.

**Datenmodell.** Eine `Szene` besteht aus `Segment`-Einträgen mit Start, Ende, Art
(`tts` oder `kopie`), Text, Sprecherprobe und Datei. Die deutsche Spur ist kein eigenes
Dokument, sondern wird bei Bedarf aus den Segmenten gerechnet: ein Nullfeld in Länge der
Quelle, in das jedes nicht stumme Segment an seine Position addiert wird, danach eine
Spitzenbegrenzung auf 0,99.

**Länge.** Beim Sprechen bekommt OmniVoice `duration` = Länge des markierten Bereichs, und die
Vorlage ist genau dieser Ausschnitt der englischen Spur. Nachbearbeitet wird über dieselbe
Kette wie im Stapel (`baue_argumente` / `nachbearbeiten`), das Ergebnis passt also exakt in
seine Lücke.

**Zeichnen.** Eine Leinwand (`canvas`) statt DOM-Elementen: Zoom, Verschieben, Auswahl und
Segmentblöcke sind bei einer halben Stunde Material sonst nicht flüssig zu bekommen. Der
Server liefert nur Hüllkurven mit 6000 Punkten je Spur; alles Weitere passiert im Browser.

**Abspielen** läuft über `data:`-Adressen in Stücken von höchstens 60 Sekunden – eine ganze
Szene am Stück wäre als Adresse zu groß. Am Ende eines Stücks wird nahtlos das nächste
geholt. Ein Klick auf die Zeitachse während der Wiedergabe startet die Kette an der neuen
Stelle neu; »anhören« aus dem Rechtsklickmenü setzt zuerst den Abspielkopf und benutzt dann
denselben Weg, damit es sich nicht anders anfühlt als der normale Start.

Beim Ziehen der Marke und bei den Pfeiltasten wird bewusst **nicht** für jede Bewegung ein
Schnipsel geholt: Ziehen hört erst beim Loslassen wieder, die Pfeiltasten nach einer
Viertelsekunde Ruhe. Sonst würde jede Mausbewegung eine Serveranfrage auslösen.

**Layout des Fensters.** Kopfzeile, Werkzeugleiste und Fuß stehen auf `flex: 0 0 auto`, nur
Bühne und Segmentliste geben nach. Vorher konnten Kopf und Werkzeugleiste umbrechen, wodurch
der Fuß aus dem Fenster mit `overflow: hidden` herausfiel – ausgerechnet der Speichern-Knopf
war damit unsichtbar. Zusätzlich ist das Fenster jetzt notfalls scrollbar, die Erklärtexte
verschwinden auf kleinen Fenstern, Eingabefelder bekommen `min-width: 0` (sonst erzwingen sie
ihre Standardbreite von rund 20 Zeichen), und der Speichern-Knopf steht ein zweites Mal ganz
oben, wo er nie verdrängt werden kann.

**Verschieben gegen Größe ändern.** Beides läuft über dieselbe Server-Funktion. Ändert sich
die Länge nicht, bleibt die Aufnahme gültig – Kopien werden neu aus dem Original geschnitten,
gesprochene Segmente einfach umgehängt. Ändert sich die Länge, wird ein gesprochenes Segment
als *veraltet* markiert, weil seine Aufnahme nicht mehr in den Bereich passt.

**Teilen** schneidet die vorhandene Aufnahme an der Cursorstelle in zwei Dateien, sodass beide
Hälften sofort wieder gültigen Ton haben. Ohne diesen Schnitt hätte man nach dem Teilen zwei
Segmente ohne Aufnahme.

**Autosicherung.** Nach jeder Änderung wird `szene.omniprojekt.json` geschrieben, in einem
Ordner je Quelldatei. Der Ordnername kommt aus einer md5-Summe des kleingeschriebenen,
aufgelösten Pfades – **nicht** aus Pythons eingebautem `hash()`, das für Texte bei jedem
Programmstart andere Werte liefert und den Zwischenstand damit unauffindbar machen würde.
Aus derselben Funktion weiß auch die Stapelliste, zu welcher Zeile bereits eine Szene
existiert.

**Verbindung zur Liste.** Editor und Liste sind zwei getrennte `gr.HTML`-Bausteine und sehen
sich gegenseitig nicht. Sie reden deshalb über zwei Funktionen am `window`-Objekt:
`izeSzeneOeffnen(pfad, ziel)` öffnet den Editor aus einer Zeile heraus,
`izeListeAuffrischen()` lässt die sichtbaren Zeilen nach dem Speichern neu einlesen. Beide
Seiten prüfen vor dem Aufruf, ob es die Gegenseite überhaupt gibt.

Geprüft im echten Browser gegen Gradio 6.20: Öffnen aus der Zeile lädt die Aufnahme und füllt
den Zielpfad vor, Teilen liefert zwei Hälften mit passendem Ton, Verschieben lässt die Länge
unangetastet, der Abspielkopf springt beim Anhören, folgt einem Klick und dem Ziehen auf der
Zeitachse und lässt sich mit den Pfeiltasten in 10-ms-Schritten setzen, die Leertaste nimmt
die zuletzt gewählte Spur, beide Speichern-Knöpfe bleiben bis hinunter zu 640×480 erreichbar,
und nach dem Speichern steht die Stapelzeile auf *fertig*.

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
»Reparieren« wählen – das entfernt `system/umgebung`, `system/whisper-umgebung` und
`system/szenen-umgebung` und baut sie neu auf, ohne bereits geladene Modelle erneut
herunterzuladen.

---

<div align="center">

**iZE**

</div>
