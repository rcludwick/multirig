const { test, expect } = require('@playwright/test');
const net = require('net');
const { ensureProfileExists, loadProfile, deleteProfile, createProxy } = require('./profile_helpers');

test.describe('Disabled Band Validation', () => {
  test('should NOT forward frequency command for disabled band via rigctl', async ({ request }) => {
    const proxyPort = 9023;
    const targetPort = 4532;

    const proxyRes = await createProxy(request, {
      local_port: proxyPort,
      target_host: '127.0.0.1',
      target_port: targetPort,
      name: 'Disabled_Band_Test_Rig',
      protocol: 'hamlib'
    });
    expect(proxyRes.ok()).toBeTruthy();

    const config = {
      rigs: [
        {
          name: "Disabled Band Test Rig",
          connection_type: "rigctld",
          host: "127.0.0.1",
          port: proxyPort,
          poll_interval_ms: 200,
          allow_out_of_band: false,
          band_presets: [
             { label: "40m", frequency_hz: 7074000, enabled: true },
             { label: "80m", frequency_hz: 3573000, enabled: false }
          ]
        }
      ],
      poll_interval_ms: 200
    };
    
    const configYaml = JSON.stringify(config);

    const profileName = 'test_band_disabled_validation';
    await ensureProfileExists(request, profileName, { allowCreate: true, configYaml });
    await loadProfile(request, profileName);
    try {
      await new Promise(r => setTimeout(r, 1000));

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
      expect(found).toBeFalsy(); 
    } finally {
      await deleteProfile(request, profileName);
      await request.delete('http://127.0.0.1:9000/api/proxies/9005').catch(() => {});
    }
  });
});
