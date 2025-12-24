const form = document.getElementById('cfgForm');
const rigList = document.getElementById('rigList');
const addRigBtn = document.getElementById('addRig');

const rigctlHostSelect = document.getElementById('rigctlHost');
const rigctlPortInput = document.getElementById('rigctlPort');

const activeProfileNameEl = document.getElementById('activeProfileName');
const profileSelectBtn = document.getElementById('profileSelectBtn');
const profileAddBtn = document.getElementById('profileAddBtn');
const profileRenameBtn = document.getElementById('profileRenameBtn');
const profileDuplicateBtn = document.getElementById('profileDuplicateBtn');
const profileDeleteBtn = document.getElementById('profileDeleteBtn');
const profileResult = document.getElementById('profileResult');
const configExportBtn = document.getElementById('configExport');
const configImportInput = document.getElementById('configImport');
const configImportBtn = document.getElementById('configImportBtn');

const profileSelectDialog = document.getElementById('profileSelectDialog');
const profileSelectChoice = document.getElementById('profileSelectChoice');
const profileSelectConfirm = document.getElementById('profileSelectConfirm');

const profileAddDialog = document.getElementById('profileAddDialog');
const profileAddName = document.getElementById('profileAddName');
const profileAddConfirm = document.getElementById('profileAddConfirm');

const profileRenameDialog = document.getElementById('profileRenameDialog');
const profileRenameOld = document.getElementById('profileRenameOld');
const profileRenameNew = document.getElementById('profileRenameNew');
const profileRenameConfirm = document.getElementById('profileRenameConfirm');

const profileDuplicateDialog = document.getElementById('profileDuplicateDialog');
const profileDuplicateFrom = document.getElementById('profileDuplicateFrom');
const profileDuplicateNew = document.getElementById('profileDuplicateNew');
const profileDuplicateStep1 = document.getElementById('profileDuplicateStep1');
const profileDuplicateStep2 = document.getElementById('profileDuplicateStep2');
const profileDuplicateBack = document.getElementById('profileDuplicateBack');
const profileDuplicateNext = document.getElementById('profileDuplicateNext');
const profileDuplicateConfirm = document.getElementById('profileDuplicateConfirm');

const profileDeleteDialog = document.getElementById('profileDeleteDialog');
const profileDeleteChoice = document.getElementById('profileDeleteChoice');
const profileDeleteConfirm = document.getElementById('profileDeleteConfirm');

let rigs = [];
let syncEnabled = true;
let syncSourceIndex = 0;
let rigctlToMainEnabled = true;
let rigModels = []; // Will be loaded from JSON

let suppressAutosave = false;
let autosaveTimer = null;
let autosaveInFlight = false;
let autosavePending = false;
let activeProfileName = '';

function bandLimits(label) {
  const key = String(label || '').trim().toLowerCase();
  const table = {
    '160m': [1800000, 2000000],
    '80m': [3500000, 4000000],
    '60m': [5330000, 5406000],
    '40m': [7000000, 7300000],
    '30m': [10100000, 10150000],
    '20m': [14000000, 14350000],
    '17m': [18068000, 18168000],
    '15m': [21000000, 21450000],
    '12m': [24890000, 24990000],
    '10m': [28000000, 29700000],
    '6m': [50000000, 54000000],
    '2m': [144000000, 148000000],
    '1.25m': [222000000, 225000000],
    '70cm': [420000000, 450000000],
    '33cm': [902000000, 928000000],
    '23cm': [1240000000, 1300000000],
  };
  return table[key] || null;
}

function setProfileResult(msg, ok) {
  if (!profileResult) return;
  profileResult.textContent = msg || '';
  profileResult.style.color = ok ? '#0a7b2f' : '#a40000';
  if (msg) {
    setTimeout(() => {
      if (profileResult.textContent === msg) profileResult.textContent = '';
    }, 4000);
  }
}

function hasActiveProfile() {
  return !!String(activeProfileName || '').trim();
}

function setActiveProfileName(name) {
  activeProfileName = String(name || '').trim();
  if (activeProfileNameEl) activeProfileNameEl.textContent = activeProfileName || '(none)';
}

function buildConfigFromDom() {
  const fsList = Array.from(rigList.querySelectorAll('fieldset'));
  const newRigs = fsList.map((fs) => {
    const get = (sel) => fs.querySelector(sel);
    const val = (sel) => (get(sel)?.value ?? '').trim();
    const asNum = (sel) => {
      const v = val(sel);
      return v === '' ? null : Number(v);
    };
    const ct = val('select[data-key="connection_type"]') || 'hamlib';

    const bandRows = Array.from(fs.querySelectorAll('.band-row'));
    const band_presets = bandRows.map((row) => {
      const label = (row.getAttribute('data-label') || '').trim();
      const enabled = !!row.querySelector('input[data-role="band-enabled"]')?.checked;
      const hz = Number(row.querySelector('input[data-role="band-hz"]')?.value || 0);
      const lower_hz = Number(row.querySelector('input[data-role="band-lo"]')?.value || 0);
      const upper_hz = Number(row.querySelector('input[data-role="band-hi"]')?.value || 0);
      return { label, frequency_hz: hz, enabled, lower_hz, upper_hz };
    }).filter((p) => p.label);

    return {
      name: val('input[data-key="name"]') || 'Rig',
      poll_interval_ms: Number(val('input[data-key="poll_interval_ms"]') || 1000),
      allow_out_of_band: !!get('input[data-key="allow_out_of_band"]')?.checked,
      connection_type: ct,
      host: val('input[data-key="host"]') || '127.0.0.1',
      port: Number(val('input[data-key="port"]') || (4532)),
      model_id: asNum('select[data-key="model_id"]'),
      device: val('input[data-key="device"]') || null,
      baud: asNum('input[data-key="baud"]'),
      serial_opts: val('input[data-key="serial_opts"]') || null,
      extra_args: val('input[data-key="extra_args"]') || null,
      band_presets,
      color: val('input[data-key="color"]') || '#a4c356',
      inverted: !!get('input[data-key="inverted"]')?.checked,
    };
  });
  const poll = Number(form.querySelector('input[name="poll"]').value || 1000);
  return {
    rigs: newRigs,
    rigctl_listen_host: (rigctlHostSelect.value || '127.0.0.1').trim(),
    rigctl_listen_port: Number(rigctlPortInput.value || 4534),
    rigctl_to_main_enabled: rigctlToMainEnabled,
    poll_interval_ms: poll,
    sync_enabled: syncEnabled,
    sync_source_index: syncSourceIndex
  };
}

