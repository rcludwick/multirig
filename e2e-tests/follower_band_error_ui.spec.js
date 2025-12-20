const { test, expect } = require('@playwright/test');
const net = require('net');

const { ensureProfileExists, loadProfile, deleteProfile, createProxy } = require('./profile_helpers');

const waitForFollowerError = async (page, containsText) => {
  const errBox = page.locator('#rig-1 [data-role="error"]');
  await expect(errBox).toBeVisible({ timeout: 10_000 });
  if (containsText) {
    await expect(errBox).toContainText(containsText, { timeout: 10_000 });
  }
};

const setupTwoRigProfile = async ({ request, profileName, mainRigProxyPort, followerRigProxyPort }) => {
  const targetRigctldPort = 4532;

  const mainProxyRes = await createProxy(request, {
    local_port: mainRigProxyPort,
    target_host: '127.0.0.1',
    target_port: targetRigctldPort,
    name: `${profileName}_Main_Rig_Proxy`,
    protocol: 'hamlib',
  });
  expect(mainProxyRes.ok()).toBeTruthy();

  const followerProxyRes = await createProxy(request, {
    local_port: followerRigProxyPort,
    target_host: '127.0.0.1',
    target_port: targetRigctldPort,
    name: `${profileName}_Follower_Rig_Proxy`,
    protocol: 'hamlib',
  });
  expect(followerProxyRes.ok()).toBeTruthy();

  // Main supports 20m + 40m (with explicit ranges so UI manual entry allows it).
  // Follower supports only 20m, so any 40m freq will fail and should surface as last_error.
  const config = {
    rigs: [
      {
        name: 'Main Rig',
        connection_type: 'rigctld',
        host: '127.0.0.1',
        port: mainRigProxyPort,
        poll_interval_ms: 200,
        allow_out_of_band: false,
        band_presets: [
          { label: '20m', frequency_hz: 14074000, enabled: true, lower_hz: 14000000, upper_hz: 14350000 },
          { label: '40m', frequency_hz: 7074000, enabled: true, lower_hz: 7000000, upper_hz: 7300000 },
        ],
      },
      {
        name: 'Follower Rig',
        connection_type: 'rigctld',
        host: '127.0.0.1',
        port: followerRigProxyPort,
        poll_interval_ms: 200,
        follow_main: true,
        allow_out_of_band: false,
        band_presets: [
          { label: '20m', frequency_hz: 14074000, enabled: true, lower_hz: 14000000, upper_hz: 14350000 },
        ],
      },
    ],
    sync_enabled: true,
    rigctl_to_main_enabled: true,
    sync_source_index: 0,
    poll_interval_ms: 200,
  };

  const configYaml = JSON.stringify(config);
  await ensureProfileExists(request, profileName, { allowCreate: true, configYaml });
  await loadProfile(request, profileName);
};

test.describe('Follower band incompatibility error (UI)', () => {
  test('manual main frequency edit shows follower error', async ({ page, request }) => {
    const profileName = 'test_follower_band_error_ui_manual';
    try {
      await setupTwoRigProfile({ request, profileName, mainRigProxyPort: 9030, followerRigProxyPort: 9031 });

      await page.goto('/');
      await expect(page.locator('#rig-0')).toBeVisible();
      await expect(page.locator('#rig-1')).toBeVisible();

      // Edit main rig frequency to 40m.
      await page.locator('#rig-0 button[data-action="edit-freq"]').click();
      const editor = page.locator('#rig-0 [data-role="freq-editor"]');
      await expect(editor).toBeVisible();

      // 7.074 MHz = 7074000 Hz.
      await editor.locator('[data-role="freq-input"]').fill('7.074');
      await editor.locator('button[data-action="freq-save"]').click();

      await waitForFollowerError(page, 'Frequency out of configured band ranges');
    } finally {
      await deleteProfile(request, profileName);
      await request.delete('http://127.0.0.1:9000/api/proxies/9030').catch(() => {});
      await request.delete('http://127.0.0.1:9000/api/proxies/9031').catch(() => {});
    }
  });

  test('rigctl TCP freq change shows follower error', async ({ page, request }) => {
    const profileName = 'test_follower_band_error_ui_rigctl_tcp';
    try {
      await setupTwoRigProfile({ request, profileName, mainRigProxyPort: 9032, followerRigProxyPort: 9033 });

      await page.goto('/');
      await expect(page.locator('#rig-0')).toBeVisible();
      await expect(page.locator('#rig-1')).toBeVisible();

      // Send freq change to rigctl listener (simulating WSJT-X / hamlib client).
      const targetFreq = '7074000';
      const cmd = `F ${targetFreq}\n`;
      await new Promise((resolve, reject) => {
        const client = new net.Socket();
        client.connect(4534, '127.0.0.1', () => {
          client.write(cmd, () => {
            client.end();
            resolve();
          });
        });
        client.on('error', reject);
      });

      await waitForFollowerError(page, 'Frequency out of configured band ranges');
    } finally {
      await deleteProfile(request, profileName);
      await request.delete('http://127.0.0.1:9000/api/proxies/9032').catch(() => {});
      await request.delete('http://127.0.0.1:9000/api/proxies/9033').catch(() => {});
    }
  });

  test('clicking an incompatible band button shows follower error', async ({ page, request }) => {
    const profileName = 'test_follower_band_error_ui_band_click';
    try {
      await setupTwoRigProfile({ request, profileName, mainRigProxyPort: 9034, followerRigProxyPort: 9035 });

      await page.goto('/');
      await expect(page.locator('#rig-0')).toBeVisible();
      await expect(page.locator('#rig-1')).toBeVisible();

      // Click main rig's 40m preset button.
      const btn40 = page.locator('#rig-0 button[data-action="set-band"]', { hasText: '40m' });
      await expect(btn40).toBeVisible();
      await btn40.click();

      await waitForFollowerError(page, 'Frequency out of configured band ranges');
    } finally {
      await deleteProfile(request, profileName);
      await request.delete('http://127.0.0.1:9000/api/proxies/9034').catch(() => {});
      await request.delete('http://127.0.0.1:9000/api/proxies/9035').catch(() => {});
    }
  });
});
