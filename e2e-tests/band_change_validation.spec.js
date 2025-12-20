const { test, expect } = require('@playwright/test');
const net = require('net');
const { ensureProfileExists, loadProfile, deleteProfile, createProxy } = require('./profile_helpers');

test.describe('Band Change Validation', () => {
  test('should send correct frequency command when band is changed in UI', async ({ page, request }) => {
    const proxyPort = 9022;
    const targetPort = 4532;

    const proxyRes = await createProxy(request, {
      local_port: proxyPort,
      target_host: '127.0.0.1',
      target_port: targetPort,
      name: 'Band_Change_Test_Rig',
      protocol: 'hamlib'
    });
    expect(proxyRes.ok()).toBeTruthy();

    const config = {
      rigs: [
        {
          name: "Band Test Rig",
          connection_type: "rigctld",
          host: "127.0.0.1",
          port: proxyPort,
          poll_interval_ms: 200,
          band_presets: [
             { label: "20m", frequency_hz: 14074000, enabled: true },
             { label: "40m", frequency_hz: 7074000, enabled: true }
          ]
        }
      ],
      poll_interval_ms: 200
    };
    
    const configYaml = JSON.stringify(config);

    const profileName = 'test_band_change_validation';
    await ensureProfileExists(request, profileName, { allowCreate: true, configYaml });
    await loadProfile(request, profileName);
    try {
      await page.waitForTimeout(1000);
      await page.goto('/');
      
      const rigCard = page.locator('#rig-0');
      await expect(rigCard).toBeVisible();
      
      const btn40m = rigCard.locator('button', { hasText: '40m' });
      await expect(btn40m).toBeVisible();
      
      const startTime = Date.now() / 1000;
      await btn40m.click();
      let found = false;
      for (let i = 0; i < 20; i++) {
          const historyRes = await request.get('http://127.0.0.1:9000/api/history', {
              params: { limit: 20 }
          });
          const history = await historyRes.json();
          found = history.find(p => 
              p.timestamp > startTime &&
              p.direction === 'TX' &&
              (
                  p.data_str.includes('F 7074000') || 
                  p.semantic.includes('SET FREQ: 7074000')
              )
          );
          
          if (found) break;
          await page.waitForTimeout(200);
      }
      expect(found).toBeTruthy();
    } finally {
      await deleteProfile(request, profileName);
      await request.delete('http://127.0.0.1:9000/api/proxies/9002').catch(() => {});
    }
    await expect(
      ensureProfileExists(request, profileName, { allowCreate: false })
    ).rejects.toThrow(/profile not found/);
  });
});
