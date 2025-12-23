const { test, expect } = require('@playwright/test');
const net = require('net');
const { ensureProfileExists, loadProfile, deleteProfile, createProxy } = require('./profile_helpers');

test.describe('Band Change Out-of-Band Validation', () => {
  test('should allow setting out-of-band frequency when allowed', async ({ page, request }) => {
    const proxyPort = 9021;
    const targetPort = 4532;

    const proxyRes = await createProxy(request, {
      local_port: proxyPort,
      target_host: '127.0.0.1',
      target_port: targetPort,
      name: 'OOB_Allowed_Test_Rig',
      protocol: 'hamlib'
    });
    expect(proxyRes.ok()).toBeTruthy();

    const config = {
      rigs: [
        {
          name: "OOB Test Rig",
          connection_type: "rigctld",
          host: "127.0.0.1",
          port: proxyPort,
          poll_interval_ms: 200,
          allow_out_of_band: true,
          band_presets: [
             { label: "20m", frequency_hz: 14074000, enabled: true }
          ]
        }
      ],
      poll_interval_ms: 200
    };
    
    const configYaml = JSON.stringify(config);

    const profileName = 'test_band_change_out_of_band_validation';
    try {
      await ensureProfileExists(request, profileName, { allowCreate: true, configYaml });
      // Use request context to load profile to avoid page reload race conditions
      await loadProfile(page.request, profileName);
      await page.reload();

      await page.waitForTimeout(1000);
      await page.goto('/');
      
      const rigCard = page.locator('#rig-0');
      await expect(rigCard).toBeVisible();

      const freqBtn = rigCard.locator('button[data-action="edit-freq"]');
      await freqBtn.click();
      
      const input = rigCard.locator('input[data-role="freq-input"]');
      await expect(input).toBeVisible();
      
      const targetFreq = '7074000';
      await input.fill(targetFreq);
      
      const saveBtn = rigCard.locator('button[data-action="freq-save"]');
      await saveBtn.click();
      
      const errorBox = rigCard.locator('[data-role="error"]');
      await expect(errorBox).not.toBeVisible();
      
      const startTime = Date.now() / 1000;
      let found = false;
      for (let i = 0; i < 20; i++) {
          const historyRes = await request.get('http://127.0.0.1:9000/api/history', {
              params: { limit: 20 }
          });
          const history = await historyRes.json();
          found = history.find(p => 
              p.direction === 'TX' && 
              p.data_str.includes(`F ${targetFreq}`)
          );
          if (found) break;
          await page.waitForTimeout(200);
      }
      expect(found).toBeTruthy();
    } finally {
      await deleteProfile(request, profileName);
      await request.delete('http://127.0.0.1:9000/api/proxies/9004').catch(() => {});
    }
  });
});
