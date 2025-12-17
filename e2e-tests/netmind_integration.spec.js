const { test, expect } = require('@playwright/test');
const net = require('net');

test.describe('Netmind Integration', () => {
  test('should forward dump_caps from Multirig to Netmind to Rig', async ({ request }) => {
    // 1. Setup Netmind Proxy: Listen on 9001, Forward to 4532 (Dummy Rig)
    const proxyRes = await request.post('http://127.0.0.1:9000/api/proxies', {
      params: {
        local_port: 9001,
        target_host: '127.0.0.1',
        target_port: 4532,
        name: 'Multirig_Test_Path',
        protocol: 'hamlib'
      }
    });
    expect(proxyRes.ok()).toBeTruthy();

    // 2. Configure Multirig to use the Netmind Proxy as "Rig 1"
    const configRes = await request.get('http://127.0.0.1:8000/api/config');
    expect(configRes.ok()).toBeTruthy();
    const config = await configRes.json();

    config.rigs = [
      {
        name: "Netmind Path Rig",
        connection_type: "rigctld",
        host: "127.0.0.1",
        port: 9001,
        enabled: true,
        poll_interval_ms: 1000
      }
    ];
    config.rigctl_listen_port = 4534;

    const updateRes = await request.post('http://127.0.0.1:8000/api/config', {
      data: config
    });
    expect(updateRes.ok()).toBeTruthy();

    // Allow some time for Multirig to reconnect
    await new Promise(resolve => setTimeout(resolve, 1500));

    // 3. Connect to Multirig's Rigctl Server (Port 4534) and send \dump_caps
    const client = new net.Socket();
    const responsePromise = new Promise((resolve, reject) => {
      client.connect(4534, '127.0.0.1', () => {
        client.write('\\dump_caps\n');
      });

      let dataBuffer = '';
      client.on('data', (data) => {
        dataBuffer += data.toString();
        // Wait for reasonable amount of data
        if (dataBuffer.length > 50) {
             // Don't close immediately, wait a bit for more packets
             setTimeout(() => {
                 client.end();
                 resolve(dataBuffer);
             }, 500);
        }
      });

      client.on('error', (e) => {
          console.error("Socket error:", e);
          reject(e);
      });
      
      // Safety timeout
      setTimeout(() => {
          client.destroy();
          resolve(dataBuffer);
      }, 3000);
    });

    const rigctlResponse = await responsePromise;
    console.log("Multirig response length:", rigctlResponse.length);
    // console.log("Multirig response snippet:", rigctlResponse.substring(0, 100));

    // 4. Verify Netmind received the command
    // Poll for history
    let found = undefined;
    for (let i = 0; i < 10; i++) {
        const historyRes = await request.get('http://127.0.0.1:9000/api/history', {
            params: { limit: 50 }
        });
        expect(historyRes.ok()).toBeTruthy();
        const history = await historyRes.json();

        // Look for the packet
        found = history.find(p => 
            p.direction === 'TX' && 
            (
                (p.data_str && p.data_str.includes('dump_caps')) || 
                (p.semantic && p.semantic.includes('dump_caps'))
            )
        );
        
        if (found) break;
        await new Promise(r => setTimeout(r, 500));
    }

    if (!found) {
        console.log("Packet not found in history. Fetching last history for debug:");
        const debugRes = await request.get('http://127.0.0.1:9000/api/history', {
            params: { limit: 20 }
        });
        const debugHistory = await debugRes.json();
        console.log(JSON.stringify(debugHistory, null, 2));
    }

    expect(found).toBeDefined();
  });
});