async function applyConfigFromDom() {
  const body = buildConfigFromDom();
  const res = await fetch('/api/config', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });
  const json = await res.json();
  const saveEl = document.getElementById('saveResult');
  if (saveEl) saveEl.textContent = json.status === 'ok' ? 'Saved' : 'Failed';
  return json;
}

async function saveSelectedProfile() {
  const name = String(activeProfileName || '').trim();
  if (!name) return { status: 'skipped' };
  const res = await fetch(`/api/config/profiles/${encodeURIComponent(name)}`, { method: 'POST' });
  const json = await res.json();
  return json;
}

async function autosaveNow() {
  if (autosaveInFlight) {
    autosavePending = true;
    return;
  }
  autosaveInFlight = true;
  autosavePending = false;
  try {
    const applyRes = await applyConfigFromDom();
    if (applyRes?.status !== 'ok') {
      setProfileResult(applyRes?.error || 'Save failed', false);
      return;
    }
    if (hasActiveProfile()) {
      const profRes = await saveSelectedProfile();
      if (profRes?.status !== 'ok' && profRes?.status !== 'skipped') {
        setProfileResult(profRes?.error || 'Profile save failed', false);
      }
    }
  } catch (e) {
    setProfileResult('Save failed', false);
  } finally {
    autosaveInFlight = false;
    if (autosavePending) {
      autosavePending = false;
      await autosaveNow();
    }
  }
}

function scheduleAutosave() {
  if (suppressAutosave) return;
  if (!hasActiveProfile()) return;
  if (autosaveTimer) clearTimeout(autosaveTimer);
  autosaveTimer = setTimeout(() => {
    autosaveTimer = null;
    autosaveNow();
  }, 700);
}

async function fetchProfileNames() {
  const res = await fetch('/api/config/profiles', { cache: 'no-store' });
  const json = await res.json();
  return (json && Array.isArray(json.profiles)) ? json.profiles.map((n) => String(n)) : [];
}

function populateSelect(selectEl, list, selectedName, includeEmpty) {
  if (!selectEl) return;
  selectEl.innerHTML = '';
  if (includeEmpty) {
    const opt0 = document.createElement('option');
    opt0.value = '';
    opt0.textContent = 'Select…';
    selectEl.appendChild(opt0);
  }
  list.forEach((name) => {
    const opt = document.createElement('option');
    opt.value = name;
    opt.textContent = name;
    if (selectedName && name === selectedName) opt.selected = true;
    selectEl.appendChild(opt);
  });
}

async function refreshProfileChoices() {
  try {
    const list = await fetchProfileNames();
    populateSelect(profileSelectChoice, list, activeProfileName, false);
    populateSelect(profileRenameOld, list, activeProfileName, false);
    populateSelect(profileDuplicateFrom, list, activeProfileName, false);
    populateSelect(profileDeleteChoice, list, activeProfileName, false);
  } catch (e) {
    populateSelect(profileSelectChoice, [], '', false);
    populateSelect(profileRenameOld, [], '', false);
    populateSelect(profileDuplicateFrom, [], '', false);
    populateSelect(profileDeleteChoice, [], '', false);
  }
}

async function refreshActiveProfileName() {
  try {
    const res = await fetch('/api/config/active_profile', { cache: 'no-store' });
    const json = await res.json();
    if (json && json.status === 'ok') {
      setActiveProfileName(json.name);
    }
  } catch { }
}

async function loadProfileByName(name) {
  const n = String(name || '').trim();
  if (!n) return;
  const res = await fetch(`/api/config/profiles/${encodeURIComponent(n)}/load`, { method: 'POST' });
  const json = await res.json();
  if (json && json.status === 'ok') {
    setActiveProfileName(n);
    await loadConfig();
    await refreshActiveProfileName();
    await refreshProfileChoices();
    setProfileResult('Loaded profile', true);
  } else {
    setProfileResult(json?.error || 'Load failed', false);
  }
}

async function createProfileByName(name) {
  const n = String(name || '').trim();
  if (!n) {
    setProfileResult('Enter a profile name', false);
    return false;
  }
  const res = await fetch(`/api/config/profiles/${encodeURIComponent(n)}/create`, { method: 'POST' });
  const json = await res.json();
  if (json && json.status === 'ok') {
    return true;
  }
  setProfileResult(json?.error || 'Create failed', false);
  return false;
}

async function renameProfile(oldName, newName) {
  const oldN = String(oldName || '').trim();
  const newN = String(newName || '').trim();
  if (!oldN || !newN) {
    setProfileResult('Select a profile and enter a new name', false);
    return false;
  }
  const res = await fetch(`/api/config/profiles/${encodeURIComponent(oldN)}/rename`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ new_name: newN }),
  });
  const json = await res.json();
  if (json && json.status === 'ok') {
    await refreshActiveProfileName();
    await refreshProfileChoices();
    setProfileResult('Renamed profile', true);
    return true;
  }
  setProfileResult(json?.error || 'Rename failed', false);
  return false;
}

