const { test, expect } = require('@playwright/test');
const net = require('net');
const { ensureProfileExists, loadProfile, deleteProfile, createProxy } = require('./profile_helpers');

test.describe('Mode Change Validation', () => {
  test('should send correct mode command when a mode button is clicked in UI', async ({ page, request }) => {
    const proxyPort = 9024;
    const targetPort = 4532;

    const proxyRes = await createProxy(request, {
      local_port: proxyPort,
      target_host: '127.0.0.1',
      target_port: targetPort,
      name: 'Mode_Change_Test_Rig',
      protocol: 'hamlib'
    });
    expect(proxyRes.ok()).toBeTruthy();

    const config = {
      rigs: [
        {
          name: 'Mode Test Rig',
          connection_type: 'rigctld',
          host: '127.0.0.1',
          port: proxyPort,
          poll_interval_ms: 200,
          model_id: 29001,
        },
      ],
      poll_interval_ms: 200,
    };

    const configYaml = JSON.stringify(config);

    const profileName = 'test_mode_change_validation';
    await ensureProfileExists(request, profileName, { allowCreate: true, configYaml });
    await loadProfile(request, profileName);

    try {
      await page.goto('/');

      const rigCard = page.locator('#rig-0');
      await expect(rigCard).toBeVisible();

      const usbBtn = rigCard.locator('button[data-action="set-mode"]', { hasText: 'USB' });
      await expect(usbBtn).toBeVisible();

      const startTime = Date.now() / 1000;

      await usbBtn.click();

      let found = null;
      const proxyName = 'Mode_Change_Test_Rig';
      for (let i = 0; i < 20; i++) {
        const historyRes = await request.get('http://127.0.0.1:9000/api/history', {
          params: { limit: 500, proxy_name: proxyName },
        });
        expect(historyRes.ok()).toBeTruthy();
        const history = await historyRes.json();

        found = history.find((p) =>
          (p.timestamp == null || p.timestamp > startTime) &&
          p.proxy_name === proxyName &&
          p.direction === 'TX' &&
          typeof p.data_str === 'string' &&
          p.data_str.includes('M USB')
        );

        if (found) break;
        await page.waitForTimeout(200);
      }

      expect(found).toBeTruthy();
    } finally {
      await deleteProfile(request, profileName);
      await request.delete(`http://127.0.0.1:9000/api/proxies/${proxyPort}`).catch(() => {});
    }
  });
});
