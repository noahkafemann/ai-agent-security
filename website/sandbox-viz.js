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
  
  let stats = { allowed: 0, denied: 0, suspicious: 0 };
  let currentIndex = 0;
  let isRunning = false;
  
  function clearHighlights() {
    Object.values(COMPONENTS).forEach(comp => {
      if (comp) comp.classList.remove('highlight', 'allowed', 'denied', 'suspicious');
    });
    if (sandboxBoxEl) sandboxBoxEl.classList.remove('highlight');
    const boundary = document.querySelector('.boundary-zone');
    if (boundary) boundary.classList.remove('highlight');
  }
  
  function highlightComponent(name, result) {
    clearHighlights();
    if (COMPONENTS[name]) {
      COMPONENTS[name].classList.add('highlight', result);
    }
    if (result === 'denied') {
      if (sandboxBoxEl) sandboxBoxEl.classList.add('highlight');
      const boundary = document.querySelector('.boundary-zone');
      if (boundary) boundary.classList.add('highlight');
    }
  }
  
  function drawPath(from, to, result) {
    // Remove old paths
    eventPathsEl.innerHTML = '';
    
    const coords = {
      agent: { x: 200, y: 250 },
      filesystem: { x: 360, y: 235 },
      terminal: { x: 360, y: 310 },
      processes: { x: 460, y: 235 },
      network: { x: 500, y: 260 }
    };
    
    const fromPos = coords[from];
    const toPos = coords[to];
    if (!fromPos || !toPos) return;
    
    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    // Create curved path
    const midX = (fromPos.x + toPos.x) / 2;
    const midY = Math.min(fromPos.y, toPos.y) - 40;
    path.setAttribute('d', `M ${fromPos.x} ${fromPos.y} Q ${midX} ${midY} ${toPos.x} ${toPos.y}`);
    path.setAttribute('class', `event-path path-${result}`);
    eventPathsEl.appendChild(path);
  }
  
  function addEventToLog(event) {
    // Remove empty message
    const empty = eventLogEl.querySelector('.log-empty');
    if (empty) empty.remove();
    
    const item = document.createElement('div');
    item.className = `event-item ${event.result}`;
    item.setAttribute('data-id', event.id);
    
    const realBadge = event.real ? ' <span class="badge real" style="font-size:8px;padding:1px 4px;">ECHT</span>' : ' <span class="badge demo" style="font-size:8px;padding:1px 4px;">DEMO</span>';
    
    item.innerHTML = `
      <div><span class="time">${event.time}</span> ${realBadge}</div>
      <div><span class="type">${event.type}</span> → <span class="target">${event.to.toUpperCase()}</span></div>
      <div>${event.action}</div>
      <div class="result">${event.result.toUpperCase()}</div>
    `;
    
    item.addEventListener('click', () => {
      eventDetailEl.style.display = 'block';
      eventDetailTextEl.textContent = event.detail;
      // Highlight all items
      eventLogEl.querySelectorAll('.event-item').forEach(i => i.style.opacity = '0.5');
      item.style.opacity = '1';
      item.style.background = 'rgba(53, 224, 232, 0.12)';
    });
    
    eventLogEl.insertBefore(item, eventLogEl.firstChild);
  }
  
  function updateStats(result) {
    if (result === 'allowed') stats.allowed++;
    else if (result === 'denied') stats.denied++;
    else if (result === 'suspicious') stats.suspicious++;
    
    statAllowedEl.textContent = stats.allowed;
    statDeniedEl.textContent = stats.denied;
    statSuspiciousEl.textContent = stats.suspicious;
  }
  
  function runNextEvent() {
    if (currentIndex >= DEMO_EVENTS.length) {
      if (isRunning) {
        alert('Demo abgeschlossen. Alle ' + DEMO_EVENTS.length + ' Ereignisse durchlaufen.');
        isRunning = false;
      }
      return;
    }
    
    const event = DEMO_EVENTS[currentIndex++];
    
    highlightComponent(event.to, event.result);
    drawPath(event.from, event.to, event.result);
    addEventToLog(event);
    updateStats(event.result);
    
    // Auto-remove path after animation
    setTimeout(() => {
      eventPathsEl.innerHTML = '';
    }, 2000);
  }
  
  function runAllDemo() {
    if (isRunning) return;
    isRunning = true;
    clearHighlights();
    eventPathsEl.innerHTML = '';
    eventLogEl.innerHTML = '<div class="log-empty">Starte Demo...</div>';
    eventDetailEl.style.display = 'none';
    stats = { allowed: 0, denied: 0, suspicious: 0 };
    statAllowedEl.textContent = '0';
    statDeniedEl.textContent = '0';
    statSuspiciousEl.textContent = '0';
    currentIndex = 0;
    
    DEMO_EVENTS.forEach((event, idx) => {
      setTimeout(() => {
        highlightComponent(event.to, event.result);
        drawPath(event.from, event.to, event.result);
        addEventToLog(event);
        updateStats(event.result);
        setTimeout(() => {
          eventPathsEl.innerHTML = '';
        }, 2000);
      }, idx * 1200);
    });
    
    setTimeout(() => {
      isRunning = false;
    }, DEMO_EVENTS.length * 1200 + 500);
  }
  
  function resetDemo() {
    isRunning = false;
    clearHighlights();
    eventPathsEl.innerHTML = '';
    eventLogEl.innerHTML = '<div class="log-empty">Noch keine Ereignisse. Starte Demo oder warte auf echte Ereignisse.</div>';
    eventDetailEl.style.display = 'none';
    stats = { allowed: 0, denied: 0, suspicious: 0 };
    statAllowedEl.textContent = '0';
    statDeniedEl.textContent = '0';
    statSuspiciousEl.textContent = '0';
    currentIndex = 0;
  }
  
  // Event Listeners
  const demoRunBtn = document.getElementById('demo-run');
  const demoClearBtn = document.getElementById('demo-clear');
  const demoStepBtn = document.getElementById('demo-step');
  
  if (demoRunBtn) demoRunBtn.addEventListener('click', runAllDemo);
  if (demoClearBtn) demoClearBtn.addEventListener('click', resetDemo);
  if (demoStepBtn) demoStepBtn.addEventListener('click', runNextEvent);
  
  // Try to load real events from audit logs if available
  async function tryLoadRealEvents() {
    try {
      // Try to fetch from common locations - in browser context this may not work
      // but structure is prepared for integration
      const badge = document.getElementById('sandbox-real-badge');
      if (badge) {
        // Check if we can detect real events
        // For now, just show demo is working
      }
    } catch (e) {
      // Ignore
    }
  }
  
  tryLoadRealEvents();
  
  console.log('AGORIS Sandbox Visualization loaded - Demo mode ready');
})();
