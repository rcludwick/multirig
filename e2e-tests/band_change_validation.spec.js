const { test, expect } = require('@playwright/test');
const yaml = require('js-yaml'); // Need to install js-yaml or just construct JSON object?
// Multirig import API takes YAML text.
// Or I can just send JSON? API import_config: data = yaml.safe_load(body).
// yaml.safe_load works on JSON too (JSON is valid YAML).
// So I can send JSON string.

test.describe('Band Change Validation', () => {
  test('should send correct frequency command when band is changed in UI', async ({ page, request }) => {
    // 1. Setup Netmind Proxy: Listen on 9002 -> 4532
    const proxyPort = 9002;
    const targetPort = 4532;
    
    const proxyRes = await request.post('http://127.0.0.1:9000/api/proxies', {
      params: {
        local_port: proxyPort,
        target_host: '127.0.0.1',
        target_port: targetPort,
        name: 'Band_Test_Rig',
        protocol: 'hamlib'
      }
    });
    expect(proxyRes.ok()).toBeTruthy();

    // 2. Configure Multirig with this rig
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
    
    // Convert to JSON string (valid YAML)
    const configYaml = JSON.stringify(config);
    
    const importRes = await request.post('http://127.0.0.1:8000/api/config/import', {
      data: configYaml,
      headers: { 'Content-Type': 'text/yaml' }
    });
    expect(importRes.ok()).toBeTruthy();
    
    // Give it a moment to connect
    await page.waitForTimeout(1000);

    // 3. Go to Dashboard
    await page.goto('/');
    
    // Wait for Rig Card
    const rigCard = page.locator('#rig-0');
    await expect(rigCard).toBeVisible();
    
    // Find Band buttons. They are usually in a band presets section.
    // The UI structure for bands: .band-grid > button
    // Let's look for button with text "40m"
    const btn40m = rigCard.locator('button', { hasText: '40m' });
    await expect(btn40m).toBeVisible();
    
    // Clear history/mark timestamp? 
    // Netmind history API returns last N packets. We'll look for recent ones.
    const startTime = Date.now() / 1000;

    // 4. Click 40m
    await btn40m.click();
    
    // Verify UI feedback (optional, active class?)
    // await expect(btn40m).toHaveClass(/active/); 

    // 5. Verify Netmind received "F 7074000"
    // Poll for it
    let found = false;
    for (let i = 0; i < 20; i++) {
        const historyRes = await request.get('http://127.0.0.1:9000/api/history', {
            params: { limit: 20 }
        });
        const history = await historyRes.json();
        
        // Look for TX packet with F 7074000
        // Semantic: "SET FREQ: 7074000"
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
  });
});
