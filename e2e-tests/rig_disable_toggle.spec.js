const { test, expect } = require('@playwright/test');
const net = require('net');

const { ensureProfileExists, loadProfile, deleteProfile } = require('./profile_helpers');

function startFakeRigctldServer({ frequencyHz = 14074000, mode = 'USB', passband = 2400 } = {}) {
  const server = net.createServer((socket) => {
    let buf = '';
    socket.on('data', (data) => {
      buf += data.toString('utf8');
      if (!buf.includes('\n')) return;

      const line = buf.split('\n')[0].trim();
      const cmd = line.startsWith('+') ? line.slice(1) : line;

      if (cmd === 'f') {
        socket.end(`Frequency: ${frequencyHz}\nRPRT 0\n`);
        return;
      }

      if (cmd === 'm') {
        socket.end(`Mode: ${mode}\nPassband: ${passband}\nRPRT 0\n`);
        return;
      }

      socket.end('RPRT -1\n');
    });
  });

  return new Promise((resolve) => {
    server.listen(0, '127.0.0.1', () => {
      const addr = server.address();
      resolve({ server, port: addr.port });
    });
  });
}

test.describe('Dashboard - Rig enabled toggle', () => {
  test('Disabling a rig should persist and reflect in /api/status and UI after refresh/reload', async ({ page, request }) => {
    const rigA = await startFakeRigctldServer({ frequencyHz: 14074000 });
    const rigB = await startFakeRigctldServer({ frequencyHz: 7074000 });

    const profileName = 'test_dashboard_rig_disable_persists';
    const config = {
      rigs: [
        {
          name: 'Rig A',
          enabled: true,
          connection_type: 'rigctld',
          host: '127.0.0.1',
          port: rigA.port,
          poll_interval_ms: 200,
        },
        {
          name: 'Rig B',
          enabled: true,
          connection_type: 'rigctld',
          host: '127.0.0.1',
          port: rigB.port,
          poll_interval_ms: 200,
        },
      ],
      poll_interval_ms: 200,
    };

    const configYaml = JSON.stringify(config);
    await ensureProfileExists(request, profileName, { allowCreate: true, configYaml });

    try {
      await page.goto('/');
      // Use request context to load profile to avoid page reload race conditions
      await loadProfile(page.request, profileName);
      await page.reload();

      const card0 = page.locator('#rig-0');
      await expect(card0).toBeVisible();

      const power0 = card0.locator('input[data-action="power"]');
      await expect(power0).toBeChecked();

      await power0.uncheck();
      await expect(power0).not.toBeChecked();
      await expect(card0).toHaveAttribute('data-enabled', 'false');

      // Give the UI time to receive subsequent status updates (WS refresh) that might overwrite the toggle.
      await page.waitForTimeout(1800);

      await expect(power0).not.toBeChecked();
      await expect(card0).toHaveAttribute('data-enabled', 'false');

      const statusRes = await request.get('/api/status');
      expect(statusRes.ok()).toBeTruthy();
      const status = await statusRes.json();
      expect(status.rigs[0].enabled).toBe(false);

      // Reload to ensure persisted config takes effect.
      await page.reload();
      const card0b = page.locator('#rig-0');
      await expect(card0b).toBeVisible();
      const power0b = card0b.locator('input[data-action="power"]');
      await expect(power0b).not.toBeChecked();
      await expect(card0b).toHaveAttribute('data-enabled', 'false');
    } finally {
      await deleteProfile(request, profileName);
      await new Promise((resolve) => rigA.server.close(resolve));
      await new Promise((resolve) => rigB.server.close(resolve));
    }

    await expect(
      ensureProfileExists(request, profileName, { allowCreate: false })
    ).rejects.toThrow(/profile not found/);
  });
});
