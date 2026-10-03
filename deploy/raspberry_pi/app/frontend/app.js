// ==== Device metadata & inline SVG icons ====
const deviceConfig = {
  "light":        { name: "Bedroom Light", type: "Light",        icon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2a6 6 0 0 0-6 6v7"/><path d="M12 2a6 6 0 0 1 6 6v7"/><path d="M12 22v-7"/><path d="M9 12l3-3 3 3"/></svg>` },
  "fan":          { name: "Fan",           type: "Fan",          icon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="2"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="M4.93 4.93l1.41 1.41"/><path d="M17.66 17.66l1.41 1.41"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="M4.93 19.07l1.41-1.41"/><path d="M17.66 6.34l1.41-1.41"/></svg>` },
  "tv":           { name: "TV",            type: "Media",        icon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8"/><path d="M12 17v4"/></svg>` },
  "ac":           { name: "AC",            type: "Climate",      icon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M12 4v16"/><path d="M8 8h8"/><path d="M8 16h8"/><path d="M4 12h4"/><path d="M16 12h4"/></svg>` },
  "plug":         { name: "Plug",          type: "Outlet",       icon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2v6"/><path d="M8 14h8"/><path d="M8 18h8"/><rect x="4" y="10" width="16" height="10" rx="2"/></svg>` },
  "geyser":       { name: "Geyser",        type: "Water Heater", icon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2a5 5 0 0 1 5 5v5"/><path d="M12 2a5 5 0 0 0-5 5v5"/><path d="M4 16v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"/></svg>` },
  "exhaust":      { name: "Exhaust",       type: "Ventilation",  icon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M6 6h16"/><path d="M6 12h12"/><path d="M6 18h8"/><path d="M14 6v12"/></svg>` },
  "garden lights":{ name: "Garden Lights", type: "Outdoor",      icon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"/><path d="M12 1v2"/><path d="M12 21v2"/><path d="M4.22 4.22l1.42 1.42"/><path d="M18.36 18.36l1.42 1.42"/><path d="M1 12h2"/><path d="M21 12h2"/><path d="M4.22 19.78l1.42-1.42"/><path d="M18.36 5.64l1.42-1.42"/></svg>` }
};

const grid = document.getElementById('devicesGrid');
const onCountEl = document.getElementById('onCount');
const offCountEl = document.getElementById('offCount');
const lastCmdEl = document.getElementById('lastCommand');
const recogDevEl = document.getElementById('recognizedDevice');
const recogActEl = document.getElementById('recognizedAction');

function createTile(key, state) {
  const cfg = deviceConfig[key] || { name: key, type: "", icon: "" };
  const tile = document.createElement('article');
  tile.className = `tile ${state === 'on' ? 'on' : 'off'}`;
  tile.dataset.key = key;
  tile.setAttribute('role', 'listitem');
  tile.innerHTML = `
    <div class="tile-icon">${cfg.icon}</div>
    <div class="tile-name">${cfg.name}</div>
    <div class="tile-type">${cfg.type}</div>
    <span class="state-badge ${state === 'on' ? 'on' : 'off'}">${state.toUpperCase()}</span>
  `;
  return tile;
}

function updateCounts(appliances) {
  const on = appliances.filter(a => a.state === 'on').length;
  const off = appliances.length - on;
  onCountEl.textContent = on;
  offCountEl.textContent = off;
}

async function fetchStatus() {
  try {
    const res = await fetch('/api/status');
    if (!res.ok) throw new Error('Network error');
    const data = await res.json();
    grid.innerHTML = '';
    for (const app of data.appliances) {
      grid.appendChild(createTile(app.appliance, app.state));
    }
    updateCounts(data.appliances);
  } catch (e) {
    console.error('Failed to fetch status', e);
  }
}

/* Voice activity placeholder – will stay static until a dedicated endpoint exists.
   If you later add an endpoint (e.g. /api/last-command) replace the static
   strings below with a fetch to that endpoint. */
function setVoiceActivity({lastCommand = '', device = '', action = ''}) {
  lastCmdEl.textContent = lastCommand || 'Waiting for voice command…';
  recogDevEl.textContent = device || '—';
  recogActEl.textContent = action || '—';
}

// initial load
fetchStatus();
setVoiceActivity({});
// poll every 2 s
setInterval(fetchStatus, 2000);