async function duplicateProfile(fromName, newName) {
  const fromN = String(fromName || '').trim();
  const newN = String(newName || '').trim();
  if (!fromN || !newN) {
    setProfileResult('Select a profile and enter a new name', false);
    return false;
  }
  const res = await fetch(`/api/config/profiles/${encodeURIComponent(fromN)}/duplicate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ new_name: newN }),
  });
  const json = await res.json();
  if (json && json.status === 'ok') {
    await loadProfileByName(newN);
    return true;
  }
  setProfileResult(json?.error || 'Duplicate failed', false);
  return false;
}

async function deleteProfileByName(name) {
  const n = String(name || '').trim();
  if (!n) {
    setProfileResult('Select a profile', false);
    return false;
  }
  const ok = window.confirm(`Delete profile "${n}"?`);
  if (!ok) return false;
  const res = await fetch(`/api/config/profiles/${encodeURIComponent(n)}`, { method: 'DELETE' });
  const json = await res.json();
  if (json && json.status === 'ok') {
    await refreshActiveProfileName();
    await refreshProfileChoices();
    await loadConfig();
    setProfileResult('Deleted profile', true);
    return true;
  }
  setProfileResult(json?.error || 'Delete failed', false);
  return false;
}

async function exportCurrentConfig() {
  try {
    const res = await fetch('/api/config/export', { cache: 'no-store' });
    const text = await res.text();
    const blob = new Blob([text], { type: 'text/yaml' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'multirig.config.yaml';
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  } catch (e) {
    setProfileResult('Export failed', false);
  }
}

async function importConfigFile(file) {
  if (!file) return;
  try {
    const text = await file.text();
    const res = await fetch('/api/config/import', {
      method: 'POST',
      headers: { 'Content-Type': 'text/yaml' },
      body: text,
    });
    const json = await res.json();
    if (json && json.status === 'ok') {
      await loadConfig();
      setProfileResult('Imported config', true);
      await refreshActiveProfileName();
      await refreshProfileChoices();
    } else {
      setProfileResult(json?.error || 'Import failed', false);
    }
  } catch (e) {
    setProfileResult('Import failed', false);
  } finally {
    if (configImportInput) configImportInput.value = '';
  }
}

function knownBandLabels() {
  return ['160m', '80m', '60m', '40m', '30m', '20m', '17m', '15m', '12m', '10m', '6m', '2m', '1.25m', '70cm', '33cm', '23cm'];
}

function collectRigConfig(fieldset) {
  const get = (sel) => fieldset.querySelector(sel);
  const val = (sel) => (get(sel)?.value ?? '').trim();
  const asNum = (sel) => {
    const v = val(sel);
    return v === '' ? null : Number(v);
  };

  const connectionType = val('select[data-key="connection_type"]') || 'hamlib';
  return {
    name: val('input[data-key="name"]') || 'Test Rig',
    poll_interval_ms: Number(val('input[data-key="poll_interval_ms"]') || 1000),
    connection_type: connectionType,
    host: val('input[data-key="host"]') || '127.0.0.1',
    port: Number(val('input[data-key="port"]') || 4532),
    model_id: asNum('select[data-key="model_id"]'),
    device: val('input[data-key="device"]') || null,
    baud: asNum('input[data-key="baud"]'),
    serial_opts: val('input[data-key="serial_opts"]') || null,
    extra_args: val('input[data-key="extra_args"]') || null,
    inverted: !!get('input[data-key="inverted"]')?.checked,
  };
}

function defaultBandFrequency(label) {
  const key = String(label || '').trim().toLowerCase();
  const table = {
    '160m': 1900000,
    '80m': 3700000,
    '60m': 5364000,
    '40m': 7074000,
    '30m': 10136000,
    '20m': 14074000,
    '17m': 18100000,
    '15m': 21074000,
    '12m': 24915000,
    '10m': 28074000,
    '6m': 50125000,
    '2m': 145000000,
    '1.25m': 223500000,
    '70cm': 432100000,
    '33cm': 903000000,
    '23cm': 1296000000,
  };
  return table[key] || 0;
}

function defaultBandPresets() {
  const mk = (label, frequency_hz) => {
    const lim = bandLimits(label);
    const lower_hz = lim ? lim[0] : null;
    const upper_hz = lim ? lim[1] : null;
    return { label, frequency_hz, enabled: true, lower_hz, upper_hz };
  };
  return knownBandLabels().map((label) => mk(label, defaultBandFrequency(label)));
}

function ensureBandPresets(rig) {
  if (!rig) return defaultBandPresets();
  if (Array.isArray(rig.band_presets) && rig.band_presets.length) return rig.band_presets;
  return defaultBandPresets();
}

function bandPresetsSectionKey(idx) {
  return `multirig.settings.rig.${idx}.band_presets.collapsed`;
}

function getBandPresetsCollapsed(idx) {
  try {
    const v = localStorage.getItem(bandPresetsSectionKey(idx));
    if (v == null) return true;
    return v === '1';
  } catch {
    return true;
  }
}

function setBandPresetsCollapsed(idx, collapsed) {
  try {
    localStorage.setItem(bandPresetsSectionKey(idx), collapsed ? '1' : '0');
  } catch { }
}

function renderBandPresets(container, presets) {
  if (!container) return;
  const list = Array.isArray(presets) && presets.length ? presets : defaultBandPresets();
  container.innerHTML = '';
  const title = document.createElement('div');
  title.className = 'band-presets-title';
  title.textContent = 'Band presets (shown on dashboard)';
  container.appendChild(title);

  const actions = document.createElement('div');
  actions.className = 'band-presets-actions';
  actions.innerHTML = `
        <label class="band-add">
          <span class="band-add-label">Add band</span>
          <select data-role="band-add-select"></select>
        </label>
        <button type="button" data-action="band-add" class="band-add-btn">Add</button>
        <button type="button" data-action="band-reset" class="band-reset-btn">Reset to Default</button>
      `;
  container.appendChild(actions);

  const rows = document.createElement('div');
  rows.className = 'band-presets-rows';

  const addSelect = actions.querySelector('[data-role="band-add-select"]');
  const addBtn = actions.querySelector('[data-action="band-add"]');

  const rebuildOptions = () => {
    const existing = new Set(Array.from(rows.querySelectorAll('.band-row')).map(r => (r.getAttribute('data-label') || '').trim()));
    const options = knownBandLabels().filter(l => !existing.has(l));
    if (addSelect) {
      addSelect.innerHTML = '';
      const opt0 = document.createElement('option');
      opt0.value = '';
      opt0.textContent = options.length ? 'Select…' : 'No more bands';
      addSelect.appendChild(opt0);
      options.forEach(l => {
        const opt = document.createElement('option');
        opt.value = l;
        opt.textContent = l;
        addSelect.appendChild(opt);
      });
      addSelect.disabled = options.length === 0;
    }
    if (addBtn) addBtn.disabled = options.length === 0;
  };

  const addRow = (p) => {
    const label = String(p.label || '').trim();
    if (!label) return;
    const lim = bandLimits(label);
    const lower_hz = Number(p.lower_hz ?? (lim ? lim[0] : 0));
    const upper_hz = Number(p.upper_hz ?? (lim ? lim[1] : 0));
    const row = document.createElement('div');
    row.className = 'band-row';
    row.dataset.label = label;
    row.innerHTML = `
          <label class="band-enabled">
            <input type="checkbox" data-role="band-enabled" ${p.enabled === false ? '' : 'checked'}>
            <span>${label}</span>
          </label>
          <label class="band-freq">
            <input type="number" data-role="band-hz" min="0" step="1" value="${Number(p.frequency_hz || 0)}">
            <span class="band-unit">Hz</span>
          </label>
          <label class="band-range">
            <span class="band-range-label">Lo</span>
            <input type="number" data-role="band-lo" min="0" step="1" value="${lower_hz}">
            <span class="band-range-label">Hi</span>
            <input type="number" data-role="band-hi" min="0" step="1" value="${upper_hz}">
          </label>
          <button type="button" class="band-remove" data-action="band-remove">Remove</button>
        `;
    rows.appendChild(row);
  };

  list.forEach((p) => {
    addRow(p);
  });
  container.appendChild(rows);

  rows.addEventListener('click', (e) => {
    const btn = e.target.closest('button[data-action="band-remove"]');
    if (!btn) return;
    const row = btn.closest('.band-row');
    if (row) row.remove();
    rebuildOptions();
  });

  if (addBtn) {
    addBtn.addEventListener('click', () => {
      const label = String(addSelect?.value || '').trim();
      if (!label) return;
      const lim = bandLimits(label);
      addRow({
        label,
        enabled: true,
        frequency_hz: defaultBandFrequency(label),
        lower_hz: lim ? lim[0] : null,
        upper_hz: lim ? lim[1] : null,
      });
      rebuildOptions();
    });
  }

  const resetBtn = actions.querySelector('[data-action="band-reset"]');
  if (resetBtn) {
    resetBtn.addEventListener('click', async () => {
      const prevText = resetBtn.textContent;
      resetBtn.disabled = true;
      resetBtn.textContent = 'Resetting...';

      let nextPresets = null;
      try {
        const fieldset = container.closest('fieldset');
        if (fieldset) {
          const rigConfig = collectRigConfig(fieldset);
          const res = await fetch('/api/test-rig', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(rigConfig),
          });
          const result = await res.json();

          const modelId = fieldset.querySelector('select[data-key="model_id"]')?.value;
          if (modelId != null && String(modelId).trim() !== '' && result && result.caps && typeof result.caps === 'object') {
            const model = getModelById(modelId);
            if (model) {
              model.caps = result.caps;
              if (Array.isArray(result.modes)) model.modes = result.modes;
            }
          }
          if (result?.detected_bands && Array.isArray(result.detected_bands) && result.detected_bands.length) {
            nextPresets = result.detected_bands;
          }
        }
      } catch { }

      if (!nextPresets) {
        nextPresets = defaultBandPresets();
      }

      rows.innerHTML = '';
      nextPresets.forEach((p) => {
        addRow(p);
      });

      resetBtn.disabled = false;
      resetBtn.textContent = prevText;
    });
  }

  rebuildOptions();
}

/**
 * Get a rig model by ID.
 * @param {number|string} modelId - The model ID to look up.
 * @returns {Object|null} The model object or null if not found.
 */
function getModelById(modelId) {
  const id = Number(modelId);
  if (!Number.isFinite(id)) return null;
  return rigModels.find(m => Number(m.id) === id) || null;
}

/**
 * Format read/write capability flags.
 * @param {boolean} getOk - Whether read is supported.
 * @param {boolean} setOk - Whether write is supported.
 * @returns {string} 'RW', 'R', 'W', or empty string.
 */
function formatRw(getOk, setOk) {
  if (getOk && setOk) return 'RW';
  if (getOk) return 'R';
  if (setOk) return 'W';
  return '';
}

/**
 * Render capability badges for a rig model.
 * @param {HTMLElement} el - Container element for badges.
 * @param {number|string} modelId - The model ID.
 */
function renderCapsBadges(el, modelId) {
  if (!el) return;
  if (modelId === null || modelId === undefined || String(modelId).trim() === '') {
    el.innerHTML = '<span class="cap-badge cap-unknown" title="Capabilities are not available until a model is selected.">Caps unknown</span>';
    return;
  }
  const model = getModelById(modelId);
  const caps = model && model.caps ? model.caps : null;
  if (!caps) {
    el.innerHTML = '<span class="cap-badge cap-unknown" title="No capability data is available for this model.">Caps unknown</span>';
    return;
  }
  const descByLabel = {
    'Freq': 'Frequency control',
    'Mode': 'Mode control',
    'VFO': 'VFO control',
    'PTT': 'Transmit (PTT) control',
  };
  const items = [
    { label: 'Freq', g: 'freq_get', s: 'freq_set' },
    { label: 'Mode', g: 'mode_get', s: 'mode_set' },
    { label: 'VFO', g: 'vfo_get', s: 'vfo_set' },
    { label: 'PTT', g: 'ptt_get', s: 'ptt_set' },
  ];
  el.innerHTML = '';
  items.forEach(it => {
    const getOk = !!caps[it.g];
    const setOk = !!caps[it.s];
    const any = getOk || setOk;
    const badge = document.createElement('span');
    badge.className = 'cap-badge ' + (any ? 'cap-on' : 'cap-off');
    const rw = formatRw(getOk, setOk);
    badge.textContent = it.label + (rw ? ` ${rw}` : '');
    const rwText = (getOk && setOk)
      ? 'RW = can read and set'
      : (getOk ? 'R = can read' : (setOk ? 'W = can set' : 'Not supported'));
    badge.title = `${descByLabel[it.label] || it.label}. ${rwText}. (get=${getOk ? 'Y' : 'N'}, set=${setOk ? 'Y' : 'N'})`;
    el.appendChild(badge);
  });
}

/**
 * Render mode badges for a rig model.
 * @param {HTMLElement} el - Container element for badges.
 * @param {number|string} modelId - The model ID.
 */
function renderModesBadges(el, modelId) {
  if (!el) return;
  if (modelId === null || modelId === undefined || String(modelId).trim() === '') {
    el.innerHTML = '';
    return;
  }
  const model = getModelById(modelId);
  const modes = model && Array.isArray(model.modes) ? model.modes : null;
  if (!modes || modes.length === 0) {
    el.innerHTML = '<span class="mode-badge mode-unknown" title="No supported mode list is available for this model.">Modes unknown</span>';
    return;
  }

  const modeMeanings = {
    'AM': 'Amplitude Modulation',
    'AM-D': 'Amplitude Modulation (Digital)',
    'AMN': 'Amplitude Modulation (Narrow)',
    'CW': 'Morse Code (CW)',
    'CWR': 'Morse Code (CW) Reverse',
    'USB': 'Upper Side Band',
    'LSB': 'Lower Side Band',
    'DSB': 'Double Side Band',
    'FM': 'Frequency Modulation',
    'FMN': 'Frequency Modulation (Narrow)',
    'WFM': 'Wide Frequency Modulation',
    'RTTY': 'Radioteletype (RTTY)',
    'RTTYR': 'Radioteletype (RTTY) Reverse',
    'PKTLSB': 'Packet (LSB)',
    'PKTUSB': 'Packet (USB)',
    'PKT': 'Packet',
    'FAX': 'Facsimile',
    'SAM': 'Synchronous AM',
    'SAL': 'Synchronous AM (Lower side)',
    'SAH': 'Synchronous AM (Upper side)',
    'ECSSUSB': 'ECSS (USB)',
    'ECSSLSB': 'ECSS (LSB)',
    'D-STAR': 'D-STAR Digital Voice',
    'P25': 'APCO Project 25',
    'NXDN-VN': 'NXDN Voice Narrow',
    'NXDN-N': 'NXDN Narrow',
    'DPMR': 'dPMR',
    'DCR': 'Digital (DCR)',
    'PSK': 'Phase Shift Keying (PSK)',
    'PSKR': 'Phase Shift Keying (PSK) Reverse',
  };

  el.innerHTML = '';
  modes.forEach((m) => {
    const badge = document.createElement('span');
    badge.className = 'mode-badge';
    badge.textContent = m;
    const meaning = modeMeanings[m];
    badge.title = meaning ? `${m}: ${meaning}` : `Mode: ${m}`;
    el.appendChild(badge);
  });
}

async function loadBindAddrs() {
  try {
    const res = await fetch('/api/bind_addrs');
    const addrs = await res.json();
    rigctlHostSelect.innerHTML = '';
    const preferred = ['127.0.0.1', '0.0.0.0'];
    const seen = new Set();
    preferred.concat(addrs || []).forEach(ip => {
      if (!ip || seen.has(ip)) return;
      seen.add(ip);
      const opt = document.createElement('option');
      opt.value = ip;
      opt.textContent = ip;
      rigctlHostSelect.appendChild(opt);
    });
  } catch (e) {
    rigctlHostSelect.innerHTML = '';
    ['127.0.0.1', '0.0.0.0'].forEach(ip => {
      const opt = document.createElement('option');
      opt.value = ip;
      opt.textContent = ip;
      rigctlHostSelect.appendChild(opt);
    });
  }
}

// Load rig models from JSON
async function loadRigModels() {
  try {
    const res = await fetch('/static/rig_models.json?ts=' + Date.now(), { cache: 'no-store' });
    rigModels = await res.json();
  } catch (e) {
    console.error('Failed to load rig models:', e);
  }
}

function createModelSelect(currentModelId) {
  const select = document.createElement('select');
  select.setAttribute('data-key', 'model_id');

  // Add empty option
  const emptyOpt = document.createElement('option');
  emptyOpt.value = '';
  emptyOpt.textContent = 'Select a rig model...';
  select.appendChild(emptyOpt);

  // Add all models
  rigModels.forEach(model => {
    const opt = document.createElement('option');
    opt.value = model.id;
    opt.textContent = model.label;
    if (Number(model.id) === Number(currentModelId)) {
      opt.selected = true;
    }
    select.appendChild(opt);
  });

  return select;
}

async function testRigConnection(fieldset) {
  const resultDiv = fieldset.querySelector('.test-result');
  const testBtn = fieldset.querySelector('[data-action="test"]');

  // Disable test button and show loading
  testBtn.disabled = true;
  testBtn.textContent = 'Testing...';
  resultDiv.style.display = 'block';
  resultDiv.classList.remove('loading', 'success', 'warning', 'error');
  resultDiv.classList.add('loading');
  resultDiv.textContent = 'Testing connection...';

  const rigConfig = collectRigConfig(fieldset);

  try {
    const res = await fetch('/api/test-rig', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(rigConfig)
    });
    const result = await res.json();

    // Display result
    if (result.status === 'success') {
      resultDiv.classList.remove('loading', 'warning', 'error');
      resultDiv.classList.add('success');
      resultDiv.textContent = result.message;

      // If a profile is selected and the connection test succeeds, persist the current config.
      // This applies the config to the running server and then saves it into the selected profile.
      if (hasActiveProfile()) {
        await autosaveNow();
      }
    } else if (result.status === 'warning') {
      resultDiv.classList.remove('loading', 'success', 'error');
      resultDiv.classList.add('warning');
      resultDiv.textContent = result.message;
    } else {
      resultDiv.classList.remove('loading', 'success', 'warning');
      resultDiv.classList.add('error');
      resultDiv.textContent = result.message;
    }
  } catch (error) {
    resultDiv.classList.remove('loading', 'success', 'warning');
    resultDiv.classList.add('error');
    resultDiv.textContent = `Test failed: ${error.message}`;
  } finally {
    testBtn.disabled = false;
    testBtn.textContent = 'Test Connection';
  }
}

async function refreshRigCaps(fieldset) {
  const btn = fieldset.querySelector('[data-action="caps"]');
  const resultDiv = fieldset.querySelector('.test-result');
  if (!btn) return;

  const prevText = btn.textContent;
  btn.disabled = true;
  btn.textContent = 'Getting...';
  if (resultDiv) {
    resultDiv.style.display = 'block';
    resultDiv.classList.remove('loading', 'success', 'warning', 'error');
    resultDiv.classList.add('loading');
    resultDiv.textContent = 'Fetching capabilities (dump_caps)...';
  }

  try {
    const rigConfig = collectRigConfig(fieldset);
    const res = await fetch('/api/test-rig', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(rigConfig)
    });
    const result = await res.json();

    const modelId = fieldset.querySelector('select[data-key="model_id"]')?.value;
    if (modelId == null || String(modelId).trim() === '') {
      throw new Error('Select a model first');
    }

    if (!result || !result.caps || typeof result.caps !== 'object') {
      throw new Error('No caps returned');
    }

    const model = getModelById(modelId);
    if (!model) {
      throw new Error('Model not found');
    }
    model.caps = result.caps;
    if (Array.isArray(result.modes)) model.modes = result.modes;

    // Re-render badges.
    try {
      const capsEl = fieldset.querySelector('[data-role="caps"]');
      const modesEl = fieldset.querySelector('[data-role="modes"]');
      renderCapsBadges(capsEl, modelId);
      renderModesBadges(modesEl, modelId);
    } catch { }

    if (resultDiv) {
      resultDiv.classList.remove('loading', 'warning', 'error');
      resultDiv.classList.add('success');
      resultDiv.textContent = 'Capabilities updated.';
    }
  } catch (e) {
    if (resultDiv) {
      resultDiv.classList.remove('loading', 'success', 'warning');
      resultDiv.classList.add('error');
      resultDiv.textContent = `Failed to get capabilities: ${e.message || e}`;
    }
  } finally {
    btn.disabled = false;
    btn.textContent = prevText;
  }
}

async function showSerialPorts(fieldset) {
  const portsDiv = fieldset.querySelector('.ports-list');
  const deviceInput = fieldset.querySelector('input[data-key="device"]');
  const showPortsBtn = fieldset.querySelector('[data-action="show-ports"]');

  showPortsBtn.disabled = true;
  showPortsBtn.textContent = 'Loading...';
  portsDiv.style.display = 'block';
  portsDiv.innerHTML = 'Scanning for serial ports...';

  try {
    const res = await fetch('/api/serial-ports');
    const result = await res.json();

    if (result.status === 'ok' && result.ports.length > 0) {
      let html = '<div class="ports-title">Available Serial Ports</div><ul class="ports-items">';
      result.ports.forEach(port => {
        html += `<li><button type="button" class="port-link" data-device="${port.device}"><code>${port.device}</code></button><span class="port-desc">${port.description}</span></li>`;
      });
      html += '</ul><div class="ports-hint">Click a port path to use it</div>';
      portsDiv.innerHTML = html;

      portsDiv.querySelectorAll('.port-link').forEach((btn) => {
        btn.addEventListener('click', () => {
          const dev = btn.getAttribute('data-device') || '';
          if (deviceInput) deviceInput.value = dev;
        });
      });
    } else if (result.status === 'ok') {
      portsDiv.innerHTML = 'No serial ports found. Make sure your rig is connected.';
    } else {
      portsDiv.innerHTML = `Error: ${result.message}`;
    }
  } catch (error) {
    portsDiv.innerHTML = `Error fetching ports: ${error.message}`;
  } finally {
    showPortsBtn.disabled = false;
    showPortsBtn.textContent = '📋 Show Ports';
  }
}

function renderLcdPreview(container, color, inverted) {
  if (!container) return;
  container.innerHTML = '';
  const lcd = document.createElement('div');
  lcd.className = 'lcd';
  if (inverted) lcd.classList.add('inverted');

  // Apply styles
  if (inverted) {
    lcd.style.background = '#222';
    lcd.style.color = color;
    lcd.style.textShadow = `0 0 5px ${color}`;
  } else {
    lcd.style.background = `linear-gradient(to bottom, ${color} 0%, #000 150%)`;
    lcd.style.color = '#222';
    lcd.style.textShadow = 'none';
  }

  // Match dashboard structure exactly for styling parity
  lcd.innerHTML = `
    <div class="lcd-row">
      <div>
        <button type="button" class="freq-btn" style="pointer-events:none;">
          <span class="freq" style="font-family: 'Segment7', monospace; font-size: 2em; letter-spacing: 2px;">14.074.000</span>
          <span class="unit" style="font-size: 0.8em; margin-left: 4px;">Hz</span>
        </button>
      </div>
      <div class="band" style="font-size: 0.9em; opacity: 0.8;">20m</div>
    </div>
    <div class="lcd-subrow" style="margin-top: 5px;">
      <div class="mode" style="font-weight: bold; font-size: 1.1em;">USB</div>
    </div>
  `;

  // Apply preview-specific overrides
  lcd.style.padding = '15px';
  lcd.style.borderRadius = '8px';
  lcd.style.fontFamily = '"Segment7", monospace'; // Fallback
  lcd.style.boxSizing = 'border-box'; // Ensure padding is included in width

  if (inverted) {
    lcd.style.background = '#000000'; // Darker for inverted
    lcd.style.color = color;
    lcd.style.textShadow = `0 0 10px ${color}`;
    lcd.style.boxShadow = `inset 0 0 10px ${color}33`; // Faint glow
  } else {
    // Standard dashboard gradient approximation
    lcd.style.background = `linear-gradient(180deg, ${color}cc 0%, ${color} 100%)`;
    lcd.style.color = '#1a1a1a';
    lcd.style.textShadow = '0 1px 0 rgba(255,255,255,0.4)';
    lcd.style.boxShadow = 'inset 0 2px 5px rgba(255,255,255,0.2)';
  }

  // Scale down for preview if needed, though exact sizing is better
  lcd.style.transform = 'scale(0.9)';
  lcd.style.transformOrigin = 'top left';
  // Fix overflow: width 110% was causing extension past the box.
  // 100% / 0.9 = 111%, but we need to ensure the container clips or fits.
  // Better: Set width to 100% relative to the scaled space?
  // Let's rely on the scale and give it enough room.
  lcd.style.width = '111%';

  container.appendChild(lcd);
}

function render() {
  rigList.innerHTML = '';
  rigs.forEach((rig, idx) => {
    const fs = document.createElement('fieldset');
    fs.innerHTML = `
          <legend>Rig ${idx + 1}</legend>
          <label>Name <input type="text" data-key="name" value="${rig.name ?? ''}" placeholder="Rig"></label>
          <label>Color 
            <span class="color-picker-wrapper">
              <input type="color" data-key="color" value="${rig.color ?? '#a4c356'}">
              <button type="button" class="color-reset-btn" data-action="reset-color">Default</button>
            </span>
          </label>
          <label style="display: grid; grid-template-columns: 180px 1fr; gap: 12px; align-items: center;">
              Invert LCD Colors
              <input type="checkbox" data-key="inverted" ${rig.inverted ? 'checked' : ''} style="width: auto; margin: 0; justify-self: start;">
          </label>
          <div class="lcd-preview-wrapper" style="margin: 10px 0; padding: 10px; border: 1px solid #444; border-radius: 4px; background: #111; overflow: hidden;">
             <div class="lcd-preview-label" style="font-size: 0.8em; color: #888; margin-bottom: 5px;">Preview:</div>
             <div class="lcd-preview-container"></div>
          </div>
          <label>Poll interval (ms) <input type="number" min="100" step="50" data-key="poll_interval_ms" value="${rig.poll_interval_ms ?? 1000}"></label>
          <label class="allow-oob">
            <input type="checkbox" data-key="allow_out_of_band" ${rig.allow_out_of_band ? 'checked' : ''}>
            Allow out-of-band frequencies
          </label>
          <label>Connection <select data-key="connection_type">
            <option value="hamlib">Hamlib (Direct)</option>
            <option value="rigctld">rigctld (TCP)</option>
          </select></label>
          <div class="rig-meta">
            <label>Model (-m)
              <span class="model-select-container"></span>
            </label>
            <div class="caps-badges" data-role="caps"></div>
            <div class="modes-badges" data-role="modes"></div>
          </div>
          <div class="conn hamlib">
            <label>Device (-r)
              <span class="device-row">
                <input type="text" data-key="device" value="${rig.device ?? ''}" placeholder="/dev/tty.usbserial...">
                <button type="button" class="ports-btn" data-action="show-ports">📋 Show Ports</button>
              </span>
            </label>
            <div class="ports-list" style="display: none;"></div>
            <label>Baud (-s) <input type="number" data-key="baud" value="${rig.baud ?? 38400}" placeholder="38400"></label>
            <label>Serial opts <input type="text" data-key="serial_opts" value="${rig.serial_opts ?? ''}" placeholder="e.g., N8 RTSCTS"></label>
            <label>Extra args <input type="text" data-key="extra_args" value="${rig.extra_args ?? ''}" placeholder="additional rigctl flags"></label>
          </div>
          <div class="conn rigctld">
            <label>Host <input type="text" data-key="host" value="${rig.host ?? '127.0.0.1'}" placeholder="127.0.0.1"></label>
            <label>Port <input type="number" data-key="port" value="${rig.port ?? 4532}" placeholder="4532"></label>
          </div>
          <div class="actions">
            <button type="button" data-action="test">Test Connection</button>
            <button type="button" data-action="caps">Get capabilities</button>
            <button type="button" data-action="remove">Remove</button>
          </div>
          <div class="rig-section" data-role="band-presets-section">
            <button type="button" class="rig-section-header" data-action="toggle-band-presets">
              <span class="turnstile">▼</span>
              <span class="rig-section-title">Band presets</span>
            </button>
            <div class="rig-section-body">
              <div class="band-presets" data-role="band-presets"></div>
            </div>
          </div>
          <div class="test-result" style="display: none;"></div>
        `;

    // Insert model select
    const modelSelect = createModelSelect(rig.model_id);
    fs.querySelector('.model-select-container').appendChild(modelSelect);

    const capsEl = fs.querySelector('[data-role="caps"]');
    const modesEl = fs.querySelector('[data-role="modes"]');
    const updateCaps = () => {
      renderCapsBadges(capsEl, modelSelect.value);
      renderModesBadges(modesEl, modelSelect.value);
    };
    modelSelect.addEventListener('change', updateCaps);

    // Initialize selects and visibility
    const sel = fs.querySelector('select[data-key="connection_type"]');
    sel.value = rig.connection_type || 'hamlib';
    const updateVis = () => {
      fs.querySelector('.conn.rigctld').style.display = sel.value === 'rigctld' ? '' : 'none';
      fs.querySelector('.conn.hamlib').style.display = sel.value === 'hamlib' ? '' : 'none';
      updateCaps();
    };
    sel.addEventListener('change', updateVis);
    updateVis();

    // Wire test button
    fs.querySelector('[data-action="test"]').addEventListener('click', async () => {
      await testRigConnection(fs);
    });

    // Wire caps button
    fs.querySelector('[data-action="caps"]').addEventListener('click', async () => {
      await refreshRigCaps(fs);
    });

    // Wire show ports button
    const showPortsBtn = fs.querySelector('[data-action="show-ports"]');
    if (showPortsBtn) {
      showPortsBtn.addEventListener('click', async () => {
        await showSerialPorts(fs);
      });
    }

    // Wire remove
    fs.querySelector('[data-action="remove"]').addEventListener('click', () => {
      rigs.splice(idx, 1);
      render();
    });

    const bandSection = fs.querySelector('[data-role="band-presets-section"]');
    const bandBody = bandSection ? bandSection.querySelector('.rig-section-body') : null;
    const bandToggle = bandSection ? bandSection.querySelector('[data-action="toggle-band-presets"]') : null;
    const applyBandCollapsed = (collapsed) => {
      if (!bandSection || !bandBody) return;
      bandSection.classList.toggle('collapsed', !!collapsed);
      bandBody.style.display = collapsed ? 'none' : '';
    };
    applyBandCollapsed(getBandPresetsCollapsed(idx));
    if (bandToggle) {
      bandToggle.addEventListener('click', () => {
        const next = !bandSection.classList.contains('collapsed');
        setBandPresetsCollapsed(idx, next);
        applyBandCollapsed(next);
      });
    }

    const bandsEl = fs.querySelector('[data-role="band-presets"]');
    renderBandPresets(bandsEl, ensureBandPresets(rig));

    // Wire color reset button
    const colorResetBtn = fs.querySelector('[data-action="reset-color"]');
    if (colorResetBtn) {
      colorResetBtn.addEventListener('click', () => {
        const colorInput = fs.querySelector('input[data-key="color"]');
        if (colorInput) {
          colorInput.value = '#a4c356';
          // Trigger input event to ensure autosave picks up the change
          colorInput.dispatchEvent(new Event('input', { bubbles: true }));
        }
      });
    }


    // Initialize LCD Preview
    const previewContainer = fs.querySelector('.lcd-preview-container');
    const colorInput = fs.querySelector('input[data-key="color"]');
    const invertInput = fs.querySelector('input[data-key="inverted"]');

    const updatePreview = () => {
      if (colorInput && invertInput) {
        renderLcdPreview(previewContainer, colorInput.value, invertInput.checked);
      }
    };

    if (colorInput) colorInput.addEventListener('input', updatePreview);
    if (invertInput) invertInput.addEventListener('change', updatePreview);
    updatePreview();

    rigList.appendChild(fs);
  });
}

async function loadConfig() {
  // Load rig models first
  await loadRigModels();
  await loadBindAddrs();

  try {
    suppressAutosave = true;
    const res = await fetch('/api/config');
    const cfg = await res.json();

    // Also load runtime status to get auto-detected caps
    try {
      const statusRes = await fetch('/api/status');
      const status = await statusRes.json();
      const statusRigs = Array.isArray(status?.rigs) ? status.rigs : [];
      // Merge detected caps into rigModels cache for display
      statusRigs.forEach(r => {
        if (r.model_id != null && r.caps) {
          const model = getModelById(r.model_id);
          if (model) {
            model.caps = r.caps;
            if (Array.isArray(r.modes)) model.modes = r.modes;
          }
        }
      });
    } catch (e) {
      console.warn('Failed to load status for caps:', e);
    }

    rigs = Array.isArray(cfg.rigs) && cfg.rigs.length ? cfg.rigs : [];
    syncEnabled = cfg.sync_enabled !== false;
    syncSourceIndex = Number.isFinite(Number(cfg.sync_source_index)) ? Number(cfg.sync_source_index) : 0;
    rigctlToMainEnabled = cfg.rigctl_to_main_enabled !== false;
    // Set poll interval
    form.querySelector('input[name="poll"]').value = cfg.poll_interval_ms ?? 1000;
    rigctlHostSelect.value = cfg.rigctl_listen_host ?? '127.0.0.1';
    rigctlPortInput.value = cfg.rigctl_listen_port ?? 4534;
    if (!rigs.length) {
      rigs = [
        { name: 'Rig 1', connection_type: 'hamlib', model_id: null, device: '', baud: 38400 },
      ];
    }
    rigs = rigs.map((r) => ({ ...r, poll_interval_ms: r.poll_interval_ms ?? 1000, band_presets: ensureBandPresets(r) }));
    render();
  } catch { }
  suppressAutosave = false;
}

if (profileSelectBtn && profileSelectDialog) {
  profileSelectBtn.addEventListener('click', async () => {
    await refreshActiveProfileName();
    await refreshProfileChoices();
    profileSelectDialog.showModal();
  });
}

if (profileSelectConfirm && profileSelectDialog) {
  profileSelectConfirm.addEventListener('click', async (e) => {
    e.preventDefault();
    const name = String(profileSelectChoice?.value || '').trim();
    await loadProfileByName(name);
    profileSelectDialog.close();
  });
}

if (profileAddBtn && profileAddDialog) {
  profileAddBtn.addEventListener('click', async () => {
    if (profileAddName) profileAddName.value = '';
    await refreshProfileChoices();
    profileAddDialog.showModal();
  });
}

if (profileAddConfirm && profileAddDialog) {
  profileAddConfirm.addEventListener('click', async (e) => {
    e.preventDefault();
    const name = String(profileAddName?.value || '').trim();
    const created = await createProfileByName(name);
    if (!created) return;
    await loadProfileByName(name);
    profileAddDialog.close();
  });
}

if (profileRenameBtn && profileRenameDialog) {
  profileRenameBtn.addEventListener('click', async () => {
    if (profileRenameNew) profileRenameNew.value = '';
    await refreshActiveProfileName();
    await refreshProfileChoices();
    profileRenameDialog.showModal();
  });
}

if (profileRenameConfirm && profileRenameDialog) {
  profileRenameConfirm.addEventListener('click', async (e) => {
    e.preventDefault();
    const oldName = String(profileRenameOld?.value || '').trim();
    const newName = String(profileRenameNew?.value || '').trim();
    const ok = await renameProfile(oldName, newName);
    if (!ok) return;
    profileRenameDialog.close();
  });
}

if (profileDuplicateBtn && profileDuplicateDialog) {
  profileDuplicateBtn.addEventListener('click', async () => {
    if (profileDuplicateNew) profileDuplicateNew.value = '';
    if (profileDuplicateStep1) profileDuplicateStep1.style.display = '';
    if (profileDuplicateStep2) profileDuplicateStep2.style.display = 'none';
    if (profileDuplicateBack) profileDuplicateBack.style.display = 'none';
    if (profileDuplicateNext) profileDuplicateNext.style.display = '';
    if (profileDuplicateConfirm) profileDuplicateConfirm.style.display = 'none';
    await refreshActiveProfileName();
    await refreshProfileChoices();
    profileDuplicateDialog.showModal();
  });
}

if (profileDuplicateNext) {
  profileDuplicateNext.addEventListener('click', async (e) => {
    e.preventDefault();
    if (profileDuplicateStep1) profileDuplicateStep1.style.display = 'none';
    if (profileDuplicateStep2) profileDuplicateStep2.style.display = '';
    if (profileDuplicateBack) profileDuplicateBack.style.display = '';
    if (profileDuplicateNext) profileDuplicateNext.style.display = 'none';
    if (profileDuplicateConfirm) profileDuplicateConfirm.style.display = '';
  });
}

if (profileDuplicateBack) {
  profileDuplicateBack.addEventListener('click', async (e) => {
    e.preventDefault();
    if (profileDuplicateStep1) profileDuplicateStep1.style.display = '';
    if (profileDuplicateStep2) profileDuplicateStep2.style.display = 'none';
    if (profileDuplicateBack) profileDuplicateBack.style.display = 'none';
    if (profileDuplicateNext) profileDuplicateNext.style.display = '';
    if (profileDuplicateConfirm) profileDuplicateConfirm.style.display = 'none';
  });
}

if (profileDuplicateConfirm && profileDuplicateDialog) {
  profileDuplicateConfirm.addEventListener('click', async (e) => {
    e.preventDefault();
    const fromName = String(profileDuplicateFrom?.value || '').trim();
    const newName = String(profileDuplicateNew?.value || '').trim();
    const ok = await duplicateProfile(fromName, newName);
    if (!ok) return;
    profileDuplicateDialog.close();
  });
}

if (profileDeleteBtn && profileDeleteDialog) {
  profileDeleteBtn.addEventListener('click', async () => {
    await refreshActiveProfileName();
    await refreshProfileChoices();
    profileDeleteDialog.showModal();
  });
}

if (profileDeleteConfirm && profileDeleteDialog) {
  profileDeleteConfirm.addEventListener('click', async (e) => {
    e.preventDefault();
    const name = String(profileDeleteChoice?.value || '').trim();
    const ok = await deleteProfileByName(name);
    if (!ok) return;
    profileDeleteDialog.close();
  });
}
if (configExportBtn) configExportBtn.addEventListener('click', exportCurrentConfig);
if (configImportBtn) {
  configImportBtn.addEventListener('click', () => {
    if (configImportInput) configImportInput.click();
  });
}
if (configImportInput) {
  configImportInput.addEventListener('change', async () => {
    const file = configImportInput.files && configImportInput.files[0];
    await importConfigFile(file);
  });
}

addRigBtn.addEventListener('click', () => {
  const nextIndex = rigs.length + 1;
  rigs.push({ name: `Rig ${nextIndex}`, connection_type: 'hamlib', model_id: null, device: '', baud: 38400, color: '#a4c356' });
  render();
});

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  await autosaveNow();
});

form.addEventListener('input', scheduleAutosave, true);
form.addEventListener('change', scheduleAutosave, true);

loadConfig().then(async () => {
  await refreshActiveProfileName();
  await refreshProfileChoices();
});
