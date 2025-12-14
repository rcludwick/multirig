(() => {
  const $ = (sel, root=document) => root.querySelector(sel);
  const $$ = (sel, root=document) => Array.from(root.querySelectorAll(sel));

  // Dark mode toggle
  const initTheme = () => {
    const t = localStorage.getItem('theme');
    if (t) document.documentElement.dataset.theme = t;
    const btn = $('#darkToggle');
    if (btn) btn.addEventListener('click', () => {
      const next = document.documentElement.dataset.theme === 'dark' ? '' : 'dark';
      document.documentElement.dataset.theme = next;
      localStorage.setItem('theme', next);
    });
  };

  const humanHz = (hz) => {
    if (hz == null || isNaN(hz)) return '—';
    const s = hz.toString();
    // Insert thousands separators for readability
    return s.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  };

  const ensureGrid = (rigs) => {
    const grid = $('#rigGrid');
    if (!grid) return;
    // Rebuild grid if counts differ or missing cards
    const existing = $$('.rig-card', grid);
    if (existing.length !== rigs.length) {
      grid.innerHTML = '';
      rigs.forEach((rig, idx) => {
        const card = document.createElement('div');
        card.className = 'rig-card';
        card.id = `rig-${idx}`;
        card.dataset.index = String(idx);
        card.innerHTML = `
          <div class="rig-title">${rig.name || `Rig ${idx+1}`}</div>
          <div class="rig-conn">●</div>
          <div class="freq">—</div>
          <div class="mode">—</div>
          <div class="error"></div>
          <div class="controls">
            <input type="number" step="1" min="0" placeholder="Freq (Hz)" data-input="frequency_hz">
            <input type="text" placeholder="Mode (e.g., USB, LSB, DIGU)" data-input="mode">
            <input type="number" step="1" placeholder="Passband (Hz)" data-input="passband">
            <button data-action="set" data-index="${idx}">Set</button>
          </div>`;
        grid.appendChild(card);
      });
      // Wire up buttons
      grid.addEventListener('click', (e) => {
        const btn = e.target.closest('button[data-action="set"]');
        if (!btn) return;
        const idx = Number(btn.dataset.index);
        setRig(idx);
      });
    } else {
      // Update titles if names changed
      rigs.forEach((rig, idx) => {
        const card = $(`#rig-${idx}`);
        if (card) {
          const title = $('.rig-title', card);
          if (title) title.textContent = rig.name || `Rig ${idx+1}`;
        }
      });
    }
  };

  const bindStatus = (data) => {
    const rigs = Array.isArray(data.rigs) ? data.rigs : [];
    ensureGrid(rigs);
    rigs.forEach((rig, idx) => {
      const card = document.getElementById(`rig-${idx}`);
      if (!card) return;
      const conn = $('.rig-conn', card);
      const freq = $('.freq', card);
      const mode = $('.mode', card);
      const err = $('.error', card);
      if (conn) {
        conn.classList.toggle('ok', !!rig.connected);
        conn.title = rig.connected ? 'Connected' : 'Disconnected';
      }
      if (freq) freq.textContent = humanHz(rig.frequency_hz);
      if (mode) mode.textContent = rig.mode || '—';
      if (err) err.textContent = rig.error || '';
    });
    // Sync controls
    const sync = $('#syncToggle');
    if (sync && typeof data.sync_enabled === 'boolean') {
      sync.checked = data.sync_enabled;
    }
    const srcSel = $('#sourceSelect');
    if (srcSel) {
      // Rebuild options if mismatch
      if (srcSel.options.length !== rigs.length) {
        srcSel.innerHTML = '';
        rigs.forEach((r, i) => {
          const opt = document.createElement('option');
          opt.value = String(i);
          opt.textContent = r.name || `Rig ${i+1}`;
          srcSel.appendChild(opt);
        });
      } else {
        // Update labels
        rigs.forEach((r, i) => {
          const opt = srcSel.options[i];
          if (opt) opt.textContent = r.name || `Rig ${i+1}`;
        });
      }
      if (typeof data.sync_source_index === 'number') {
        srcSel.value = String(data.sync_source_index);
      }
    }
  };

  const postJSON = async (url, payload) => {
    const res = await fetch(url, { method: 'POST', headers: { 'Content-Type':'application/json' }, body: JSON.stringify(payload)});
    return res.json();
  };

  const setRig = async (index) => {
    const root = document.getElementById(`rig-${index}`);
    if (!root) return;
    const payload = {};
    for (const input of $$('[data-input]', root)) {
      const key = input.getAttribute('data-input');
      let val = input.value.trim();
      if (!val) continue;
      if (key.includes('frequency') || key.includes('passband')) val = Number(val);
      payload[key] = val;
    }
    await postJSON(`/api/rig/${index}/set`, payload);
    // rudimentary feedback
    root.classList.add('pulse');
    setTimeout(()=>root.classList.remove('pulse'), 300);
  };

  const initControls = () => {
    $('#syncToggle')?.addEventListener('change', async (e) => {
      const enabled = e.target.checked;
      await postJSON('/api/sync', { enabled });
    });
    $('#sourceSelect')?.addEventListener('change', async (e) => {
      const source_index = Number(e.target.value);
      await postJSON('/api/sync', { source_index });
    });
  };

  const connectWS = () => {
    const wsUrl = (()=>{
      const proto = location.protocol === 'https:' ? 'wss' : 'ws';
      return `${proto}://${location.host}${(window.MULTIRIG_CONFIG||{}).wsPath || '/ws'}`;
    })();

    let ws;
    const open = () => {
      ws = new WebSocket(wsUrl);
      ws.onopen = () => {};
      ws.onmessage = (ev) => {
        try { bindStatus(JSON.parse(ev.data)); } catch {}
      };
      ws.onclose = () => setTimeout(open, 1500);
      ws.onerror = () => { try { ws.close(); } catch {} };
    };
    open();
  };

  window.addEventListener('DOMContentLoaded', () => {
    initTheme();
    initControls();
    connectWS();
  });
})();
