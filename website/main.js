/* AGORIS - Website. Kein Framework, kein Build: eine Datei, die laeuft. */
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

  var raster = document.getElementById("result-grid");

  if (raster) {
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
     Tippt die beiden Befehle Zeile fuer Zeile. Rein kosmetisch, faellt aber
     sofort aus, wenn jemand kein JavaScript hat oder reduced motion gesetzt ist. */
  var terminal = document.querySelector(".terminal");
  var reduziert = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  if (terminal && !reduziert) {
    var volltext = terminal.textContent.replace(/^\s+/, "");
    terminal.textContent = "";

    var zeilen = volltext.split("\n");
    var zaehler = { zeile: 0, zeichen: 0 };
    var puffer = "";

    function schreibe() {
      if (zaehler.zeile >= zeilen.length) {
        puffer += "\n";
        terminal.appendChild(document.createTextNode(puffer));
        return;
      }
      var ziel = zeilen[zaehler.zeile];
      if (zaehler.zeichen < ziel.length) {
        zaehler.zeichen += 2;
        puffer = zeilen
          .slice(0, zaehler.zeile)
          .concat([ziel.slice(0, zaehler.zeichen)])
          .join("\n");
        terminal.appendChild(document.createTextNode(puffer));
        window.setTimeout(schreibe, 16);
      } else {
        puffer += ziel + "\n";
        terminal.appendChild(document.createTextNode(puffer));
        zaehler.zeile += 1;
        zaehler.zeichen = 0;
        window.setTimeout(schreibe, 260);
      }
    }

    window.setTimeout(schreibe, 420);
  }

  /* -------------------------------------------------------------- Kopfzeile
     Markiert, welcher Abschnitt gerade sichtbar ist. */
  var abschnitte = Array.prototype.slice.call(document.querySelectorAll("main section[id]"));
  var verweise = {};
  Array.prototype.forEach.call(document.querySelectorAll("nav li a"), function (a) {
    var ziel = a.getAttribute("href");
    if (ziel && ziel.charAt(0) === "#") verweise[ziel.slice(1)] = a;
  });

  if (abschnitte.length && "IntersectionObserver" in window) {
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
})();