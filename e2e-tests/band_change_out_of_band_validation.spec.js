const { test, expect } = require('@playwright/test');

test.describe('Band Change Out-of-Band Validation', () => {
  test('should allow setting out-of-band frequency when allowed', async ({ page, request }) => {
    // 1. Setup Netmind Proxy: Listen on 9004 -> 4532
    const proxyPort = 9004;
    const targetPort = 4532;
    
    const proxyRes = await request.post('http://127.0.0.1:9000/api/proxies', {
      params: {
        local_port: proxyPort,
        target_host: '127.0.0.1',
        target_port: targetPort,
        name: 'OOB_Test_Rig',
        protocol: 'hamlib'
      }
    });
    expect(proxyRes.ok()).toBeTruthy();

    // 2. Configure Multirig
    const config = {
      rigs: [
        {
          name: "OOB Test Rig",
          connection_type: "rigctld",
          host: "127.0.0.1",
          port: proxyPort,
          poll_interval_ms: 200,
          allow_out_of_band: true, // Allow OOB
          band_presets: [
             // Only 20m enabled
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
    const targetFreq = '7074000';
    await input.fill(targetFreq);
    
    // 6. Save
    const saveBtn = rigCard.locator('button[data-action="freq-save"]');
    await saveBtn.click();
    
    // 7. Check for Error - Should NOT exist
    const errorBox = rigCard.locator('[data-role="error"]');
    // It might exist in DOM but be hidden.
    await expect(errorBox).not.toBeVisible();
    
    // 8. Verify Netmind received the command
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
  });
});
