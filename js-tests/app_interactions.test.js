
const { describe, test, expect, beforeEach, afterEach } = require('@jest/globals');

// Mock fetch
global.fetch = jest.fn();

// Setup DOM for app.js
document.body.innerHTML = `
<div id="rigGrid"></div>
<input type="checkbox" id="rigctlToMainToggle">
<input type="checkbox" id="mainToFollowersToggle">
<input type="checkbox" id="allRigsEnabledToggle">
<select id="mainRigSelect"></select>
`;

// Load app.js (execution populates globalThis.__multirig_test)
require('../multirig/static/app.js');

const app = globalThis.__multirig_test;

describe('app.js interactions', () => {
    beforeEach(() => {
        document.body.innerHTML = `
        <div id="rigGrid"></div>
        <input type="checkbox" id="rigctlToMainToggle">
        <input type="checkbox" id="mainToFollowersToggle">
        <input type="checkbox" id="allRigsEnabledToggle">
        <select id="mainRigSelect"></select>
        `;
        global.fetch.mockClear();

        // Setup initial grid
        app.ensureGrid([{ name: "Rig 1" }, { name: "Rig 2" }]);
    });

    test('bindStatus updates UI elements', () => {
        const status = {
            rigs: [
                {
                    name: "Rig 1", connected: true, frequency_hz: 14074000,
                    mode: "USB", enabled: true, follow_main: false,
                    band_presets: []
                },
                {
                    name: "Rig 2", connected: false, frequency_hz: 7074000,
                    mode: "LSB", enabled: true, follow_main: true,
                    band_presets: []
                }
            ],
            sync_source_index: 0,
            rigctl_to_main_enabled: true,
            sync_enabled: true,
            all_rigs_enabled: true
        };

        app.bindStatus(status);

        const grid = document.getElementById('rigGrid');
        const cards = grid.querySelectorAll('.rig-card');
        expect(cards.length).toBe(2);

        // Check Rig 1
        const r1 = cards[0];
        expect(r1.querySelector('.freq').textContent).toBe('14.074000');
        expect(r1.querySelector('.mode').textContent).toBe('USB');
        expect(r1.classList.contains('disconnected')).toBe(false);
        const r1badge = r1.querySelector('.badge-main');
        expect(r1badge).not.toBeNull(); // Is MAIN

        // Check Rig 2
        const r2 = cards[1];
        expect(r2.querySelector('.freq').textContent).toBe('7.074000');
        expect(r2.classList.contains('disconnected')).toBe(true); // connected=false
        expect(r2.querySelector('.badge-main')).toBeNull();

        // Toggles
        expect(document.getElementById('rigctlToMainToggle').checked).toBe(true);
    });

    test('sync button triggers update', async () => {
        // Mock post response
        global.fetch.mockResolvedValue({
            json: () => Promise.resolve({ status: 'ok' })
        });

        // Must setup grid listener (ensureGrid does this but we need to verify listener attached)
        // ensureGrid attaches listeners to #rigGrid ONCE in app.js scope usually?
        // Wait, app.js attaches listeners to grid in `initControls` which is called on DOMContentLoaded.
        // But `ensureGrid` ALSO attaches listeners?
        // Let's check ensureGrid code in app.js
        // No, ensureGrid REBUILDS innerHTML.
        // Listeners usually attached to grid container which is permanent?
        // In app.js lines 396: grid.addEventListener...
        // This is inside `initControls` or `loadRigModels`?
        // It's inside `loadRigModels`?
        // No, lines 396 seem to be inside `ensureGrid` or the function that wraps it?
        // Let's look at lines 284: const ensureGrid ...
        // Then lines 396: grid.addEventListener ...
        // Wait, lines 396 are AFTER ensureGrid?
        // Lines 396 seem to be INSIDE `ensureGrid` or the function that wraps it?
        // App.js structure (lines 1 to 1211):
        // It seems `ensureGrid` ends around line 394?
        // Then lines 396 is inside... `loadRigModels`?
        // Let's re-read the file snippet (Step 448).
        // ensureGrid (284).
        // ... grid.appendChild(card) (393).
        // }); (394).
        // // Wire up buttons (395).
        // grid.addEventListener... (396).

        // Ah, `ensureGrid` defines `grid` as `$('#rigGrid')`.
        // Does `ensureGrid` ADD listeners every time?
        // If it does, we might have duplicate listeners if called multiple times?
        // Or maybe ensureGrid is only for creating cards.
        // Wait, where does `ensureGrid` end?
        // The snippet lines 284-394 is `ensureGrid`.
        // But the indentation of 396 matches 284 (2 spaces).
        // So line 396 is outside `ensureGrid`?
        // Wait, line 284: `  const ensureGrid = (rigs) => {`
        // Line 394: `});` closes `rigs.forEach`.
        // Line 571: `  };` closes ensureGrid?
        // If so, yes it adds listeners every time.
        // BUT `bindStatus` calls `ensureGrid`.
        // `ensureGrid` checks `if (needsRebuild)` (293).
        // If `needsRebuild` is true, it clears innerHTML and rebuilds.
        // Does it add listeners only if `needsRebuild`?
        // The `grid.addEventListener` block (396) seems to be INSIDE `ensureGrid`?
        // Actually, if it is inside `ensureGrid`, it adds listeners every time `ensureGrid` is called?
        // But `ensureGrid` is called by `bindStatus` (every 1s).
        // If it adds listeners every 1s, that's a memory leak/performance issue.
        // I should check if it guards against this.
        // Or maybe it's outside?
        // 395: `      // Wire up buttons`
        // 396: `      grid.addEventListener...`
        // 571: `  };` closes ensureGrid?
        // If so, yes it adds listeners every time.
        // BUT `bindStatus` calls `ensureGrid`.
        // `ensureGrid` checks `needsRebuild`.
        // Lines 285: `const grid = $('#rigGrid');`
        // `if (!grid) return;`
        // `const needsRebuild = ...`
        // If `!needsRebuild`, does it exit?
        // No, it doesn't show an early return if `!needsRebuild`.
        // It just skips the DOM reconstruction (lines 294-394).
        // BUT it seems to proceed to line 396?
        // If line 396 is executed every time, that's a bug in `app.js`.
        // I should fix that bug too! 
        // It should only add listeners ONCE, e.g. in `initControls` or check if added.

        // Wait, let's verify if 396 is inside ensureGrid.
        // Yes, indentation suggests so.
        // I'll fix this in app.js as well.

        // Back to test:
        global.fetch.mockResolvedValue({
            json: () => Promise.resolve({ status: 'ok' })
        });

        // ensure listeners attached
        const grid = document.getElementById('rigGrid');

        const status = {
            rigs: [{ name: "Rig 1", connected: true }, { name: "Rig 2", connected: true }],
            sync_source_index: 0
        };
        app.bindStatus(status);

        const r2 = grid.children[1]; // Rig 2
        const syncBtn = r2.querySelector('button[data-action="sync"]');
        expect(syncBtn).not.toBeNull();

        syncBtn.click();

        expect(global.fetch).toHaveBeenCalledWith('/api/rig/1/sync_from_source', expect.anything());
    });

    test('set-mode button triggers API', async () => {
        global.fetch.mockResolvedValue({ json: () => Promise.resolve({ status: 'ok' }) });
        app.ensureGrid([{ name: "Rig 1", model_id: 123 }]);
        // Need to render mode buttons? bindStatus calls renderModeButtons
        // renderModeButtons needs rig model or list?
        // Let's manually trigger setRigMode via simulation if we can't easily find button?
        // Or inject mode buttons.
        const grid = document.getElementById('rigGrid');
        const card = grid.firstChild;
        const modesDiv = card.querySelector('[data-role="modes"]');
        modesDiv.innerHTML = '<button data-action="set-mode" data-mode="USB" data-index="0">USB</button>';

        const btn = modesDiv.querySelector('button');
        btn.click();

        expect(global.fetch).toHaveBeenCalledWith('/api/rig/0/set', expect.objectContaining({
            body: JSON.stringify({ mode: "USB" })
        }));
    });

    test('set-vfo button triggers API', async () => {
        global.fetch.mockResolvedValue({ json: () => Promise.resolve({ status: 'ok' }) });
        const grid = document.getElementById('rigGrid');
        const card = grid.firstChild;
        const vfoDiv = card.querySelector('[data-role="vfo-controls"]');
        vfoDiv.innerHTML = '<button data-action="set-vfo" data-vfo="VFOA" data-index="0">A</button>';

        vfoDiv.querySelector('button').click();

        expect(global.fetch).toHaveBeenCalledWith('/api/rig/0/set', expect.objectContaining({
            body: JSON.stringify({ vfo: "VFOA" })
        }));
    });

    test('follow-main toggle triggers API', async () => {
        global.fetch.mockResolvedValue({ json: () => Promise.resolve({ status: 'ok' }) });
        const grid = document.getElementById('rigGrid');
        // bindStatus to create toggle
        app.bindStatus({
            rigs: [{ name: "Rig 1" }, { name: "Rig 2" }],
            sync_source_index: 0
        });
        const card = grid.children[1]; // Rig 2 (index 1)
        const toggle = card.querySelector('input[data-action="follow-main"]');

        toggle.click(); // changing checking state?
        // We simulate change event
        const event = new Event('change', { bubbles: true });
        toggle.dispatchEvent(event);

        expect(global.fetch).toHaveBeenCalledWith('/api/rig/1/follow_main', expect.objectContaining({
            body: JSON.stringify({ follow_main: toggle.checked })
        }));
    });

    test('freq editor flow', async () => {
        global.fetch.mockResolvedValue({ json: () => Promise.resolve({ status: 'ok' }) });
        // Enable allow_out_of_band to avoid policy error
        app.bindStatus({ rigs: [{ name: "Rig 1", frequency_hz: 14000, allow_out_of_band: true }] });
        const grid = document.getElementById('rigGrid');
        const card = grid.firstChild;

        const editBtn = card.querySelector('button[data-action="edit-freq"]');
        editBtn.click();

        const editor = card.querySelector('.freq-editor');
        expect(editor.style.display).not.toBe('none');

        const input = editor.querySelector('input');
        input.value = '14.200';

        const saveBtn = editor.querySelector('button[data-action="freq-save"]');
        saveBtn.click();

        // Wait for async handler to complete
        await new Promise(resolve => setTimeout(resolve, 0));

        expect(global.fetch).toHaveBeenCalledWith('/api/rig/0/set', expect.objectContaining({
            body: JSON.stringify({ frequency_hz: 14200000 })
        })); // 14.2 MHz default

        // Editor should close?
        expect(editor.style.display).toBe('none');
    });

    test('connectWS initializes websocket', async () => {
        // Mock WebSocket
        const mockWS = {
            close: jest.fn(),
        };
        global.WebSocket = jest.fn(() => mockWS);

        app.__connectWS();

        expect(global.WebSocket).toHaveBeenCalled();
        // Trigger message
        const msgEvent = { data: JSON.stringify({ rigs: [] }) };
        mockWS.onmessage(msgEvent);

        // Trigger error/close to cover those paths
        mockWS.onerror();
        mockWS.onclose();

        // Wait for reconnect timeout?
        // Timeout is 1500ms. We can use jest fake timers if we want to test reconnect loop.
        // For now, executing lines is enough.
    });


    test('power toggle', async () => {
        global.fetch.mockResolvedValue({ json: () => Promise.resolve({ status: 'ok' }) });
        app.bindStatus({ rigs: [{ name: "Rig 1" }] });
        const grid = document.getElementById('rigGrid');
        const card = grid.firstChild;
        const toggle = card.querySelector('input[data-action="power"]');

        toggle.click(); // toggle
        const event = new Event('change', { bubbles: true });
        toggle.dispatchEvent(event);

        expect(global.fetch).toHaveBeenCalledWith('/api/rig/0/enabled', expect.objectContaining({
            body: JSON.stringify({ enabled: toggle.checked })
        }));
    });

    // Invert LCD test (local state only)
    test('invert lcd toggle', () => {
        // Create local storage mock if simpler, or just check calls?
        // jsdom supports localStorage.
        app.bindStatus({ rigs: [{ name: "Rig 1" }] });
        const grid = document.getElementById('rigGrid');
        const card = grid.firstChild;

        // Assuming invert toggle is somewhere? Usually in settings but here we check if it is in grid?
        // Actually invert LCD is usually in settings page, not grid?
        // App.js lines 511: input[data-action="invert-lcd"].
        // Where is it in grid? Maybe unrelated to grid?
        // The event listener is ON grid.
        // If I create such button in grid it should work.
        card.innerHTML += '<input type="checkbox" data-icon="invert-lcd" data-action="invert-lcd" data-index="0">';
        const toggle = card.querySelector('input[data-action="invert-lcd"]');

        toggle.click();
        const event = new Event('change', { bubbles: true });
        toggle.dispatchEvent(event);

        // Should update local storage
        expect(localStorage.getItem('multirig.lcd.inverted.0')).toBe('1');
    });

    test('toggle section collapses section', () => {
        app.ensureGrid([{ name: "Rig 1" }]);
        const r1 = document.getElementById('rig-0');
        const vfoSec = r1.querySelector('.rig-section[data-section="vfo"]');
        const btn = vfoSec.querySelector('button[data-action="toggle-section"]');

        // Initially maybe expanded or collapsed?
        // Code defaults? localStorage?
        // Simulate click
        btn.click();

        // Verify class toggle
        // We need to check if setSectionCollapsed called?
        // Or check classList
        // It toggles.
        // We can check if localStorage.setItem called?
        // Or just class.
        // If it was not collapsed, it becomes collapsed.
        // app.js defaults debug to collapsed. others unknown?
        // Check manually:
        const isCollapsed = vfoSec.classList.contains('collapsed');
        btn.click();
        expect(vfoSec.classList.contains('collapsed')).toBe(!isCollapsed);
    });

    test('refreshServerMeta updates DOM', async () => {
        global.fetch.mockResolvedValue({
            ok: true,
            json: () => Promise.resolve({ host: '1.2.3.4', port: 1234 })
        });
        document.body.innerHTML += '<div id="rigctlAddr"></div><div id="debugPortDisplay"></div>';

        await app.refreshServerMeta();

        expect(document.getElementById('rigctlAddr').textContent).toBe('1.2.3.4:1234');
        expect(document.getElementById('debugPortDisplay').textContent).toBe('1234');
    });

    test('refreshServerDebug updates DOM', async () => {
        global.fetch.mockResolvedValue({
            ok: true,
            json: () => Promise.resolve({
                events: [
                    { ts: 1000, kind: 'server_rx', line: 'cat' },
                    { ts: 1001, kind: 'server_tx', response: 'meow' }
                ]
            })
        });
        document.body.innerHTML += '<div id="serverDebugLog"></div>';

        await app.refreshServerDebug();

        const log = document.getElementById('serverDebugLog');
        expect(log.innerHTML).toContain('cat');
        expect(log.innerHTML).toContain('meow');
        expect(log.innerHTML).toContain('RX');
        expect(log.innerHTML).toContain('TX');
    });

});

