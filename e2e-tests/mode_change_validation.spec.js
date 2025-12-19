const { test, expect } = require('@playwright/test');

const { ensureProfileExists, loadProfile, deleteProfile } = require('./profile_helpers');

test.describe('Mode Change Validation', () => {
  test('should send correct mode command when a mode button is clicked in UI', async ({ page, request }) => {
    // 1. Setup Netmind Proxy: Listen on 9022 -> 4532 (rigctld dummy)
    const proxyPort = 9022;
    const targetPort = 4532;

    const proxyRes = await request.post('http://127.0.0.1:9000/api/proxies', {
      data: {
        local_port: proxyPort,
        target_host: '127.0.0.1',
        target_port: targetPort,
        name: 'Mode_Test_Rig',
        protocol: 'hamlib',
      },
    });
    expect(proxyRes.ok()).toBeTruthy();

    // 2. Configure Multirig with this rig.
    // model_id is required for the dashboard to render mode buttons from rig_models.json.
    const config = {
      rigs: [
        {
          name: 'Mode Test Rig',
          connection_type: 'rigctld',
          host: '127.0.0.1',
          port: proxyPort,
          poll_interval_ms: 200,
          // This model has USB/LSB/etc in rig_models.json.
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

      // 3. Verify Netmind received the mode command.
      let found = null;
      for (let i = 0; i < 20; i++) {
        const historyRes = await request.get('http://127.0.0.1:9000/api/history', {
          params: { limit: 50, proxy_name: 'Mode_Test_Rig' },
        });
        expect(historyRes.ok()).toBeTruthy();
        const history = await historyRes.json();

        found = history.find((p) =>
          (p.timestamp == null || p.timestamp > startTime) &&
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
    }

    await expect(
      ensureProfileExists(request, profileName, { allowCreate: false })
    ).rejects.toThrow(/profile not found/);
  });
});
