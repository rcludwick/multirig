const { test, expect } = require('@playwright/test');
const net = require('net');
const { ensureProfileExists, loadProfile, deleteProfile, createProxy } = require('./profile_helpers');

test.describe('Band Change Error Validation', () => {
  test('should show error when setting out-of-band frequency if not allowed', async ({ page, request }) => {
    const proxyPort = 9020;
    const targetPort = 4532;

    const proxyRes = await createProxy(request, {
      local_port: proxyPort,
      target_host: '127.0.0.1',
      target_port: targetPort,
      name: 'Band_Error_Test_Rig',
      protocol: 'hamlib'
    });
    expect(proxyRes.ok()).toBeTruthy();

    const config = {
      rigs: [
        {
          name: "Error Test Rig",
          connection_type: "rigctld",
          host: "127.0.0.1",
          port: proxyPort,
          poll_interval_ms: 200,
          allow_out_of_band: false,
          band_presets: [
             { label: "20m", frequency_hz: 14074000, enabled: true }
          ]
        }
      ],
      poll_interval_ms: 200
    };
    
    const configYaml = JSON.stringify(config);

    const profileName = 'test_band_change_error_validation';
    try {
      await ensureProfileExists(request, profileName, { allowCreate: true, configYaml });
      await loadProfile(request, profileName);
      await page.waitForTimeout(1000);
      await page.goto('/');
      
      const rigCard = page.locator('#rig-0');
      await expect(rigCard).toBeVisible();

      const freqBtn = rigCard.locator('button[data-action="edit-freq"]');
      await freqBtn.click();
      
      const input = rigCard.locator('input[data-role="freq-input"]');
      await expect(input).toBeVisible();
      
      await input.fill('7074000');
      
      const saveBtn = rigCard.locator('button[data-action="freq-save"]');
      await saveBtn.click();
      
      const errorBox = rigCard.locator('[data-role="error"]');
      await expect(errorBox).toBeVisible();
      await expect(errorBox).toContainText('Frequency out of configured band ranges');
      
      const historyRes = await request.get('http://127.0.0.1:9000/api/history', {
          params: { limit: 20 }
      });
      const history = await historyRes.json();
      const found = history.find(p => 
          p.direction === 'TX' && 
          p.data_str.includes('F 7074000')
      );
      expect(found).toBeUndefined();
    } finally {
      await deleteProfile(request, profileName);
      await request.delete('http://127.0.0.1:9000/api/proxies/9003').catch(() => {});
    }
  });
});
