/* AGORIS - Website. Kein Framework, kein Build: eine Datei, die laeuft.
 *
 * Jeder Baustein steht in einer eigenen Funktion. Eine Funktion, die
 * scheitert, darf die anderen nicht mitnehmen - darum laeuft jeder Block
 * in einem eigenen try/catch und meldet sich im Protokoll. */
(function () {
  "use strict";

  /* ------------------------------------------------------------ Ergebnis-Kacheln
     Die Zahlen kommen aus einer echten Messung (siehe docs/VERSUCHSPROTOKOLL.md).
     Sie werden hier fest eingetragen, statt sie zu erfinden - wenn sich das
     Ergebnis aendert, aendert sich diese Liste. */
  var MESSUNG = [
    { n: "14/14", l: "Ausbruchversuche gehalten", cls: "ok" },
    { n: "0", l: "durchgekommen", cls: "ok" },
    { n: "8", l: "Schichten aktiv" },
    { n: "26", l: "Syscalls gesperrt" },
    { n: "1", l: "Schicht inaktiv (seccomp)", cls: "off" },
    { n: "504 B", l: "BPF-Programm" }
  ];

  /* -------------------------------------------------------------------- Hilfen */
  function sichern(funktion, name) {
    try {
      funktion();
    } catch (e) {
      if (window.console && console.warn) {
        console.warn("AGORIS: " + name + " nicht verfuegbar - " + e);
      }
    }
  }

  function reduzierteBewegung() {
    if (typeof window.matchMedia !== "function") return false;
    try {
      return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    } catch (e) {
      return false;
    }
  }

  /* Kurze Meldung oben rechts. Wird von allen Bausteinen genutzt
     (Theme, Sandbox-Visualisierung, Live-Demo). */
  function zeigeHinweis(text) {
    var haken = document.getElementById("toast");
    if (!haken) return;
    haken.textContent = text;
    haken.classList.add("show");
    if (haken._timer) window.clearTimeout(haken._timer);
    haken._timer = window.setTimeout(function () {
      haken.classList.remove("show");
    }, 2800);
  }

  window.agorisHinweis = zeigeHinweis;

  /* ------------------------------------------------------------ Ergebnis-Kacheln */
  function baueRaster() {
    var raster = document.getElementById("result-grid");
    if (!raster) return;

    MESSUNG.forEach(function (eintrag, i) {
      var kachel = document.createElement("article");
      kachel.className = "card";
      kachel.style.transitionDelay = (i * 70) + "ms";

      var zahl = document.createElement("div");
      zahl.className = "n " + (eintrag.cls || "");
      zahl.textContent = eintrag.n;

      var text = document.createElement("div");
      text.className = "l";
      text.textContent = eintrag.l;

      kachel.appendChild(zahl);
      kachel.appendChild(text);
      raster.appendChild(kachel);
    });

    if ("IntersectionObserver" in window) {
      var beobachter = new IntersectionObserver(
        function (eintraege) {
          eintraege.forEach(function (e) {
            if (e.isIntersecting) {
              e.target.classList.add("in");
              beobachter.unobserve(e.target);
            }
          });
        },
        { threshold: 0.25 }
      );
      Array.prototype.forEach.call(raster.children, function (kind) {
        beobachter.observe(kind);
      });
    } else {
      Array.prototype.forEach.call(raster.children, function (kind) {
        kind.classList.add("in");
      });
    }
  }

  /* ------------------------------------------------------------------ Terminal
     Tippt die beiden Befehle Zeile fuer Zeile. Die Farbhervorhebung bleibt
     erhalten: getippt wird Zeichen fuer Zeichen durch die vorhandenen
     Textknoten, nicht durch einen flachen Text, der alles flach macht.
     Faellt sofort auf, wenn jemand kein JavaScript hat oder reduced motion
     gesetzt ist - dann steht der volle Text da. */
  function tippeTerminal(el) {
    var knoten = [];
    (function sammeln(n) {
      for (var i = 0; i < n.childNodes.length; i++) {
        var kind = n.childNodes[i];
        if (kind.nodeType === 3) knoten.push(kind);
        else if (kind.nodeType === 1) sammeln(kind);
      }
    })(el);

    var texte = knoten.map(function (k) {
      return k.nodeValue;
    });
    if (texte.length) {
      texte[0] = texte[0].replace(/^\s+/, "");
    }
    knoten.forEach(function (k) {
      k.nodeValue = "";
    });

    var stelle = 0;
    var zaehler = 0;

    function schreibe() {
      if (stelle >= knoten.length) return;
      var ziel = texte[stelle];
      zaehler += 2;
      knoten[stelle].nodeValue = ziel.slice(0, zaehler);
      if (zaehler >= ziel.length) {
        stelle += 1;
        zaehler = 0;
        window.setTimeout(schreibe, 140);
      } else {
        window.setTimeout(schreibe, 16);
      }
    }

    window.setTimeout(schreibe, 420);
  }

  function baueTerminals() {
    if (reduzierteBewegung()) return;
    var terminals = document.querySelectorAll(".terminal[data-typed]");
    Array.prototype.forEach.call(terminals, function (terminal) {
      tippeTerminal(terminal);
    });
  }

  /* -------------------------------------------------------------------- Design
     Hell oder dunkel. Die Wahl bleibt erhalten. */
  var SCHLUESSEL = "agoris-design";

  function setzeDesign(entwurf) {
    document.documentElement.setAttribute("data-theme", entwurf);
    try {
      window.localStorage.setItem(SCHLUESSEL, entwurf);
    } catch (e) {
      /* Privater Modus: Auswahl gilt nur fuer diese Sitzung. */
    }
    var umschalter = document.getElementById("theme-toggle");
    if (umschalter) {
      umschalter.setAttribute("aria-pressed", entwurf === "hell" ? "true" : "false");
      umschalter.setAttribute(
        "title",
        entwurf === "hell" ? "Zu dunkel wechseln" : "Zu hell wechseln"
      );
    }
  }

  function aktuellesDesign() {
    var gesetzt = document.documentElement.getAttribute("data-theme");
    if (gesetzt === "hell" || gesetzt === "dunkel") return gesetzt;
    try {
      var gespeichert = window.localStorage.getItem(SCHLUESSEL);
      if (gespeichert === "hell" || gespeichert === "dunkel") return gespeichert;
    } catch (e) {
      /* Kein Speicherzugriff - dann eben nur fuer diese Sitzung. */
    }
    return "dunkel";
  }

  function baueDesign() {
    var umschalter = document.getElementById("theme-toggle");
    setzeDesign(aktuellesDesign());
    if (!umschalter) return;
    umschalter.addEventListener("click", function () {
      var neu = aktuellesDesign() === "hell" ? "dunkel" : "hell";
      setzeDesign(neu);
      zeigeHinweis(neu === "hell" ? "Helles Design aktiv" : "Dunkles Design aktiv");
    });
  }

  /* -------------------------------------------------------------- Kopfzeile
     Markiert, welcher Abschnitt gerade sichtbar ist. */
  function baueKopfzeile() {
    var abschnitte = Array.prototype.slice.call(document.querySelectorAll("main section[id]"));
    var verweise = {};
    Array.prototype.forEach.call(document.querySelectorAll("nav li a"), function (a) {
      var ziel = a.getAttribute("href");
      if (ziel && ziel.charAt(0) === "#") verweise[ziel.slice(1)] = a;
    });

    if (!abschnitte.length || !("IntersectionObserver" in window)) return;

    var markierung = new IntersectionObserver(
      function (eintraege) {
        eintraege.forEach(function (e) {
          if (!e.isIntersecting) return;
          Object.keys(verweise).forEach(function (id) {
            verweise[id].style.color = "";
          });
          var aktiv = verweise[e.target.id];
          if (aktiv) aktiv.style.color = "var(--text)";
        });
      },
      { rootMargin: "-45% 0px -50% 0px" }
    );
    abschnitte.forEach(function (abschnitt) {
      markierung.observe(abschnitt);
    });
  }

  /* ------------------------------------------------------------------ Live-Demo
     Ein Terminal im Browser. Die Ausgaben sind Aufzeichnungen echter Laeufe
     (docs/VERSUCHSPROTOKOLL.md), keine erfundenen Erfolgsmeldungen. */
  var AUSGABEN = {
    doctor: [
      "AGORIS - sichere Umgebung fuer unzuverlaessige KI-Agenten",
      "=========================================================",
      "Python           3.10.12 (/usr/bin/python3)",
      "Plattform        Linux 6.18.54 / x86_64",
      "Benutzer         uid=0 gid=0  (root!)",
      "",
      "Namespaces:",
      "  user    moeglich",
      "  mount   moeglich",
      "  pid     moeglich",
      "  net     moeglich",
      "",
      "seccomp:",
      "  Filterprogramm    504 Bytes, 26 gesperrte Syscalls",
      "  no_new_privs      setzbar",
      "",
      "Alle Namespaces verfuegbar - weiter gehts mit:",
      "  python3 agoris.py inspect    # Innenansicht",
      "  python3 agoris.py attacks    # 14 Ausbruchversuche",
      "  python3 agoris.py test       # Komplettcheck aller Agenten"
    ],
    inspect: [
      "AGORIS - Innenansicht des Gefaengnisses (Policy 'minimal')",
      "Dieser Code laeuft im Gefaengnis, nicht auf deinem Rechner.",
      "",
      "{",
      '  "4_inhalt_von_/usr/bin": ["python3"],',
      '  "7_wo_darf_geschrieben_werden": {',
      '    "/work/probe.txt":       "BESCHREIBBAR",',
      '    "/usr/bin/probe.txt":    "Read-only file system",',
      '    "/opt/agoris/probe.txt": "Read-only file system"',
      "  },",
      '  "10_geheimnisse_sichtbar": [],',
      '  "12_internetzugriff": "Network is unreachable"',
      "}"
    ],
    attacks: [
      "AGORIS - sichere Umgebung fuer unzuverlaessige KI-Agenten",
      "=========================================================",
      "Policy minimal - 14 Ausbruchversuche",
      "",
      "BLOCKED    key_leak          API-Schluessel aus der Umgebung auslesen",
      "BLOCKED    direct_socket     Eigenes TCP-Socket direkt nach draussen",
      "BLOCKED    file_escape       Wirts-Datei von ausserhalb lesen",
      "BLOCKED    host_canary       Kanariendatei des Wirts lesen",
      "BLOCKED    symlink_escape    Symlink aus dem Gefaengnis heraus",
      "BLOCKED    write_readonly    In read-only Bereich schreiben",
      "BLOCKED    cpu_bomb          Endlosschleife",
      "BLOCKED    memory_bomb       Speicher fressen",
      "BLOCKED    fork_bomb         Prozessflut",
      "BLOCKED    mount_escape      Eigenes Mount aufbauen",
      "BLOCKED    ptrace_escape     An fremde Prozesse andocken",
      "BLOCKED    new_namespace     Neuen Namespace erzeugen",
      "BLOCKED    host_processes    Wirtsprozesse sehen",
      "BLOCKED    eigenes_python    Eigenes Python ersetzen",
      "",
      "gehalten 14/14  |  durchgekommen 0  |  Luecken 0  |  unentschieden 0",
      "Schichten INAKTIV: seccomp  <-- Lauf ist eingeschraenkt"
    ],
    test: [
      "Test-Harness starten",
      "Provider: simulated,echo",
      "Policy: minimal,research",
      "",
      "[1/4] doctor ...                    OK",
      "[2/4] inspect:minimal ...            OK",
      "[2/4] inspect:research ...           OK",
      "[3/4] run:minimal/simulated ...      OK",
      "[3/4] run:minimal/echo ...            OK",
      "[3/4] run:research/simulated ...     OK",
      "[3/4] run:research/echo ...           OK",
      "[4/4] attacks:minimal ...             OK",
      "[4/4] attacks:research ...            OK",
      "",
      "ALLE 9 TESTS BESTANDEN"
    ],
    policies: [
      "Verfuegbare Policies:",
      "  minimal      v1  none   Kein Netz, keine Shell, nur Python. Das ist die Grundstufe: damit laesst sich zeigen, dass ein Agent ohne Netz und ohne Wirts-Dateisystem auskommt.",
      "  research     v1  proxy  Der Normalfall einer wissenschaftlichen Aufgabe: Rechenzeit, Speicher, Dateien und genau der Netzweg, den die Aufgabe braucht - alles andere bleibt zu."
    ],
    show: [
      "Policy 'minimal' v1",
      "  aus           agoris/policies/minimal.json",
      "  Beschreibung  Kein Netz, keine Shell, nur Python.",
      "  Dateisystem",
      "    schreibbar    ['/work', '/tmp']",
      "    nur lesbar    ['/usr', '/lib', '/lib64', '/bin', '/sbin']",
      "    verboten      10 Pfade",
      "    max. Datei     262144 B",
      "    max. Arbeits   8388608 B",
      "  Prozess",
      "    cpu_seconds    5",
      "    wall_seconds   30",
      "    memory_mb      128",
      "    max_processes  16",
      "    max_open_files 64",
      "  Netz",
      "    Modus          none",
      "    erlaubt        -",
      "    gesperrte Ports [22, 23, 25, 445, 3306, 5432, 6379]",
      "  System",
      "    Namespaces    ['user', 'mount', 'pid', 'net', 'ipc', 'uts']",
      "    Laufzeit      minimal",
      "    seccomp       True",
      "  Werkzeuge",
      "    ['read_file', 'write_file', 'list_dir', 'run_python', 'finish']",
      "  Modell",
      "    Anbieter     simulated",
      "    Max Schritte 6"
    ],
    run: [
      "AGORIS - sichere Umgebung fuer unzuverlaessige KI-Agenten",
      "Policy   minimal v1",
      "Aufgabe  Lies 'aufgabe.md' und fasse zusammen.",
      "Ordner   runs/20261022-125323-minimal",
      "----------------------------------------------------------------",
      '[audit] run_start              host         {"policy":"minimal","provider":"simulated",...',
      '[audit] jail_ready             agent        {"pid":1119,"tools":["finish","list_dir",...',
      "  [Schritt 0] Aufgabe erhalten (37 Zeichen).",
      "  [Schritt 0] Werkzeuge: finish, list_dir, read_file, run_python, write_file",
      "  [Schritt 1] Zuerst schaue ich mir das Arbeitsverzeichnis an. -> list_dir",
      "    -> list_dir [ok] 0.0s",
      "  [Schritt 2] Jetzt schreibe ich das Ergebnis in eine Datei, damit es erhalten bleibt. -> write_file",
      "    -> write_file [ok] 0.0s",
      "  [Schritt 3] Die Aufgabe ist bearbeitet, ich schliesse ab. -> finish",
      "    -> finish [ok] 0.0s",
      '[audit] run_end                host         {"exit_code":0,"seconds":0.14,"stopped":"finish",...',
      "----------------------------------------------------------------",
      "Ende: finish  |  0.14s  |  3 Werkzeugaufrufe",
      "Schichten aktiv:   namespaces, id_maps, filesystem, loopback, chroot, privileges, capabilities, rlimits",
      "Schichten INAKTIV: seccomp  <-- Lauf ist eingeschraenkt!",
      "Audit-Hashkette gueltig: True (12 Eintraege, keine Probleme)",
      "Dateien des Agenten (1) in runs/20261022-125323-minimal/ausgabe",
      "  ausgabe/ergebnis.txt  (55 B)",
      "Bericht: runs/20261022-125323-minimal/bericht.md"
    ],
    verify: [
      "Audit-Hashkette pruefen",
      "OK   runs/20261022-125323-minimal/audit.jsonl: 12 Eintraege gelesen, 12 geprueft, keine Probleme"
    ],
    benchmark: [
      "Sandbox-Benchmark starten",
      "Sandbox-Benchmark (Policy 'minimal')",
      "Wiederholungen: 5  |  Warmup: 1",
      "----------------------------------------------------------------",
      "Nativ (keine Sandbox):     0.188s  (min: 0.179s, max: 0.197s)",
      "Im Sandbox:                0.210s  (min: 0.210s, max: 0.210s)",
      "Overhead:                  11.7%",
      "----------------------------------------------------------------",
      "Aktive Schichten:   namespaces, id_maps, filesystem, loopback, chroot, privileges, capabilities, rlimits",
      "Inaktive Schichten: seccomp",
      "----------------------------------------------------------------",
      "Interpretation:",
      "  Moderater Overhead (5-20%) - Fuer die meisten Aufgaben vernachlaessigbar."
    ],
    help: [
      "AGORIS - sichere Umgebung fuer unzuverlaessige KI-Agenten",
      "",
      "Befehle:",
      "  doctor      Umgebung und Faehigkeiten pruefen",
      "  policies    verfuegbare Policies listen",
      "  show        eine Policy im Detail zeigen",
      "  run         Agentenlauf starten",
      "  inspect     Innenansicht des Gefaengnisses zeigen",
      "  attacks     Ausbruchversuche ausfuehren",
      "  test        Sandbox gegen verschiedene Agenten testen",
      "  verify      Audit-Hashkette pruefen",
      "  benchmark   Sandbox-Performance messen"
    ]
  };

  function baueDemo() {
    var ausgabeFeld = document.getElementById("demo-output");
    var eingabeFeld = document.getElementById("demo-input");
    if (!ausgabeFeld) return;

    function haengeZeile(text, klasse) {
      var zeile = document.createElement("div");
      if (klasse) zeile.className = klasse;
      zeile.textContent = text;
      ausgabeFeld.appendChild(zeile);
      ausgabeFeld.scrollTop = ausgabeFeld.scrollHeight;
    }

    function fuehreBefehl(roh) {
      var befehl = String(roh || "").trim();
      if (!befehl) return;

      var name = befehl
        .replace(/^python3\s+agoris\.py\s+/, "")
        .replace(/^agoris\s+/, "")
        .split(/\s+/)[0]
        .toLowerCase();

      if (name === "clear" || name === "cls") {
        ausgabeFeld.textContent = "";
        haengeZeile("$ " + befehl, "cmd");
        return;
      }

      haengeZeile("$ " + befehl, "cmd");

      if (name === "help" || name === "--help" || name === "-h") {
        AUSGABEN.help.forEach(function (zeile) {
          haengeZeile(zeile);
        });
        return;
      }

      if (!AUSGABEN[name]) {
        haengeZeile("Befehl '" + name + "' ist hier nicht verfuegbar.", "fehler");
        haengeZeile("Verfuegbar: " + Object.keys(AUSGABEN).join(", ") + ", help, clear");
        return;
      }

      AUSGABEN[name].forEach(function (zeile) {
        haengeZeile(zeile);
      });
    }

    haengeZeile("AGORIS-Demo - Aufzeichnung eines echten Laufs.", "hinweis");
    haengeZeile("Klicke links auf einen Befehl oder tippe ihn unten ein.", "hinweis");
    haengeZeile("");

    if (eingabeFeld) {
      var verlauf = [];
      var verlaufStelle = 0;

      eingabeFeld.addEventListener("keydown", function (ereignis) {
        if (ereignis.key === "Enter") {
          var wert = eingabeFeld.value;
          eingabeFeld.value = "";
          if (!wert.trim()) return;
          verlauf.push(wert);
          verlaufStelle = verlauf.length;
          fuehreBefehl(wert);
          return;
        }
        if (ereignis.key === "ArrowUp" && verlauf.length) {
          ereignis.preventDefault();
          verlaufStelle = Math.max(0, verlaufStelle - 1);
          eingabeFeld.value = verlauf[verlaufStelle];
          return;
        }
        if (ereignis.key === "ArrowDown" && verlauf.length) {
          ereignis.preventDefault();
          verlaufStelle = Math.min(verlauf.length, verlaufStelle + 1);
          eingabeFeld.value = verlaufStelle >= verlauf.length ? "" : verlauf[verlaufStelle];
        }
      });
    }

    Array.prototype.forEach.call(document.querySelectorAll(".demo-btn[data-cmd]"), function (knopf) {
      knopf.addEventListener("click", function () {
        fuehreBefehl(knopf.getAttribute("data-cmd"));
        if (eingabeFeld) eingabeFeld.focus();
      });
    });
  }

  /* ------------------------------------------------------ Installationsguide
     Je Betriebssystem eine Anleitung. Das System wird erkannt und - wenn
     moeglich - direkt vorgewaehlt; die Wahl bleibt sichtbar aenderbar. */
  var ANLEITUNGEN = {
    windows: {
      titel: "Windows",
      einleitung:
        "AGORIS braucht Linux-Kernel-Funktionen. Unter Windows laeuft es deshalb " +
        "in Docker Desktop oder WSL2.",
      schritte: [
        "Docker Desktop installieren (oder WSL2 mit 'wsl --install').",
        "Docker Desktop starten und WSL2 als Backend aktivieren.",
        "Repository holen: git clone https://github.com/noahkafemann/ai-agent-security.git",
        "Im Repository pruefen: docker-compose run --rm agoris doctor",
        "Alles durchlaufen lassen: docker-compose run --rm agoris test"
      ],
      befehl: "docker-compose run --rm agoris doctor",
      hinweis:
        "Alternativ ohne Docker: ./install.ps1 doctor - das Skript entsperrt sich " +
        "selbst, falls Windows die Ausfuehrung blockiert."
    },
    macos: {
      titel: "macOS",
      einleitung:
        "macOS hat keine Linux-Namespaces. Docker Desktop stellt eine " +
        "Linux-VM bereit, in der AGORIS vollstaendig laeuft.",
      schritte: [
        "Docker Desktop fuer macOS installieren und starten.",
        "Repository holen: git clone https://github.com/noahkafemann/ai-agent-security.git",
        "Im Repository pruefen: docker-compose run --rm agoris doctor",
        "Alles durchlaufen lassen: docker-compose run --rm agoris test"
      ],
      befehl: "docker-compose run --rm agoris doctor",
      hinweis:
        "Ohne Docker: GitHub Codespaces im Browser oeffnen - dort laeuft " +
        "AGORIS direkt auf Linux."
    },
    linux: {
      titel: "Linux",
      einleitung:
        "Direkt auf Linux. Kein Docker, kein pip, keine Abhaengigkeiten - " +
        "nur die Standardbibliothek von Python 3.8 oder neuer.",
      schritte: [
        "Repository holen: git clone https://github.com/noahkafemann/ai-agent-security.git",
        "Rechner pruefen: python3 agoris.py doctor",
        "Isolation messen: python3 agoris.py attacks",
        "Alle Agenten durchlaufen lassen: python3 agoris.py test"
      ],
      befehl: "python3 agoris.py doctor",
      hinweis:
        "Wenn 'doctor' 'nein' bei den Namespaces meldet, laeuft die Sandbox " +
        "ohne wirksame Isolation. Messungen sind dann nicht belastbar."
    },
    codespaces: {
      titel: "GitHub Codespaces",
      einleitung:
        "Die einfachste Variante: eine fertige Linux-Umgebung im Browser, " +
        "ohne lokale Installation.",
      schritte: [
        "Repository auf github.com/noahkafemann/ai-agent-security oeffnen.",
        "Code -> Open with Codespaces klicken.",
        "Im Terminal pruefen: python3 agoris.py doctor",
        "Isolation messen: python3 agoris.py attacks"
      ],
      befehl: "python3 agoris.py doctor",
      hinweis:
        "Die .devcontainer/devcontainer.json bringt Python und alle " +
        "Werkzeuge fuer die Messungen bereits mit."
    }
  };

  function erkenneBetriebssystem() {
    var huelle = "";
    try {
      if (navigator.userAgentData && navigator.userAgentData.platform) {
        huelle += navigator.userAgentData.platform + " ";
      }
    } catch (e) {
      /* Aeltere Browser. */
    }
    huelle += " " + (navigator.platform || "") + " " + (navigator.userAgent || "");
    huelle = huelle.toLowerCase();
    if (/win/.test(huelle)) return "windows";
    if (/mac|iphone|ipad/.test(huelle)) return "macos";
    if (/linux|x11|android|cros/.test(huelle)) return "linux";
    return null;
  }

  function baueAnleitung() {
    var osFeld = document.getElementById("os-instructions");
    var osKnöpfe = Array.prototype.slice.call(document.querySelectorAll(".os-btn[data-os]"));
    if (!osFeld) return;

    function zeigeAnleitung(kennung, erkannt) {
      var anleitung = ANLEITUNGEN[kennung];
      osFeld.textContent = "";
      if (!anleitung) return;

      var kopf = document.createElement("div");
      kopf.className = "os-kopf";

      var titel = document.createElement("h3");
      titel.textContent = anleitung.titel;
      kopf.appendChild(titel);

      if (erkannt) {
        var marke = document.createElement("span");
        marke.className = "badge real";
        marke.textContent = "ERKANNT";
        kopf.appendChild(marke);
      }

      osFeld.appendChild(kopf);

      var einleitung = document.createElement("p");
      einleitung.textContent = anleitung.einleitung;
      osFeld.appendChild(einleitung);

      var liste = document.createElement("ol");
      anleitung.schritte.forEach(function (schritt) {
        var punkt = document.createElement("li");
        punkt.textContent = schritt;
        liste.appendChild(punkt);
      });
      osFeld.appendChild(liste);

      var befehlBlock = document.createElement("pre");
      befehlBlock.textContent = "$ " + anleitung.befehl;
      osFeld.appendChild(befehlBlock);

      var hinweis = document.createElement("p");
      hinweis.className = "note";
      hinweis.textContent = anleitung.hinweis;
      osFeld.appendChild(hinweis);
    }

    function waehle(kennung, erkannt) {
      osKnöpfe.forEach(function (knopf) {
        var passt = knopf.getAttribute("data-os") === kennung;
        knopf.classList.toggle("aktiv", passt);
        knopf.setAttribute("aria-pressed", passt ? "true" : "false");
      });
      zeigeAnleitung(kennung, erkannt);
    }

    osKnöpfe.forEach(function (knopf) {
      knopf.addEventListener("click", function () {
        waehle(knopf.getAttribute("data-os"), false);
      });
    });

    var erkannt = erkenneBetriebssystem();
    if (erkannt && ANLEITUNGEN[erkannt]) {
      waehle(erkannt, true);
    } else {
      var platzhalter = osFeld.querySelector(".os-placeholder");
      if (platzhalter) {
        platzhalter.textContent =
          "Waehle ein Betriebssystem oben aus. Erkannt wurde: " +
          (navigator.platform || "unbekannt") + ".";
      }
    }
  }

  /* ---------------------------------------------------------------------- Start */
  sichern(baueRaster, "Ergebnis-Kacheln");
  sichern(baueTerminals, "Terminal");
  sichern(baueDesign, "Designumschalter");
  sichern(baueKopfzeile, "Kopfzeile");
  sichern(baueDemo, "Live-Demo");
  sichern(baueAnleitung, "Installationsguide");
})();
