const { test, expect } = require('@playwright/test');
const net = require('net');

test.describe('Disabled Band Validation', () => {
  test('should NOT forward frequency command for disabled band via rigctl', async ({ request }) => {
    // 1. Setup Netmind Proxy: Listen on 9005 -> 4532
    const proxyPort = 9005;
    const targetPort = 4532;
    
    const proxyRes = await request.post('http://127.0.0.1:9000/api/proxies', {
      params: {
        local_port: proxyPort,
        target_host: '127.0.0.1',
        target_port: targetPort,
        name: 'Disabled_Band_Rig',
        protocol: 'hamlib'
      }
    });
    expect(proxyRes.ok()).toBeTruthy();

    // 2. Configure Multirig
    const config = {
      rigs: [
        {
          name: "Disabled Band Test Rig",
          connection_type: "rigctld",
          host: "127.0.0.1",
          port: proxyPort,
          poll_interval_ms: 200,
          allow_out_of_band: false, // Strict enforcement
          band_presets: [
             { label: "40m", frequency_hz: 7074000, enabled: true },
             { label: "80m", frequency_hz: 3573000, enabled: false } // Disabled!
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
    
    await new Promise(r => setTimeout(r, 1000));

    // 3. Connect to Multirig Rigctl (4534) and send F 3573000 (80m, disabled)
    const client = new net.Socket();
    const cmd = 'F 3573000\n';
    
    const sendPromise = new Promise((resolve, reject) => {
        client.connect(4534, '127.0.0.1', () => {
            client.write(cmd, () => {
                client.end();
                resolve();
            });
        });
        client.on('error', reject);
    });
    
    await sendPromise;
    
    // 4. Verify Netmind did NOT receive the command
    // We expect checking history to yield NO result for this frequency
    
    let found = false;
    for (let i = 0; i < 10; i++) {
        const historyRes = await request.get('http://127.0.0.1:9000/api/history', {
            params: { limit: 20 }
        });
        const history = await historyRes.json();
        
        found = history.find(p => 
            p.direction === 'TX' && 
            p.data_str.includes('F 3573000')
        );
        
        if (found) break;
        await new Promise(r => setTimeout(r, 200));
    }
    
    // This assertion is expected to FAIL currently because code doesn't enforce it yet
    expect(found).toBeFalsy(); 
  });
});
