(() => {
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  const followPending = new Map();

  const debugSectionCollapsed = new Map();

  const sectionKey = (idx, name) => `multirig.section.${idx}.${name}.collapsed`;
  const getSectionCollapsed = (idx, name) => {
    if (name === 'debug') {
      return debugSectionCollapsed.has(idx) ? !!debugSectionCollapsed.get(idx) : true;
    }
    try {
      const v = localStorage.getItem(sectionKey(idx, name));
      return v === '1';
    } catch {
      return false;
    }
  };
  const setSectionCollapsed = (idx, name, collapsed) => {
    if (name === 'debug') {
      debugSectionCollapsed.set(idx, !!collapsed);
      return;
    }
    try { localStorage.setItem(sectionKey(idx, name), collapsed ? '1' : '0'); } catch { }
  };
  const applySections = (card, idx) => {
    const sections = $$('.rig-section[data-section]', card);
    for (const sec of sections) {
      const name = sec.dataset.section;
      const collapsed = getSectionCollapsed(idx, name);
      sec.classList.toggle('collapsed', collapsed);
      const body = $('.rig-section-body', sec);
      if (body) body.style.display = collapsed ? 'none' : '';
    }
  };


  const getLcdInverted = (idx, defaultVal = false) => {
    try {
      const v = localStorage.getItem(`multirig.lcd.inverted.${idx}`);
      if (v === '1') return true;
      if (v === '0') return false;
    } catch { }
    return !!defaultVal;
  };

  const setLcdInverted = (idx, inverted) => {
    try { localStorage.setItem(`multirig.lcd.inverted.${idx}`, inverted ? '1' : '0'); } catch { }
  };

  const toggleFollow = async (idx) => {
    const status = await (await fetch('/api/status', { cache: 'no-store' })).json();
    const rigs = Array.isArray(status.rigs) ? status.rigs : [];
    const mainIdx = Number.isFinite(Number(status.sync_source_index)) ? Number(status.sync_source_index) : 0;
    if (idx === mainIdx) return;
    const cur = rigs[idx];
    const next = !(cur && cur.follow_main !== false);
    await postJSON(`/api/rig/${idx}/follow_main`, { follow_main: next });
  };

  const renderVfoControls = (el, idx, currentVfo, enabled) => {
    if (!el) return;
    const v = (currentVfo || '').toUpperCase();
    if (!v) {
      el.style.display = 'none';
      el.textContent = '';
      return;
    }
    el.style.display = '';
    const activeA = v.includes('VFOA') || v === 'A';
    const activeB = v.includes('VFOB') || v === 'B';
    el.innerHTML = '';
    const a = document.createElement('button');
    a.type = 'button';
    a.className = 'vfo-btn' + (activeA ? ' active' : '');
    a.dataset.action = 'set-vfo';
    a.dataset.index = String(idx);
    a.dataset.vfo = 'VFOA';
    a.textContent = 'VFO A';
    a.disabled = !enabled;
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'vfo-btn' + (activeB ? ' active' : '');
    b.dataset.action = 'set-vfo';
    b.dataset.index = String(idx);
    b.dataset.vfo = 'VFOB';
    b.textContent = 'VFO B';
    b.disabled = !enabled;
    el.appendChild(a);
    el.appendChild(b);
  };

  const renderVfoFreqs = (el, idx, currentVfo) => {
    if (!el) return;
    const v = (currentVfo || '').toUpperCase();
    if (!v) {
      el.style.display = 'none';
      el.textContent = '';
      return;
    }
    el.style.display = '';
    const entry = vfoFreqCache.get(idx) || {};
    const a = entry.A;
    const b = entry.B;
    const fa = formatFreq(a);
    const fb = formatFreq(b);
    el.innerHTML = `A ${fa.text}${fa.unit ? ' ' + fa.unit : ''}  |  B ${fb.text}${fb.unit ? ' ' + fb.unit : ''}`;
  };

  const formatFreq = (hz) => {
    if (hz == null || isNaN(hz)) return { text: '—', unit: '' };
    const v = Number(hz);
    if (!isFinite(v)) return { text: '—', unit: '' };
    if (v < 1000000) {
      const khz = v / 1000.0;
      return { text: khz.toFixed(3), unit: 'kHz' };
    }
    const mhz = v / 1000000.0;
    return { text: mhz.toFixed(6), unit: 'MHz' };
  };

  const formatRw = (getOk, setOk) => {
    if (getOk && setOk) return 'RW';
    if (getOk) return 'R';
    if (setOk) return 'W';
    return '';
  };

  const modeMeanings = {
    'DIGI': 'Digital',
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

  let rigModels = [];
  let rigModelById = new Map();
  const vfoFreqCache = new Map();
  let globalEditorListenersAdded = false;
  const freqUnitPref = new Map();
  const rigPolicyCache = new Map();
  const rigUiErrorCache = new Map();

  const setRigUiError = (idx, message) => {
    if (!Number.isFinite(idx)) return;
    const msg = String(message || '').trim();
    if (!msg) {
      rigUiErrorCache.delete(idx);
      return;
    }
    rigUiErrorCache.set(idx, msg);
    const card = document.getElementById(`rig-${idx}`);
    const errBox = card ? card.querySelector('[data-role="error"]') : null;
    const errBody = errBox ? errBox.querySelector('.rig-error-body') : null;
    if (errBox && errBody) {
      errBox.style.display = '';
      errBox.classList.add('conn-error');
      errBody.textContent = msg;
    }
  };

  const clearRigUiError = (idx) => {
    if (!Number.isFinite(idx)) return;
    rigUiErrorCache.delete(idx);
  };

  const bands = [
    { label: '160m', lo: 1800000, hi: 2000000, def: 1900000 },
    { label: '80m', lo: 3500000, hi: 4000000, def: 3700000 },
    { label: '60m', lo: 5330000, hi: 5406000, def: 5364000 },
    { label: '40m', lo: 7000000, hi: 7300000, def: 7074000 },
    { label: '30m', lo: 10100000, hi: 10150000, def: 10136000 },
    { label: '20m', lo: 14000000, hi: 14350000, def: 14074000 },
    { label: '17m', lo: 18068000, hi: 18168000, def: 18100000 },
    { label: '15m', lo: 21000000, hi: 21450000, def: 21074000 },
    { label: '12m', lo: 24890000, hi: 24990000, def: 24915000 },
    { label: '10m', lo: 28000000, hi: 29700000, def: 28074000 },
    { label: '6m', lo: 50000000, hi: 54000000, def: 50125000 },
    { label: '2m', lo: 144000000, hi: 148000000, def: 145000000 },
    { label: '1.25m', lo: 222000000, hi: 225000000, def: 223500000 },
    { label: '70cm', lo: 420000000, hi: 450000000, def: 432100000 },
    { label: '33cm', lo: 902000000, hi: 928000000, def: 903000000 },
    { label: '23cm', lo: 1240000000, hi: 1300000000, def: 1296000000 },
  ];

  const bandLabelToMeters = (label) => {
    const s = String(label || '').trim().toLowerCase();
    if (!s) return null;
    const m = s.match(/^([0-9]+(?:\.[0-9]+)?)\s*(m|cm)$/);
    if (!m) return null;
    const n = Number(m[1]);
    if (!Number.isFinite(n)) return null;
    if (m[2] === 'cm') return n / 100.0;
    return n;
  };

  const quickBandLabels = ['40m', '20m', '15m', '10m', '6m', '2m', '70cm'];

  const bandForHz = (hz) => {
    if (hz == null) return null;
    const v = Number(hz);
    if (!isFinite(v)) return null;
    for (const b of bands) {
      if (v >= b.lo && v <= b.hi) return b;
    }
    return null;
  };

  const enabledBandPresetMatch = (presets, hz) => {
    if (hz == null) return null;
    const v = Number(hz);
    if (!isFinite(v)) return null;
    const list = Array.isArray(presets) ? presets : [];
    for (const p of list) {
      try {
        if (!p || p.enabled === false) continue;
        const lo = Number(p.lower_hz);
        const hi = Number(p.upper_hz);
        if (!isFinite(lo) || !isFinite(hi)) continue;
        if (v >= lo && v <= hi) return p;
      } catch {
        continue;
      }
    }
    return null;
  };

  const vfoKeyFromStr = (s) => {
    const v = (s || '').toUpperCase();
    if (!v) return null;
    if (v.includes('VFOA') || v === 'A') return 'A';
    if (v.includes('VFOB') || v === 'B') return 'B';
    return null;
  };

  const loadRigModels = async () => {
    try {
      const res = await fetch('/static/rig_models.json?ts=' + Date.now(), { cache: 'no-store' });
      rigModels = await res.json();
      rigModelById = new Map();
      for (const m of rigModels) {
        if (m && m.id != null) rigModelById.set(String(m.id), m);
      }
    } catch (e) {
      rigModels = [];
      rigModelById = new Map();
    }
  };

  const getModel = (modelId) => {
    if (modelId == null) return null;
    return rigModelById.get(String(modelId)) || null;
  };

  const ensureGrid = (rigs) => {
    const grid = $('#rigGrid');
    if (!grid) return;
    // Rebuild grid if counts differ or missing cards
    const existing = $$('.rig-card', grid);
    const needsRebuild =
      existing.length !== rigs.length ||
      (existing.length > 0 && (!existing[0].querySelector('[data-role="error"]') || !existing[0].querySelector('[data-role="vfo-controls"]') || !existing[0].querySelector('[data-role="vfo-freqs"]') || !existing[0].querySelector('[data-role="bands"]')));

    if (needsRebuild) {
      grid.innerHTML = '';
      rigs.forEach((rig, idx) => {
        const card = document.createElement('div');
        card.className = 'rig-card';
        card.id = `rig-${idx}`;
        card.dataset.index = String(idx);
        card.innerHTML = `
          <div class="rig-header">
            <div class="rig-header-left">
              <div class="rig-title">${rig.name || `Rig ${idx + 1}`}</div>
              <div class="rig-badges" data-role="rig-badges"></div>
            </div>
            <div class="rig-header-right">
              <button type="button" class="sync-btn" data-action="sync" data-index="${idx}" title="Sync this rig to the main rig">
                <span class="sync-icon" aria-hidden="true">⟲</span>
                <span class="sync-text">Sync</span>
              </button>
              <div class="follow-switch-wrap" data-role="follow-wrap" title="Whether this rig follows the main rig">
                <label class="follow-switch">
                  <input type="checkbox" data-action="follow-main" data-index="${idx}">
                  <span class="follow-slider">
                    <span class="follow-text follow-text-on">Follow</span>
                    <span class="follow-text follow-text-off">Manual</span>
                  </span>
                </label>
              </div>
              <label class="power-switch" title="Enable/disable">
                <input type="checkbox" data-action="power" data-index="${idx}">
                <span class="power-slider"></span>
              </label>
            </div>
          </div>
          <div class="lcd">
            <div class="lcd-row">
              <div>
                <button type="button" class="freq-btn" data-action="edit-freq" data-index="${idx}" title="Edit frequency">
                  <span class="freq">—</span>
                  <span class="unit"></span>
                </button>
                <div class="freq-editor" data-role="freq-editor" style="display:none;">
                  <input class="freq-input" data-role="freq-input" type="text" inputmode="decimal" autocomplete="off" spellcheck="false" placeholder="Frequency">
                  <select class="freq-unit" data-role="freq-unit" aria-label="Frequency unit">
                    <option value="auto">Auto</option>
                    <option value="mhz">MHz</option>
                    <option value="khz">kHz</option>
                    <option value="hz">Hz</option>
                  </select>
                  <button type="button" class="freq-save" data-action="freq-save" data-index="${idx}">Set</button>
                  <button type="button" class="freq-cancel" data-action="freq-cancel" data-index="${idx}">Cancel</button>
                </div>
              </div>
              <div class="band" data-role="band"></div>
            </div>
            <div class="vfo-freqs" data-role="vfo-freqs"></div>
            <div class="lcd-subrow">
              <div class="mode">—</div>
            </div>
          </div>
          <div class="rig-error" data-role="error" style="display:none;">
            <div class="rig-error-title">Error</div>
            <div class="rig-error-body"></div>
          </div>
          <div class="rig-section" data-section="vfo">
            <button type="button" class="rig-section-header" data-action="toggle-section" data-index="${idx}" data-section="vfo">
              <span class="turnstile">▼</span>
              <span class="rig-section-title">VFO</span>
            </button>
            <div class="rig-section-body">
              <div class="vfo-controls" data-role="vfo-controls"></div>
            </div>
          </div>
          <div class="rig-section" data-section="bands">
            <button type="button" class="rig-section-header" data-action="toggle-section" data-index="${idx}" data-section="bands">
              <span class="turnstile">▼</span>
              <span class="rig-section-title">Bands</span>
            </button>
            <div class="rig-section-body">
              <div class="band-buttons" data-role="bands"></div>
            </div>
          </div>
          <div class="rig-section" data-section="modes">
            <button type="button" class="rig-section-header" data-action="toggle-section" data-index="${idx}" data-section="modes">
              <span class="turnstile">▼</span>
              <span class="rig-section-title">Modes</span>
            </button>
            <div class="rig-section-body">
              <div class="mode-buttons" data-role="modes"></div>
            </div>
          </div>
          <div class="rig-section" data-section="debug">
            <button type="button" class="rig-section-header" data-action="toggle-section" data-index="${idx}" data-section="debug">
              <span class="turnstile">▼</span>
              <span class="rig-section-title">Rig Traffic</span>
            </button>
            <div class="rig-section-body">
              <pre class="debug-log" data-role="debug-log"></pre>
            </div>
          </div>
          `;
        grid.appendChild(card);
      });
      // Wire up buttons
      grid.addEventListener('click', (e) => {
        const secBtn = e.target.closest('button[data-action="toggle-section"]');
        if (secBtn) {
          const card = secBtn.closest('.rig-card');
          const idx = Number(secBtn.dataset.index);
          const name = String(secBtn.dataset.section || '').trim();
          if (!card || !Number.isFinite(idx) || !name) return;
          const sec = card.querySelector(`.rig-section[data-section="${name}"]`);
          if (!sec) return;
          const next = !sec.classList.contains('collapsed');
          setSectionCollapsed(idx, name, next);
          applySections(card, idx);
          if (!next && name === 'debug') {
            refreshRigDebug(idx);
          }
          return;
        }

        const bandBtn = e.target.closest('button[data-action="set-band"]');
        if (bandBtn) {
          const card = bandBtn.closest('.rig-card');
          if (card?.classList.contains('disabled')) return;
          const idx = Number(bandBtn.dataset.index);
          const hz = Number(bandBtn.dataset.hz);
          if (!Number.isFinite(idx) || !Number.isFinite(hz)) return;
          setRigFrequency(idx, hz);
          return;
        }

        const freqBtn = e.target.closest('button[data-action="edit-freq"]');
        if (freqBtn) {
          const card = freqBtn.closest('.rig-card');
          if (card?.classList.contains('disabled')) return;
          const idx = Number(freqBtn.dataset.index);
          if (!Number.isFinite(idx)) return;
          openFreqEditor(idx);
          return;
        }

        const saveBtn = e.target.closest('button[data-action="freq-save"]');
        if (saveBtn) {
          const idx = Number(saveBtn.dataset.index);
          if (!Number.isFinite(idx)) return;
          saveFreqEditor(idx);
          return;
        }

        const cancelBtn = e.target.closest('button[data-action="freq-cancel"]');
        if (cancelBtn) {
          const idx = Number(cancelBtn.dataset.index);
          if (!Number.isFinite(idx)) return;
          closeFreqEditor(idx);
          return;
        }

        const vfoBtn = e.target.closest('button[data-action="set-vfo"]');
        if (vfoBtn) {
          const card = vfoBtn.closest('.rig-card');
          if (card?.classList.contains('disabled')) return;
          const idx = Number(vfoBtn.dataset.index);
          const vfo = vfoBtn.dataset.vfo;
          if (Number.isFinite(idx) && vfo) setRigVfo(idx, vfo);
          return;
        }

        const modeBtn = e.target.closest('button[data-action="set-mode"]');
        if (modeBtn) {
          const card = modeBtn.closest('.rig-card');
          if (card?.classList.contains('disabled')) return;
          const idx = Number(card?.dataset?.index);
          const mode = modeBtn.dataset.mode;
          if (Number.isFinite(idx) && mode) setRigMode(idx, mode);
          return;
        }
        const btn = e.target.closest('button[data-action]');
        if (!btn) return;
        const action = btn.dataset.action;
        const idx = Number(btn.dataset.index);
        if (action === 'set-mode') return;
        const card = btn.closest('.rig-card');
        if (card?.classList.contains('disabled')) return;
        if (action === 'sync') return syncRig(idx);
        if (action === 'follow-toggle') return toggleFollow(idx);
      });

      grid.addEventListener('change', (e) => {
        const sw = e.target.closest('input[data-action="power"]');
        if (!sw) return;
        const idx = Number(sw.dataset.index);
        const enabled = !!sw.checked;
        setRigEnabled(idx, enabled);
      });

      grid.addEventListener('change', async (e) => {
        const sw = e.target.closest('input[data-action="follow-main"]');
        if (!sw) return;
        const idx = Number(sw.dataset.index);
        const follow_main = !!sw.checked;
        followPending.set(idx, follow_main);
        sw.disabled = true;
        try {
          const res = await postJSON(`/api/rig/${idx}/follow_main`, { follow_main });
          if (!res || res.status !== 'ok') {
            throw new Error((res && res.error) ? String(res.error) : 'failed');
          }
          followPending.delete(idx);
        } catch (err) {
          followPending.delete(idx);
          try { setRigUiError(idx, `Failed to update follow: ${err}`); } catch { }
        } finally {
          sw.disabled = false;
        }
      });

      grid.addEventListener('change', (e) => {
        const sw = e.target.closest('input[data-action="invert-lcd"]');
        if (!sw) return;
        const idx = Number(sw.dataset.index);
        const inverted = !!sw.checked;
        setLcdInverted(idx, inverted);
        // Re-apply styles immediately
        const card = document.getElementById(`rig-${idx}`);
        if (card) {
          // We need to re-run the part of bindStatus that applies colors
          // But we don't have the rig data here. 
          // However, the card has the loop updating it every second.
          // We can just wait for next tick or try to read color from somewhere?
          // Actually bindStatus runs frequently. Just saving state is enough?
          // Yes, let's just trigger a re-render if we can, or just wait for next update (1s max).
          // To make it instant, we can try to re-read current color from style if needed, 
          // but waiting 1s is probably fine or we force a refresh?
          // Let's just update the class for now for instant feedback on the checkbox itself?
          // Actually since bindStatus is called every 1s, we can just wait. 
          // But usually UI should be snappy.
          // Let's manually toggle class and style if we can find the LCD.
          const lcd = card.querySelector('.lcd');
          if (lcd) {
            lcd.classList.toggle('inverted', inverted);
            // We can't easily re-calculate the specific gradient without the rig color data.
            // So we'll rely on next update or if we can read it?
            // Let's just let the next update handle the heavy lifting of color change
            // forcing the class is enough for CSS changes that don't depend on rig color variables.
          }
        }
      });

      if (!globalEditorListenersAdded) {
        globalEditorListenersAdded = true;
        document.addEventListener('click', (e) => {
          const inside = e.target.closest('.freq-editor') || e.target.closest('button[data-action="edit-freq"]');
          if (inside) return;
          $$('.rig-card').forEach((card) => {
            const idx = Number(card.dataset.index);
            if (Number.isFinite(idx)) closeFreqEditor(idx);
          });
        });

        document.addEventListener('keydown', (e) => {
          if (e.key !== 'Escape') return;
          $$('.rig-card').forEach((card) => {
            const idx = Number(card.dataset.index);
            if (Number.isFinite(idx)) closeFreqEditor(idx);
          });
        });
      }
    } else {
      // Update titles if names changed
      rigs.forEach((rig, idx) => {
        const card = $(`#rig-${idx}`);
        if (card) {
          const title = $('.rig-title', card);
          if (title) title.textContent = rig.name || `Rig ${idx + 1}`;
        }
      });
    }
  };

  const bindStatus = (data) => {
    const rigs = Array.isArray(data.rigs) ? data.rigs : [];
    ensureGrid(rigs);
    const mainIdx = Number.isFinite(Number(data.sync_source_index)) ? Number(data.sync_source_index) : 0;

    const rigctlToMainToggle = document.getElementById('rigctlToMainToggle');
    if (rigctlToMainToggle) {
      rigctlToMainToggle.checked = data.rigctl_to_main_enabled !== false;
    }
    const mainToFollowersToggle = document.getElementById('mainToFollowersToggle');
    if (mainToFollowersToggle) {
      mainToFollowersToggle.checked = data.sync_enabled !== false;
    }
    const allRigsEnabledToggle = document.getElementById('allRigsEnabledToggle');
    if (allRigsEnabledToggle) {
      allRigsEnabledToggle.checked = data.all_rigs_enabled !== false;
    }

    const mainSel = document.getElementById('mainRigSelect');
    if (mainSel) {
      if (mainSel.options.length !== rigs.length) {
        mainSel.innerHTML = '';
        rigs.forEach((r, i) => {
          const opt = document.createElement('option');
          opt.value = String(i);
          opt.textContent = r.name || `Rig ${i + 1}`;
          mainSel.appendChild(opt);
        });
      }
      mainSel.value = String(mainIdx);
    }

    rigs.forEach((rig, idx) => {
      const card = document.getElementById(`rig-${idx}`);
      if (!card) return;

      const lcd = card.querySelector('.lcd');
      if (lcd) {
        lcd.classList.toggle('inverted', rig.inverted || false);
        if (rig.color) {
          if (rig.inverted) {
            // Inverted: Dark background, Text is rig color (brightened/dimmed as needed)
            // We use the CSS background for inverted (.lcd.inverted background) 
            // but we need to set the TEXT color to the rig color.
            lcd.style.background = ''; // Use CSS default for inverted
            lcd.style.color = rig.color;
            // Maybe add a text shadow/glow for effect?
            lcd.style.textShadow = `0 0 5px ${rig.color}66`;
          } else {
            // Normal: Rig color background, Dark text (from CSS default or set explicitly)
            lcd.style.background = `linear-gradient(135deg, ${rig.color}dd, ${rig.color}aa)`;
            lcd.style.color = 'rgba(0,0,0,0.88)';
            lcd.style.textShadow = 'none';
          }
        }
      }

      applySections(card, idx);
      card.classList.toggle('disconnected', !rig.connected);
      card.classList.toggle('ptt-on', !!rig.ptt);
      card.classList.toggle('disabled', rig.enabled === false);
      card.dataset.enabled = (rig.enabled !== false) ? 'true' : 'false';
      const power = $('input[data-action="power"]', card);
      const freq = $('.freq', card);
      const unit = $('.unit', card);
      const mode = $('.mode', card);
      const modesEl = $('[data-role="modes"]', card);
      const bandsEl = $('[data-role="bands"]', card);
      const bandEl = $('[data-role="band"]', card);
      const syncBtn = $('button[data-action="sync"]', card);
      const vfoControls = $('[data-role="vfo-controls"]', card);
      const vfoFreqs = $('[data-role="vfo-freqs"]', card);
      const freqBtn = $('button[data-action="edit-freq"]', card);
      const badges = $('[data-role="rig-badges"]', card);
      const followWrap = $('[data-role="follow-wrap"]', card);
      const followSwitch = $('input[data-action="follow-main"]', card);

      const errBox = $('[data-role="error"]', card);
      const errBody = errBox ? $('.rig-error-body', errBox) : null;
      const legacyErr = $('.error', card);

      const connErrText = (rig.error || '').trim();
      const opErrText = (rig.last_error || '').trim();
      const errText = (connErrText || opErrText).trim();
      const hasError = !!errText;
      const connError = !!connErrText && !rig.connected;
      const uiErr = (rigUiErrorCache.get(idx) || '').trim();

      rigPolicyCache.set(idx, {
        allow_out_of_band: !!rig.allow_out_of_band,
        band_presets: Array.isArray(rig.band_presets) ? rig.band_presets : [],
      });

      if (power) {
        power.disabled = connError;
        power.checked = (rig.enabled !== false) && !connError;
        power.title = connError
          ? 'Connection error'
          : ((rig.enabled !== false)
            ? (rig.connected ? 'Enabled (connected)' : 'Enabled (disconnected)')
            : 'Disabled');
      }
      const f = formatFreq(rig.frequency_hz);
      if (freq) freq.textContent = f.text;
      if (unit) unit.textContent = f.unit;
      if (mode) mode.textContent = rig.mode || '—';

      const activeVfoKey = vfoKeyFromStr(rig.vfo);
      const supportsVfo = !!activeVfoKey || rig.frequency_a_hz != null || rig.frequency_b_hz != null;
      const vfoSection = card.querySelector('.rig-section[data-section="vfo"]');
      if (vfoSection) vfoSection.style.display = supportsVfo ? '' : 'none';

      // Prefer backend dual-VFO fields if present.
      if (rig.frequency_a_hz != null || rig.frequency_b_hz != null) {
        const entry = vfoFreqCache.get(idx) || {};
        if (rig.frequency_a_hz != null) entry.A = rig.frequency_a_hz;
        if (rig.frequency_b_hz != null) entry.B = rig.frequency_b_hz;
        vfoFreqCache.set(idx, entry);
      } else if (rig.frequency_hz != null && activeVfoKey) {
        const entry = vfoFreqCache.get(idx) || {};
        if (activeVfoKey === 'A') entry.A = rig.frequency_hz;
        if (activeVfoKey === 'B') entry.B = rig.frequency_hz;
        vfoFreqCache.set(idx, entry);
      }

      renderVfoControls(vfoControls, idx, rig.vfo, (rig.enabled !== false) && !connError);
      renderVfoFreqs(vfoFreqs, idx, rig.vfo);

      if (errBox && errBody) {
        if (hasError) {
          errBox.style.display = '';
          errBox.classList.toggle('conn-error', connError);
          errBody.textContent = errText;
        } else if (uiErr) {
          errBox.style.display = '';
          errBox.classList.add('conn-error');
          errBody.textContent = uiErr;
        } else {
          errBox.style.display = 'none';
          errBox.classList.remove('conn-error');
          errBody.textContent = '';
        }
      }

      if (legacyErr) legacyErr.textContent = '';

      // If there's a connection error, force the rig to appear powered off.
      card.classList.toggle('disabled', (rig.enabled === false) || connError);

      const enabled = (rig.enabled !== false) && !connError;
      if (syncBtn) {
        syncBtn.disabled = !enabled;
        syncBtn.style.display = (idx === mainIdx) ? 'none' : '';
      }
      if (freqBtn) freqBtn.disabled = !enabled;

      if (badges) {
        badges.innerHTML = '';
        if (idx === mainIdx) {
          const b = document.createElement('span');
          b.className = 'badge-main';
          b.textContent = 'MAIN';
          badges.appendChild(b);
        }
      }

      if (followWrap && followSwitch) {
        if (idx === mainIdx) {
          followWrap.style.display = 'none';
        } else {
          followWrap.style.display = '';
          const pending = followPending.has(idx) ? followPending.get(idx) : null;
          const following = (pending == null) ? (rig.follow_main !== false) : !!pending;
          followSwitch.checked = following;
          followSwitch.disabled = !enabled;
        }
      }
      renderBandButtons(bandsEl, idx, rig.frequency_hz, enabled, rig.band_presets);
      renderBandLabel(bandEl, rig.frequency_hz, rig.band_presets);
      renderModeButtons(modesEl, rig.model_id, rig.mode, enabled);
    });
  };

  const postJSON = async (url, payload) => {
    const res = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    return res.json();
  };

  const renderCapsBadges = (el, modelId) => {
    if (!el) return;
    if (modelId == null || String(modelId).trim() === '') {
      el.innerHTML = '<span class="cap-badge cap-unknown" title="Capabilities are not available until a model is selected.">Caps unknown</span>';
      return;
    }
    const model = getModel(modelId);
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
  };

  const renderModeButtons = (el, modelId, currentMode, enabled) => {
    if (!el) return;
    if (modelId == null || String(modelId).trim() === '') {
      el.innerHTML = '';
      return;
    }
    const model = getModel(modelId);
    const modes = model && Array.isArray(model.modes) ? model.modes : null;
    if (!modes || modes.length === 0) {
      el.innerHTML = '<span class="mode-badge mode-unknown" title="No supported mode list is available for this model.">Modes unknown</span>';
      return;
    }
    el.innerHTML = '';
    modes.forEach((m) => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'mode-btn' + (currentMode === m ? ' active' : '');
      btn.dataset.action = 'set-mode';
      btn.dataset.mode = m;
      btn.textContent = m;
      btn.disabled = !enabled;
      const meaning = modeMeanings[m];
      btn.title = meaning ? `${m}: ${meaning}` : `Mode: ${m}`;
      el.appendChild(btn);
    });
  };

  const setRigEnabled = async (idx, enabled) => {
    await postJSON(`/api/rig/${idx}/enabled`, { enabled: !!enabled });
    const card = document.getElementById(`rig-${idx}`);
    if (card) {
      card.dataset.enabled = enabled ? 'true' : 'false';
      card.classList.toggle('disabled', !enabled);
    }
  };

  const syncRig = async (idx) => {
    await postJSON(`/api/rig/${idx}/sync_from_source`, {});
    const card = document.getElementById(`rig-${idx}`);
    if (card) {
      card.classList.add('pulse');
      setTimeout(() => card.classList.remove('pulse'), 300);
    }
  };

  const setRigMode = async (idx, mode) => {
    await postJSON(`/api/rig/${idx}/set`, { mode });
  };

  const setRigVfo = async (idx, vfo) => {
    await postJSON(`/api/rig/${idx}/set`, { vfo });
  };

  const setRigFrequency = async (idx, hz) => {
    const res = await postJSON(`/api/rig/${idx}/set`, { frequency_hz: Math.round(Number(hz)) });
    if (res && res.status === 'error') {
      setRigUiError(idx, String(res.error || 'Failed to set frequency'));
    } else {
      clearRigUiError(idx);
    }
    return res;
  };

  const renderBandLabel = (el, hz, presets) => {
    if (!el) return;
    const p = enabledBandPresetMatch(presets, hz);
    if (p && p.label) {
      el.textContent = String(p.label);
      el.title = `Band: ${p.label}`;
      return;
    }
    const b = bandForHz(hz);
    el.textContent = b ? b.label : '';
    el.title = b ? `Band: ${b.label}` : '';
  };

  const renderBandButtons = (el, idx, hz, enabled, presets) => {
    if (!el) return;
    el.innerHTML = '';
    const currentPreset = enabledBandPresetMatch(presets, hz);
    const current = currentPreset ? { label: String(currentPreset.label) } : bandForHz(hz);
    const configured = Array.isArray(presets) ? presets.filter(p => p && p.enabled !== false && p.label && p.frequency_hz) : [];
    if (configured.length > 0) {
      const sorted = configured.slice().sort((a, b) => {
        const am = bandLabelToMeters(a.label);
        const bm = bandLabelToMeters(b.label);
        if (am != null && bm != null && am !== bm) return bm - am;
        if (am != null && bm == null) return -1;
        if (am == null && bm != null) return 1;
        return String(a.label).localeCompare(String(b.label));
      });
      for (const p of sorted) {
        const label = String(p.label);
        const hzVal = Number(p.frequency_hz);
        const b = bands.find(x => x.label === label) || null;
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'band-btn' + (current && current.label === label ? ' active' : '');
        btn.dataset.action = 'set-band';
        btn.dataset.index = String(idx);
        btn.dataset.hz = String(hzVal);
        btn.textContent = label;
        btn.disabled = !enabled;
        btn.title = b
          ? `${b.label} (${(b.lo / 1e6).toFixed(b.lo < 1e8 ? 3 : 0)}–${(b.hi / 1e6).toFixed(b.hi < 1e8 ? 3 : 0)} MHz)`
          : `${label} (${hzVal} Hz)`;
        el.appendChild(btn);
      }
      return;
    }

    for (const label of quickBandLabels) {
      const b = bands.find(x => x.label === label);
      if (!b) continue;
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'band-btn' + (current && current.label === b.label ? ' active' : '');
      btn.dataset.action = 'set-band';
      btn.dataset.index = String(idx);
      btn.dataset.hz = String(b.def);
      btn.textContent = b.label;
      btn.disabled = !enabled;
      btn.title = `${b.label} (${(b.lo / 1e6).toFixed(b.lo < 1e8 ? 3 : 0)}–${(b.hi / 1e6).toFixed(b.hi < 1e8 ? 3 : 0)} MHz)`;
      el.appendChild(btn);
    }
  };

  const parseFrequencyInput = (raw, unit) => {
    const s = String(raw || '').trim();
    if (!s) return null;
    const lower = s.toLowerCase().replace(/\s+/g, '');
    const mhz = lower.endsWith('mhz');
    const khz = lower.endsWith('khz');
    const hz = lower.endsWith('hz');
    const numStr = lower.replace(/mhz$|khz$|hz$/g, '');
    const n = Number(numStr);
    if (!isFinite(n)) return null;

    // If the user typed a unit suffix, it wins.
    if (mhz) return Math.round(n * 1000000);
    if (khz) return Math.round(n * 1000);
    if (hz) return Math.round(n);

    const u = String(unit || 'auto').toLowerCase();
    if (u === 'mhz') return Math.round(n * 1000000);
    if (u === 'khz') return Math.round(n * 1000);
    if (u === 'hz') return Math.round(n);

    // auto: heuristic (decimals mean MHz; small integers mean MHz)
    if (numStr.includes('.')) return Math.round(n * 1000000);
    if (n < 10000) return Math.round(n * 1000000);
    return Math.round(n);
  };

  const openFreqEditor = (idx) => {
    const card = document.getElementById(`rig-${idx}`);
    if (!card) return;
    const ed = $('[data-role="freq-editor"]', card);
    const input = $('[data-role="freq-input"]', card);
    const unitSel = $('[data-role="freq-unit"]', card);
    if (!ed || !input) return;
    ed.style.display = '';
    // prefer current displayed freq
    const f = $('.freq', card)?.textContent?.trim();
    input.value = f && f !== '—' ? f : '';
    if (unitSel) {
      const pref = freqUnitPref.get(idx) || 'mhz';
      unitSel.value = pref;
      unitSel.onchange = () => {
        freqUnitPref.set(idx, unitSel.value);
      };
    }
    input.focus();
    input.select();

    input.onkeydown = (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        saveFreqEditor(idx);
      } else if (e.key === 'Escape') {
        e.preventDefault();
        closeFreqEditor(idx);
      }
    };
  };

  const closeFreqEditor = (idx) => {
    const card = document.getElementById(`rig-${idx}`);
    if (!card) return;
    const ed = $('[data-role="freq-editor"]', card);
    const input = $('[data-role="freq-input"]', card);
    const unitSel = $('[data-role="freq-unit"]', card);
    if (ed) ed.style.display = 'none';
    if (input) input.value = '';
    if (unitSel) unitSel.onchange = null;
  };

  const saveFreqEditor = async (idx) => {
    const card = document.getElementById(`rig-${idx}`);
    if (!card) return;
    const input = $('[data-role="freq-input"]', card);
    const unitSel = $('[data-role="freq-unit"]', card);
    if (!input) return;
    const unit = unitSel ? unitSel.value : 'auto';
    const hz = parseFrequencyInput(input.value, unit);
    if (hz == null) return;

    const policy = rigPolicyCache.get(idx) || { allow_out_of_band: false, band_presets: [] };
    const allow = !!policy.allow_out_of_band;
    const inRange = !!enabledBandPresetMatch(policy.band_presets, hz);
    if (!allow && !inRange) {
      setRigUiError(idx, 'Frequency out of configured band ranges (enable “Allow out-of-band frequencies” for this rig to override).');
      return;
    }

    try {
      const res = await setRigFrequency(idx, hz);
      if (res && res.status === 'error') return;
      closeFreqEditor(idx);
    } catch {
      // leave editor open
    }
  };

  const refreshRigDebug = async (idx) => {
    const card = document.getElementById(`rig-${idx}`);
    if (!card) return;
    const logEl = $('[data-role="debug-log"]', card);
    if (!logEl) return;
    const wasNearBottom = (logEl.scrollTop + logEl.clientHeight) >= (logEl.scrollHeight - 24);
    const esc = (s) => String(s == null ? '' : s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
    try {
      const res = await fetch(`/api/debug/rig/${idx}`);
      const data = await res.json();
      const ev = Array.isArray(data.events) ? data.events : [];
      const lastTs = ev.length ? Number(ev[ev.length - 1]?.ts || 0) : 0;
      const cutoff = lastTs ? (lastTs - 1.0) : 0;
      const recent = cutoff ? ev.filter(e => Number(e?.ts || 0) >= cutoff) : [];
      const windowEv = (recent.length > 0) ? recent : ev.slice(-200);

      const lines = windowEv.map(e => {
        const ts = new Date((e.ts || 0) * 1000).toLocaleTimeString();
        const kind = String(e.kind || '');
        const isTx = kind.endsWith('_tx');
        const isRx = kind.endsWith('_rx');
        const arrow = isTx
          ? '<span class="dbg-arrow dbg-tx" title="TX">▶</span>'
          : (isRx ? '<span class="dbg-arrow dbg-rx" title="RX">◀</span>' : '<span class="dbg-arrow">•</span>');
        if (kind === 'rigctl_tx') return `${arrow}<span class="dbg-ts">${esc(ts)}</span> <span class="dbg-dir">TX</span> <span class="dbg-msg">${esc(e.cmd)}</span>`;
        if (kind === 'rigctl_rx') return `${arrow}<span class="dbg-ts">${esc(ts)}</span> <span class="dbg-dir">RX</span> <span class="dbg-msg">${esc((e.lines || []).join(' | '))}</span>`;
        const sem = e.semantic ? `<span class="dbg-sem">${esc(e.semantic)}</span> ` : '';
        if (kind === 'rigctld_tx') return `${arrow}<span class="dbg-ts">${esc(ts)}</span> <span class="dbg-dir">TX</span> ${sem}<span class="dbg-msg">${esc(e.cmd)}</span>`;
        if (kind === 'rigctld_rx') return `${arrow}<span class="dbg-ts">${esc(ts)}</span> <span class="dbg-dir">RX</span> ${sem}<span class="dbg-msg">${esc(`RPRT ${e.rprt} ${(e.lines || []).join(' | ')}`)}</span>`;
        return `${arrow}<span class="dbg-ts">${esc(ts)}</span> <span class="dbg-dir">${esc(kind)}</span>`;
      });
      logEl.innerHTML = lines.join('<br>');
      if (wasNearBottom) {
        logEl.scrollTop = logEl.scrollHeight;
      }
    } catch {
      logEl.textContent = '';
    }
  };

  const initControls = () => {
    $('#mainRigSelect')?.addEventListener('change', async (e) => {
      const source_index = Number(e.target.value);
      await postJSON('/api/sync', { source_index });
    });

    $('#rigctlToMainToggle')?.addEventListener('change', async (e) => {
      await postJSON('/api/rigctl_to_main', { enabled: !!e.target.checked });
    });
    $('#mainToFollowersToggle')?.addEventListener('change', async (e) => {
      await postJSON('/api/sync', { enabled: !!e.target.checked });
    });
    $('#allRigsEnabledToggle')?.addEventListener('change', async (e) => {
      await postJSON('/api/rig/enabled_all', { enabled: !!e.target.checked });
    });
    $('#toggleServerDebug')?.addEventListener('click', async () => {
      const sec = $('#serverDebugSection');
      if (!sec) return;
      const wasCollapsed = sec.classList.contains('collapsed');
      sec.classList.toggle('collapsed', !wasCollapsed);
      const body = $('.rig-section-body', sec);
      if (body) body.style.display = !wasCollapsed ? 'none' : '';
      setSectionCollapsed('server', 'debug', !wasCollapsed);
      if (wasCollapsed) await refreshServerDebug();
    });
    $('#clearServerDebug')?.addEventListener('click', () => {
      const el = $('#serverDebugLog');
      if (el) el.textContent = '';
    });
  };

  const refreshServerMeta = async () => {
    try {
      const res = await fetch('/api/rigctl_listener');
      if (!res.ok) throw new Error('bad status');
      const data = await res.json();
      const el = $('#rigctlAddr');
      if (el) el.textContent = `${data.host}:${data.port}`;
      const portEl = $('#debugPortDisplay');
      if (portEl) portEl.textContent = data.port;
    } catch {
      const el = $('#rigctlAddr');
      if (el) el.textContent = '—';
    }
  };

  const refreshServerDebug = async () => {
    const el = $('#serverDebugLog');
    if (!el) return;
    const esc = (s) => String(s == null ? '' : s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
    try {
      const res = await fetch('/api/debug/server');
      if (!res.ok) throw new Error('bad status');
      const data = await res.json();
      const ev = Array.isArray(data.events) ? data.events : [];
      const lines = ev.slice(-120).map(e => {
        const ts = new Date((e.ts || 0) * 1000).toLocaleTimeString();
        const sem = e.semantic ? `<span class="dbg-sem">${esc(e.semantic)}</span>` : '';
        if (e.kind === 'server_rx') return `<span class="dbg-ts">${esc(ts)}</span> <span class="dbg-dir dbg-rx">RX</span> ${sem} <span class="dbg-msg">${esc(e.line)}</span>`;
        if (e.kind === 'server_tx') return `<span class="dbg-ts">${esc(ts)}</span> <span class="dbg-dir dbg-tx">TX</span> ${sem} <span class="dbg-msg">${esc(e.response || (e.bytes ? e.bytes + ' bytes' : ''))}</span>`;
        return `<span class="dbg-ts">${esc(ts)}</span> <span class="dbg-dir">${esc(e.kind)}</span>`;
      });
      el.innerHTML = lines.join('<br>');
      el.scrollTop = el.scrollHeight;
    } catch {
      el.textContent = '';
    }
  };

  const connectWS = () => {
    const wsUrl = (() => {
      const proto = location.protocol === 'https:' ? 'wss' : 'ws';
      return `${proto}://${location.host}${(window.MULTIRIG_CONFIG || {}).wsPath || '/ws'}`;
    })();

    let ws;
    const open = () => {
      ws = new WebSocket(wsUrl);
      ws.onopen = () => { };
      ws.onmessage = (ev) => {
        try { bindStatus(JSON.parse(ev.data)); } catch { }
      };
      ws.onclose = () => setTimeout(open, 1500);
      ws.onerror = () => { try { ws.close(); } catch { } };
    };
    open();
  };

  window.addEventListener('DOMContentLoaded', () => {
    loadRigModels();
    refreshServerMeta();
    initControls();
    connectWS();
    setInterval(() => {
      const pane = $('#serverDebug');
      if (pane && pane.style.display !== 'none') refreshServerDebug();
      $$('.rig-card').forEach((card) => {
        const idx = Number(card.dataset.index);
        const sec = card.querySelector('.rig-section[data-section="debug"]');
        if (sec && !sec.classList.contains('collapsed') && sec.style.display !== 'none') refreshRigDebug(idx);
      });
    }, 1200);
  });

  if (typeof process !== 'undefined' && process.env && process.env.JEST_WORKER_ID) {
    globalThis.__multirig_test = {
      parseFrequencyInput,
      enabledBandPresetMatch,
      bandForHz,
      formatFreq,
      formatRw,
      bandLabelToMeters,
      getSectionCollapsed,
      setSectionCollapsed,
      applySections,
      renderVfoControls,
      renderVfoFreqs,
      setRigUiError,
      clearRigUiError,
      __setVfoFreqCache: (idx, entry) => {
        vfoFreqCache.set(idx, entry || {});
      },
      __getRigUiError: (idx) => rigUiErrorCache.get(idx),
      renderBandButtons,
      renderBandLabel,
      renderModeButtons,
      renderCapsBadges,
      ensureGrid,
      __injectRigModels: (models) => {
        rigModels = models || [];
        rigModelById = new Map();
        for (const m of rigModels) {
          if (m && m.id != null) rigModelById.set(String(m.id), m);
        }
      },
    };
  }
})();
