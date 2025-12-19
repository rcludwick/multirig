const { test, expect } = require('@playwright/test');
const net = require('net');

const { ensureProfileExists, loadProfile, deleteProfile } = require('./profile_helpers');

function startFakeRigctldServer() {
  const server = net.createServer((socket) => {
    let buf = '';
    socket.on('data', (data) => {
      buf += data.toString('utf8');
      if (!buf.includes('\n')) return;

      const line = buf.split('\n')[0].trim();
      const cmd = line.startsWith('+') ? line.slice(1) : line;

      if (cmd === 'f') {
        socket.end('Frequency: 14074000\nRPRT 0\n');
        return;
      }

      if (cmd === 'm') {
        socket.end('Mode: USB\nPassband: 2400\nRPRT 0\n');
        return;
      }

      if (cmd === '\\dump_state') {
        // RigctldBackend strips the leading "dump_state:" header if present.
        // parse_dump_state_ranges() then reads lines[2] and lines[3] as min/max ranges.
        socket.end(
          [
            'dump_state:',
            'stub',
            'stub',
            '1000000 2000000000',
            '1000000 2000000000',
            'RPRT 0',
            '',
          ].join('\n')
        );
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

test.describe('Settings - Band presets reset', () => {
  test('Reset to Default should populate all supported bands for the rig', async ({ page, request }) => {
    const { server, port } = await startFakeRigctldServer();

    const profileName = 'test_settings_band_reset_all_supported';
    const config = {
      rigs: [
        {
          name: 'Settings Band Reset Rig',
          connection_type: 'rigctld',
          host: '127.0.0.1',
          port,
          poll_interval_ms: 200,
          // Start with a small set so the reset behavior is measurable.
          band_presets: [
            { label: '20m', frequency_hz: 14074000, enabled: true },
            { label: '40m', frequency_hz: 7074000, enabled: true },
          ],
        },
      ],
      poll_interval_ms: 200,
    };

    const configYaml = JSON.stringify(config);
    await ensureProfileExists(request, profileName, { allowCreate: true, configYaml });

    try {
      await loadProfile(request, profileName);

      await page.goto('/settings');

      const rigFieldset = page.locator('#rigList fieldset').first();
      await expect(rigFieldset).toBeVisible();

      const bandToggle = rigFieldset.locator('button[data-action="toggle-band-presets"]');
      await bandToggle.click();

      const rows = rigFieldset.locator('.band-row');
      await expect(rows).toHaveCount(2);

      await rigFieldset.locator('button[data-action="band-reset"]').click();

      await expect(rows).toHaveCount(16);

      await expect(rigFieldset.locator('.band-row', { hasText: '160m' })).toBeVisible();
      await expect(rigFieldset.locator('.band-row', { hasText: '23cm' })).toBeVisible();
    } finally {
      await deleteProfile(request, profileName);
      await new Promise((resolve) => server.close(resolve));
    }

    await expect(
      ensureProfileExists(request, profileName, { allowCreate: false })
    ).rejects.toThrow(/profile not found/);
  });
});
