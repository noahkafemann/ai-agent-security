/* AGORIS Sandbox Visualization - Interactive Sandbox View
 * Distinguishes real sandbox events from simulated demo events
 * Shows allowed (green/blue), denied (red), suspicious (orange) actions
 */

(function() {
  "use strict";

  const DEMO_EVENTS = [
    {
      id: 1,
      time: "10:23:45.123",
      type: "TOOL_CALL",
      from: "agent",
      to: "filesystem",
      action: "list_dir /work",
      result: "allowed",
      real: false,
      detail: "Agent fordert Zugriff auf /work. Policy erlaubt Lesezugriff auf Arbeitsverzeichnis. Aktion wird ausgeführt."
    },
    {
      id: 2,
      time: "10:23:46.234",
      type: "FILE_WRITE",
      from: "agent",
      to: "filesystem",
      action: "write_file /work/aufgabe.txt",
      result: "allowed",
      real: false,
      detail: "Schreibzugriff auf /work ist nach Policy erlaubt. Datei wird erstellt."
    },
    {
      id: 3,
      time: "10:23:47.456",
      type: "SYSCALL",
      from: "agent",
      to: "network",
      action: "socket() + connect() to 1.1.1.1:80",
      result: "denied",
      real: false,
      detail: "Direkter Netzwerkzugriff versucht. Netz-Namespace hat kein Interface außer ausgeschaltetem Loopback. Verbindung verweigert."
    },
    {
      id: 4,
      time: "10:23:48.567",
      type: "FILE_READ",
      from: "agent",
      to: "filesystem",
      action: "open('/etc/shadow')",
      result: "denied",
      real: false,
      detail: "Zugriff auf /etc/shadow versucht. Im chroot ist nur minimales Dateisystem eingebunden - Datei existiert nicht. Zugriff verweigert."
    },
    {
      id: 5,
      time: "10:23:49.678",
      type: "SYSCALL",
      from: "agent",
      to: "processes",
      action: "mount() /tmp/proc-test",
      result: "denied",
      real: false,
      detail: "Mount-Versuch erkannt. CAP_SYS_ADMIN verworfen, seccomp sperrt mount/umount2. EPERM."
    },
    {
      id: 6,
      time: "10:23:50.789",
      type: "SYSCALL",
      from: "agent",
      to: "processes",
      action: "ptrace(PTRACE_ATTACH)",
      result: "denied",
      real: false,
      detail: "ptrace-Versuch. Seccomp sperrt ptrace(101). EPERM."
    },
    {
      id: 7,
      time: "10:23:51.890",
      type: "RESOURCE",
      from: "agent",
      to: "processes",
      action: "fork() - Prozessflut",
      result: "suspicious",
      real: false,
      detail: "Fork-Bombe erkannt. RLIMIT_NPROC begrenzt Anzahl Prozesse pro UID. Bei uid 0 gilt Grenze nicht - aber Architektur verhindert Ausbreitung."
    },
    {
      id: 8,
      time: "10:23:52.901",
      type: "FILE_READ",
      from: "agent",
      to: "filesystem",
      action: "read host canary file",
      result: "denied",
      real: false,
      detail: "Kanariendatei außerhalb von /jail/ versucht zu lesen. chroot verhindert Zugriff. Symlink-Auflösung blockiert."
    }
  ];

  /* Mittelpunkte der Komponenten - sie folgen den Koordinaten im SVG. */
  const COORDS = {
    agent: { x: 200, y: 250 },
    filesystem: { x: 365, y: 227 },
    terminal: { x: 355, y: 315 },
    processes: { x: 470, y: 230 },
    network: { x: 540, y: 275 }
  };

  const COMPONENTS = {
    agent: document.getElementById('comp-agent'),
    filesystem: document.getElementById('comp-fs'),
    terminal: document.getElementById('comp-term'),
    processes: document.getElementById('comp-proc'),
    network: document.getElementById('comp-net')
  };

  const eventLogEl = document.getElementById('eventLog');
  const eventDetailEl = document.getElementById('eventDetail');
  const eventDetailTextEl = document.getElementById('eventDetailText');
  const statAllowedEl = document.getElementById('stat-allowed');
  const statDeniedEl = document.getElementById('stat-denied');
  const statSuspiciousEl = document.getElementById('stat-suspicious');
  const eventPathsEl = document.getElementById('eventPaths');
  const sandboxBoxEl = document.getElementById('sandboxBox');
  const boundaryEl = document.querySelector('.boundary-zone');

  let stats = { allowed: 0, denied: 0, suspicious: 0 };
  let currentIndex = 0;
  let isRunning = false;
  let laufTimer = null;
  let pfadTimer = null;

  /* Kurze Meldung - kommt aus main.js, damit es nur eine Stelle gibt. */
  function hinweis(text) {
    if (typeof window.agorisHinweis === 'function') {
      window.agorisHinweis(text);
      return;
    }
    if (window.console && console.log) console.log(text);
  }

  function clearHighlights() {
    Object.values(COMPONENTS).forEach(comp => {
      if (comp) comp.classList.remove('highlight', 'allowed', 'denied', 'suspicious');
    });
    if (sandboxBoxEl) sandboxBoxEl.classList.remove('highlight');
    if (boundaryEl) boundaryEl.classList.remove('highlight');
  }

  function highlightComponent(name, result) {
    clearHighlights();
    if (COMPONENTS[name]) {
      COMPONENTS[name].classList.add('highlight', result);
    }
    if (result === 'denied') {
      if (sandboxBoxEl) sandboxBoxEl.classList.add('highlight');
      if (boundaryEl) boundaryEl.classList.add('highlight');
    }
  }

  function drawPath(from, to, result) {
    if (!eventPathsEl) return;
    eventPathsEl.innerHTML = '';

    const fromPos = COORDS[from];
    const toPos = COORDS[to];
    if (!fromPos || !toPos) return;

    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    const midX = (fromPos.x + toPos.x) / 2;
    const midY = Math.min(fromPos.y, toPos.y) - 40;
    path.setAttribute('d', `M ${fromPos.x} ${fromPos.y} Q ${midX} ${midY} ${toPos.x} ${toPos.y}`);
    path.setAttribute('class', `event-path path-${result}`);
    eventPathsEl.appendChild(path);

    if (pfadTimer) clearTimeout(pfadTimer);
    pfadTimer = setTimeout(() => {
      if (eventPathsEl) eventPathsEl.innerHTML = '';
    }, 2000);
  }

  function addEventToLog(event) {
    if (!eventLogEl) return;

    const empty = eventLogEl.querySelector('.log-empty');
    if (empty) empty.remove();

    const item = document.createElement('div');
    item.className = `event-item ${event.result}`;
    item.setAttribute('data-id', String(event.id));

    const kopf = document.createElement('div');
    const zeit = document.createElement('span');
    zeit.className = 'time';
    zeit.textContent = event.time;
    kopf.appendChild(zeit);

    const marke = document.createElement('span');
    marke.className = `badge ${event.real ? 'real' : 'demo'}`;
    marke.style.fontSize = '8px';
    marke.style.padding = '1px 4px';
    marke.textContent = event.real ? 'ECHT' : 'DEMO';
    kopf.appendChild(document.createTextNode(' '));
    kopf.appendChild(marke);

    const zweit = document.createElement('div');
    const typ = document.createElement('span');
    typ.className = 'type';
    typ.textContent = event.type;
    zweit.appendChild(typ);
    zweit.appendChild(document.createTextNode(' → '));
    const ziel = document.createElement('span');
    ziel.className = 'target';
    ziel.textContent = String(event.to).toUpperCase();
    zweit.appendChild(ziel);

    const aktion = document.createElement('div');
    aktion.textContent = event.action;

    const ergebnis = document.createElement('div');
    ergebnis.className = 'result';
    ergebnis.textContent = String(event.result).toUpperCase();

    item.appendChild(kopf);
    item.appendChild(zweit);
    item.appendChild(aktion);
    item.appendChild(ergebnis);

    item.addEventListener('click', () => {
      if (eventDetailEl) eventDetailEl.style.display = 'block';
      if (eventDetailTextEl) eventDetailTextEl.textContent = event.detail;
      eventLogEl.querySelectorAll('.event-item').forEach(i => { i.style.opacity = '0.5'; });
      item.style.opacity = '1';
      item.style.background = 'rgba(53, 224, 232, 0.12)';
    });

    eventLogEl.insertBefore(item, eventLogEl.firstChild);
  }

  function updateStats(result) {
    if (result === 'allowed') stats.allowed++;
    else if (result === 'denied') stats.denied++;
    else if (result === 'suspicious') stats.suspicious++;

    if (statAllowedEl) statAllowedEl.textContent = String(stats.allowed);
    if (statDeniedEl) statDeniedEl.textContent = String(stats.denied);
    if (statSuspiciousEl) statSuspiciousEl.textContent = String(stats.suspicious);
  }

  function zeigeEreignis(event) {
    highlightComponent(event.to, event.result);
    drawPath(event.from, event.to, event.result);
    addEventToLog(event);
    updateStats(event.result);
  }

  function plan(delay) {
    if (laufTimer) clearTimeout(laufTimer);
    laufTimer = setTimeout(runNextEvent, delay);
  }

  function runNextEvent() {
    if (currentIndex >= DEMO_EVENTS.length) {
      if (isRunning) {
        isRunning = false;
        hinweis(`Demo abgeschlossen. Alle ${DEMO_EVENTS.length} Ereignisse durchlaufen.`);
      } else {
        hinweis(`Alle ${DEMO_EVENTS.length} Demo-Ereignisse sind bereits durchlaufen.`);
      }
      return;
    }

    zeigeEreignis(DEMO_EVENTS[currentIndex++]);

    if (isRunning) plan(1200);
  }

  function runAllDemo() {
    if (isRunning) return;
    resetDemo(true);
    isRunning = true;
    plan(200);
  }

  function resetDemo(leise) {
    isRunning = false;
    currentIndex = 0;
    if (laufTimer) { clearTimeout(laufTimer); laufTimer = null; }
    if (pfadTimer) { clearTimeout(pfadTimer); pfadTimer = null; }
    clearHighlights();
    if (eventPathsEl) eventPathsEl.innerHTML = '';
    if (eventLogEl) {
      eventLogEl.innerHTML = '<div class="log-empty">Noch keine Ereignisse. Starte Demo oder warte auf echte Ereignisse.</div>';
    }
    if (eventDetailEl) eventDetailEl.style.display = 'none';
    stats = { allowed: 0, denied: 0, suspicious: 0 };
    if (statAllowedEl) statAllowedEl.textContent = '0';
    if (statDeniedEl) statDeniedEl.textContent = '0';
    if (statSuspiciousEl) statSuspiciousEl.textContent = '0';
    if (!leise) hinweis('Zurückgesetzt.');
  }

  /* Event Listeners */
  const demoRunBtn = document.getElementById('demo-run');
  const demoClearBtn = document.getElementById('demo-clear');
  const demoStepBtn = document.getElementById('demo-step');

  if (demoRunBtn) demoRunBtn.addEventListener('click', runAllDemo);
  if (demoClearBtn) demoClearBtn.addEventListener('click', function () { resetDemo(false); });
  if (demoStepBtn) demoStepBtn.addEventListener('click', function () {
    if (isRunning) return;
    runNextEvent();
  });

  /* Echte Ereignisse: kommen sie aus dem Audit-Log eines Laufes. Wer die
     Seite in eine eigene Oberflaeche einbettet, kann sie als Array mit
     'time', 'type', 'from', 'to', 'action', 'result', 'detail' und
     'real: true' uebergeben - dann werden sie als ECHT markiert. */
  function ladeEchteEreignisse(ereignisse) {
    if (!Array.isArray(ereignisse) || !ereignisse.length) return;
    const badge = document.getElementById('sandbox-real-badge');
    if (badge) badge.style.display = 'inline-block';
    ereignisse.forEach(function (ereignis) {
      zeigeEreignis(Object.assign({ real: true, id: 'r' + ereignisse.indexOf(ereignis) }, ereignis));
    });
    hinweis(`${ereignisse.length} echte Ereignisse geladen.`);
  }

  if (window.AGORIS_EREIGNISSE) ladeEchteEreignisse(window.AGORIS_EREIGNISSE);

  console.log('AGORIS Sandbox Visualization loaded - Demo mode ready');
})();
