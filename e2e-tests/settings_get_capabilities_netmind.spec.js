const { test, expect } = require('@playwright/test');

const { ensureProfileExists, loadProfile, deleteProfile, createProxy } = require('./profile_helpers');

const NETMIND_BASE = 'http://127.0.0.1:9000';

async function resetNetmind(request) {
  return;
}

test.describe('Settings - Get capabilities (Netmind)', () => {
  test('clicking Get capabilities should run dump_caps and update badges', async ({ page, request }) => {
    await resetNetmind(request);

    const proxyName = `Multirig_Caps_UI_${Date.now()}`;

    const proxyRes = await createProxy(request, {
      local_port: 9001,
      target_host: '127.0.0.1',
      target_port: 4532,
      name: proxyName,
      protocol: 'hamlib',
    });
    expect(proxyRes.ok()).toBeTruthy();

    const profileName = 'test_settings_get_capabilities_netmind';
    const configYaml = JSON.stringify({
      rigs: [
        {
          name: 'Caps UI Rig',
          connection_type: 'rigctld',
          host: '127.0.0.1',
          port: 9001,
          poll_interval_ms: 200,
          model_id: 2,
        },
      ],
      poll_interval_ms: 200,
    });

    await ensureProfileExists(request, profileName, { allowCreate: true, configYaml });

    try {
      await loadProfile(request, profileName);
      await page.goto('/settings');

      const rigFieldset = page.locator('#rigList fieldset').first();
      await expect(rigFieldset).toBeVisible();

      const capsEl = rigFieldset.locator('.caps-badges');
      await expect(capsEl).toContainText('Caps unknown');

      const btn = rigFieldset.locator('button[data-action="caps"]');
      await expect(btn).toBeVisible();

      const respPromise = page.waitForResponse((resp) => {
        return resp.url().includes('/api/test-rig') && resp.request().method() === 'POST';
      });
      await btn.click();
      const resp = await respPromise;
      expect(resp.ok()).toBeTruthy();

      await expect(rigFieldset.locator('.test-result')).toContainText('Capabilities updated.');

      await expect(capsEl).not.toContainText('Caps unknown');
      await expect(capsEl.locator('.cap-badge')).toHaveCount(4);
      let found = undefined;
      for (let i = 0; i < 10; i++) {
        const historyRes = await request.get(`${NETMIND_BASE}/api/history`, {
          params: { limit: 200 },
        });
        expect(historyRes.ok()).toBeTruthy();
        const history = await historyRes.json();

        found = history.find((p) =>
          p.direction === 'TX' &&
          p.proxy_name === proxyName &&
          ((p.data_str && p.data_str.includes('dump_caps')) ||
            (p.semantic && p.semantic.includes('dump_caps')))
        );

        if (found) break;
        await new Promise((r) => setTimeout(r, 500));
      }

      expect(found).toBeDefined();
    } finally {
      await deleteProfile(request, profileName);
      await request.delete(`${NETMIND_BASE}/api/proxies/9001`).catch(() => {});
    }
  });
});
