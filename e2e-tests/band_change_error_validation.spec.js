const { test, expect } = require('@playwright/test');

test.describe('Band Change Error Validation', () => {
  test('should show error when setting out-of-band frequency if not allowed', async ({ page, request }) => {
    // 1. Setup Netmind Proxy: Listen on 9003 -> 4532
    const proxyPort = 9003;
    const targetPort = 4532;
    
    const proxyRes = await request.post('http://127.0.0.1:9000/api/proxies', {
      params: {
        local_port: proxyPort,
        target_host: '127.0.0.1',
        target_port: targetPort,
        name: 'Error_Test_Rig',
        protocol: 'hamlib'
      }
    });
    expect(proxyRes.ok()).toBeTruthy();

    // 2. Configure Multirig
    const config = {
      rigs: [
        {
          name: "Error Test Rig",
          connection_type: "rigctld",
          host: "127.0.0.1",
          port: proxyPort,
          poll_interval_ms: 200,
          allow_out_of_band: false, // Enforce bands
          band_presets: [
             // Only 20m enabled (14.0 - 14.35 MHz)
             { label: "20m", frequency_hz: 14074000, enabled: true }
          ]
        }
      ],
      poll_interval_ms: 200
    };
    
    const configYaml = JSON.stringify(config);
    const importRes = await request.post('http://127.0.0.1:8000/api/config/import', {
      data: configYaml,
      headers: { 'Content-Type': 'text/yaml' }
    });
    expect(importRes.ok()).toBeTruthy();
    
    await page.waitForTimeout(1000);

    // 3. Go to Dashboard
    await page.goto('/');
    const rigCard = page.locator('#rig-0');
    await expect(rigCard).toBeVisible();

    // 4. Open Freq Editor
    const freqBtn = rigCard.locator('button[data-action="edit-freq"]');
    await freqBtn.click();
    
    const input = rigCard.locator('input[data-role="freq-input"]');
    await expect(input).toBeVisible();
    
    // 5. Enter 40m freq (7.074 MHz) which is out of 20m band
    await input.fill('7074000');
    
    // 6. Save
    const saveBtn = rigCard.locator('button[data-action="freq-save"]');
    await saveBtn.click();
    
    // 7. Check for Error
    const errorBox = rigCard.locator('[data-role="error"]');
    await expect(errorBox).toBeVisible();
    await expect(errorBox).toContainText('Frequency out of configured band ranges');
    
    // 8. Verify Netmind did NOT receive the command
    // We check history for F 7074000
    const historyRes = await request.get('http://127.0.0.1:9000/api/history', {
        params: { limit: 20 }
    });
    const history = await historyRes.json();
    const found = history.find(p => 
        p.direction === 'TX' && 
        p.data_str.includes('F 7074000')
    );
    expect(found).toBeUndefined();
  });
});
