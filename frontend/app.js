// ==== Device metadata & inline SVG icons ====
const deviceConfig = {
  "light": {
    name: "Bedroom Light",
    type: "Light",
    icon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
      <path d="M12 2a6 6 0 0 0-6 6v7"/>
      <path d="M12 2a6 6 0 0 1 6 6v7"/>
      <path d="M12 22v-7"/>
      <path d="M9 12l3-3 3 3"/>
    </svg>`
  },

  "fan": {
    name: "Fan",
    type: "Fan",
    icon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
      <circle cx="12" cy="12" r="2"/>
      <path d="M12 2v2"/>
      <path d="M12 20v2"/>
      <path d="M4.93 4.93l1.41 1.41"/>
      <path d="M17.66 17.66l1.41 1.41"/>
      <path d="M2 12h2"/>
      <path d="M20 12h2"/>
      <path d="M4.93 19.07l1.41-1.41"/>
      <path d="M17.66 6.34l1.41-1.41"/>
    </svg>`
  },

  "tv": {
    name: "TV",
    type: "Media",
    icon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
      <rect x="2" y="3" width="20" height="14" rx="2"/>
      <path d="M8 21h8"/>
      <path d="M12 17v4"/>
    </svg>`
  },

  "ac": {
    name: "AC",
    type: "Climate",
    icon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
      <path d="M12 4v16"/>
      <path d="M8 8h8"/>
      <path d="M8 16h8"/>
      <path d="M4 12h4"/>
      <path d="M16 12h4"/>
    </svg>`
  },

  "plug": {
    name: "Plug",
    type: "Outlet",
    icon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
      <path d="M12 2v6"/>
      <path d="M8 14h8"/>
      <path d="M8 18h8"/>
      <rect x="4" y="10" width="16" height="10" rx="2"/>
    </svg>`
  },

  "geyser": {
    name: "Geyser",
    type: "Water Heater",
    icon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
      <path d="M12 2a5 5 0 0 1 5 5v5"/>
      <path d="M12 2a5 5 0 0 0-5 5v5"/>
      <path d="M4 16v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"/>
    </svg>`
  },

  "exhaust": {
    name: "Exhaust",
    type: "Ventilation",
    icon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
      <path d="M6 6h16"/>
      <path d="M6 12h12"/>
      <path d="M6 18h8"/>
      <path d="M14 6v12"/>
    </svg>`
  },

  "garden lights": {
    name: "Garden Lights",
    type: "Outdoor",
    icon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
      <circle cx="12" cy="12" r="5"/>
      <path d="M12 1v2"/>
      <path d="M12 21v2"/>
      <path d="M4.22 4.22l1.42 1.42"/>
      <path d="M18.36 18.36l1.42 1.42"/>
      <path d="M1 12h2"/>
      <path d="M21 12h2"/>
      <path d="M4.22 19.78l1.42-1.42"/>
      <path d="M18.36 5.64l1.42-1.42"/>
    </svg>`
  }
};


// ============================================================
// RASPBERRY PI BACKEND
// ============================================================

const API_BASE_URL = "http://10.36.186.119:8000";


// ============================================================
// DOM ELEMENTS
// ============================================================

const grid = document.getElementById("devicesGrid");
const onCountEl = document.getElementById("onCount");
const offCountEl = document.getElementById("offCount");
const lastCmdEl = document.getElementById("lastCommand");
const recogDevEl = document.getElementById("recognizedDevice");
const recogActEl = document.getElementById("recognizedAction");


// ============================================================
// CREATE DEVICE TILE
// ============================================================

function createTile(key, state) {
  const cfg = deviceConfig[key] || {
    name: key,
    type: "",
    icon: ""
  };

  const tile = document.createElement("article");

  tile.className = `tile ${state === "on" ? "on" : "off"}`;
  tile.dataset.key = key;
  tile.setAttribute("role", "listitem");

  tile.innerHTML = `
    <div class="tile-icon">${cfg.icon}</div>

    <div class="tile-name">${cfg.name}</div>

    <div class="tile-type">${cfg.type}</div>

    <span class="state-badge ${state === "on" ? "on" : "off"}">
      ${state.toUpperCase()}
    </span>
  `;

  return tile;
}


// ============================================================
// UPDATE ON/OFF COUNTS
// ============================================================

function updateCounts(appliances) {
  const on = appliances.filter(
    appliance => appliance.state === "on"
  ).length;

  const off = appliances.length - on;

  if (onCountEl) {
    onCountEl.textContent = on;
  }

  if (offCountEl) {
    offCountEl.textContent = off;
  }
}


// ============================================================
// FETCH STATUS FROM RASPBERRY PI
// ============================================================

async function fetchStatus() {
  try {
    const response = await fetch(
      `${API_BASE_URL}/api/status`
    );

    if (!response.ok) {
      throw new Error(
        `HTTP ${response.status} ${response.statusText}`
      );
    }

    const data = await response.json();

    console.log("Pi status:", data);

    if (!data.appliances) {
      throw new Error(
        "Backend response does not contain 'appliances'"
      );
    }

    grid.innerHTML = "";

    for (const appliance of data.appliances) {
      grid.appendChild(
        createTile(
          appliance.appliance,
          appliance.state
        )
      );
    }

    updateCounts(data.appliances);

  } catch (error) {
    console.error(
      "Failed to fetch Raspberry Pi status:",
      error
    );
  }
}


// ============================================================
// VOICE ACTIVITY
// ============================================================

function setVoiceActivity({
  lastCommand = "",
  device = "",
  action = ""
}) {
  if (lastCmdEl) {
    lastCmdEl.textContent =
      lastCommand || "Waiting for voice command…";
  }

  if (recogDevEl) {
    recogDevEl.textContent =
      device || "—";
  }

  if (recogActEl) {
    recogActEl.textContent =
      action || "—";
  }
}


// ============================================================
// INITIAL LOAD
// ============================================================

console.log(
  "Home Automation frontend started"
);

console.log(
  "Backend:",
  API_BASE_URL
);

fetchStatus();

setVoiceActivity({});


// ============================================================
// LIVE POLLING
// Refresh dashboard every 2 seconds
// ============================================================

setInterval(
  fetchStatus,
  2000
);