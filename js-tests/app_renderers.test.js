
/**
 * @jest-environment jsdom
 */

// We need to load the app code. Since it is an IIFE, we can just require it.
// The app.js expects document/window to exist (jsdom provides them).
require('../multirig/static/app.js');

const {
  renderBandButtons,
  renderBandLabel,
  renderModeButtons,
  renderCapsBadges,
  __injectRigModels,
} = globalThis.__multirig_test;

describe('multirig static/app.js renderers', () => {

  describe('renderBandButtons', () => {
    let container;

    beforeEach(() => {
      container = document.createElement('div');
    });

    test('renders standard quick bands when no presets are configured', () => {
      // no presets
      renderBandButtons(container, 1, 14074000, true, []);
      
      const buttons = container.querySelectorAll('button');
      expect(buttons.length).toBeGreaterThan(0);
      expect(buttons[0].textContent).toBe('40m');
      
      // Check active state
      const active = container.querySelector('.active');
      expect(active).not.toBeNull();
      expect(active.textContent).toBe('20m'); // 14.074 is in 20m
    });

    test('renders configured presets when provided', () => {
      const presets = [
        { label: '80m', frequency_hz: 3573000, enabled: true },
        { label: '20m', frequency_hz: 14074000, enabled: true },
        { label: 'Disabled', frequency_hz: 1000, enabled: false }
      ];
      
      renderBandButtons(container, 1, 14074000, true, presets);
      
      const buttons = container.querySelectorAll('button');
      expect(buttons.length).toBe(2); // Disabled one excluded
      
      // Sorted by meters descending (80m > 20m), so 80m first
      expect(buttons[0].textContent).toBe('80m');
      expect(buttons[1].textContent).toBe('20m');
      
      const active = container.querySelector('.active');
      expect(active).not.toBeNull();
      expect(active.textContent).toBe('20m');
    });
    
    test('disables buttons when enabled=false passed', () => {
       renderBandButtons(container, 1, 14074000, false, []);
       const btn = container.querySelector('button');
       expect(btn.disabled).toBe(true);
    });
  });

  describe('renderBandLabel', () => {
    let container;
    beforeEach(() => {
      container = document.createElement('div');
    });

    test('renders standard band label', () => {
      renderBandLabel(container, 7074000, []);
      expect(container.textContent).toBe('40m');
    });

    test('renders preset label', () => {
      const presets = [
        { label: 'My 40m', lower_hz: 7000000, upper_hz: 7300000, enabled: true }
      ];
      renderBandLabel(container, 7074000, presets);
      expect(container.textContent).toBe('My 40m');
    });

    test('renders empty if out of band', () => {
      renderBandLabel(container, 100, []);
      expect(container.textContent).toBe('');
    });
  });

  describe('renderModeButtons', () => {
    let container;
    beforeEach(() => {
      container = document.createElement('div');
      __injectRigModels([
        { id: 1, modes: ['USB', 'LSB', 'AM'] },
        { id: 2, modes: [] } // Empty modes
      ]);
    });

    test('renders mode buttons for known model', () => {
      renderModeButtons(container, 1, 'USB', true);
      const buttons = container.querySelectorAll('button');
      expect(buttons.length).toBe(3);
      expect(buttons[0].textContent).toBe('USB');
      expect(buttons[0].classList.contains('active')).toBe(true);
    });

    test('renders unknown message for missing model', () => {
      renderModeButtons(container, 999, 'USB', true);
      expect(container.querySelector('.mode-unknown')).not.toBeNull();
    });
    
    test('renders unknown message for empty modes', () => {
      renderModeButtons(container, 2, 'USB', true);
      expect(container.querySelector('.mode-unknown')).not.toBeNull();
    });
  });

  describe('renderCapsBadges', () => {
    let container;
    beforeEach(() => {
      container = document.createElement('div');
      __injectRigModels([
         { 
             id: 1, 
             caps: { 
                 freq_get: 1, freq_set: 1, 
                 mode_get: 1, mode_set: 0,
                 vfo_get: 0, vfo_set: 1,
                 ptt_get: 0, ptt_set: 0
             }
         }
      ]);
    });

    test('renders capabilities badges', () => {
      renderCapsBadges(container, 1);
      const badges = container.querySelectorAll('.cap-badge');
      expect(badges.length).toBe(4); // Freq, Mode, VFO, PTT
      
      // Freq: RW (both) -> cap-on
      expect(badges[0].textContent).toContain('Freq RW');
      expect(badges[0].classList.contains('cap-on')).toBe(true);
      
      // Mode: R (get only) -> cap-on
      expect(badges[1].textContent).toContain('Mode R');
      expect(badges[1].classList.contains('cap-on')).toBe(true);
      
      // VFO: W (set only) -> cap-on
      expect(badges[2].textContent).toContain('VFO W');
      expect(badges[2].classList.contains('cap-on')).toBe(true);

      // PTT: None -> cap-off
      expect(badges[3].textContent).toBe('PTT');
      expect(badges[3].classList.contains('cap-off')).toBe(true);
    });
    
    test('renders unknown if model not found', () => {
        renderCapsBadges(container, 999);
        expect(container.textContent).toContain('Caps unknown');
    });
  });

  describe('ensureGrid', () => {
    const { ensureGrid } = globalThis.__multirig_test;
    
    beforeEach(() => {
       document.body.innerHTML = '<div id="rigGrid"></div>';
    });
    
    test('creates rig cards for new rigs', () => {
      const rigs = [
        { name: 'Rig 1', enabled: true },
        { name: 'Rig 2', enabled: false }
      ];
      ensureGrid(rigs);
      
      const grid = document.getElementById('rigGrid');
      const cards = grid.querySelectorAll('.rig-card');
      expect(cards.length).toBe(2);
      
      expect(cards[0].id).toBe('rig-0');
      expect(cards[0].querySelector('.rig-title').textContent).toBe('Rig 1');
      
      expect(cards[1].id).toBe('rig-1');
      expect(cards[1].querySelector('.rig-title').textContent).toBe('Rig 2');
    });
    
    test('rebuilds grid if rig count changes', () => {
      ensureGrid([{name: 'A'}]);
      expect(document.querySelectorAll('.rig-card').length).toBe(1);
      
      ensureGrid([{name: 'A'}, {name: 'B'}]);
      expect(document.querySelectorAll('.rig-card').length).toBe(2);
    });
    
    test('updates titles if grid exists and count matches', () => {
      ensureGrid([{name: 'Old Name'}]);
      const card = document.getElementById('rig-0');
      
      ensureGrid([{name: 'New Name'}]);
      expect(document.getElementById('rig-0')).toBe(card); // Same element
      expect(card.querySelector('.rig-title').textContent).toBe('New Name');
    });
  });

});

