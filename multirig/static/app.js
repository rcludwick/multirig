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

  const bindStatus = (data) => {
    for (const el of $$('[data-bind]')) {
      const path = el.getAttribute('data-bind'); // e.g., a.frequency_hz
      const val = path.split('.').reduce((acc, k) => (acc ? acc[k] : undefined), data);
      if (el.classList.contains('freq')) {
        el.textContent = humanHz(val);
      } else if (el.classList.contains('rig-conn')) {
        el.classList.toggle('ok', !!val);
        el.title = val ? 'Connected' : 'Disconnected';
      } else if (el.classList.contains('error')) {
        el.textContent = val || '';
      } else {
        el.textContent = val ?? '—';
      }
    }
    // Sync toggle
    const sync = $('#syncToggle');
    if (sync && typeof data.sync_enabled === 'boolean') {
      sync.checked = data.sync_enabled;
    }
  };

  const postJSON = async (url, payload) => {
    const res = await fetch(url, { method: 'POST', headers: { 'Content-Type':'application/json' }, body: JSON.stringify(payload)});
    return res.json();
  };

  const initControls = () => {
    $('#syncToggle')?.addEventListener('change', async (e) => {
      const enabled = e.target.checked;
      await fetch(`/api/sync/${enabled}`, { method: 'POST' });
    });

    const setRig = async (which) => {
      const root = which === 'a' ? $('#rigA') : $('#rigB');
      const payload = {};
      for (const input of $$('[data-input]', root)) {
        const key = input.getAttribute('data-input').split('.')[1];
        let val = input.value.trim();
        if (!val) continue;
        if (key.includes('frequency') || key.includes('passband')) val = Number(val);
        payload[key] = val;
      }
      const res = await postJSON(`/api/rig/${which}/set`, payload);
      // rudimentary feedback
      root.classList.add('pulse');
      setTimeout(()=>root.classList.remove('pulse'), 300);
    };

    $('[data-action="setA"]').addEventListener('click', () => setRig('a'));
    $('[data-action="setB"]').addEventListener('click', () => setRig('b'));
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
