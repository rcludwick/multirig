const { test, expect } = require('@playwright/test');
const net = require('net');
const { ensureProfileExists, loadProfile, deleteProfile, createProxy } = require('./profile_helpers');

test.describe('Sync to Follower Band Error', () => {
  test('should report error and not sync to follower if band is incompatible', async ({ request }) => {
    const mainRigProxyPort = 9027;
    const followerRigProxyPort = 9028;
    const targetRigctldPort = 4532;

    const mainProxyRes = await createProxy(request, {
      local_port: mainRigProxyPort,
      target_host: '127.0.0.1',
      target_port: targetRigctldPort,
      name: 'Sync_Error_Main_Rig_Proxy',
      protocol: 'hamlib'
    });
    expect(mainProxyRes.ok()).toBeTruthy();

    const followerProxyRes = await createProxy(request, {
      local_port: followerRigProxyPort,
      target_host: '127.0.0.1',
      target_port: targetRigctldPort,
      name: 'Sync_Error_Follower_Rig_Proxy',
      protocol: 'hamlib'
    });
    expect(followerProxyRes.ok()).toBeTruthy();

    const config = {
      rigs: [
        {
          name: "Main Rig",
          connection_type: "rigctld",
          host: "127.0.0.1",
          port: mainRigProxyPort,
          poll_interval_ms: 200,
          band_presets: [ 
            { label: "20m", frequency_hz: 14074000, enabled: true },
            { label: "40m", frequency_hz: 7074000, enabled: true }
          ]
        },
        {
          name: "Follower Rig",
          connection_type: "rigctld",
          host: "127.0.0.1",
          port: followerRigProxyPort,
          poll_interval_ms: 200,
          follow_main: true, 
          allow_out_of_band: false,
          band_presets: [ 
            { label: "20m", frequency_hz: 14074000, enabled: true, lower_hz: 14000000, upper_hz: 14350000 }
          ]
        }
      ],
      sync_enabled: true,
      sync_source_index: 0,
      poll_interval_ms: 200
    };
    
    const configYaml = JSON.stringify(config);

    const profileName = 'test_sync_to_follower_band_error';
    await ensureProfileExists(request, profileName, { allowCreate: true, configYaml });
    await loadProfile(request, profileName);
    try {
      await new Promise(r => setTimeout(r, 2000));

      const client = new net.Socket();
      const targetFreq = '7074000';
      const cmd = `F ${targetFreq}\n`;
      
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
      await new Promise(r => setTimeout(r, 2500));
    // Main Rig's proxy: should see the command
    let mainRigFound = undefined;
    const mainProxyName = 'Sync_Error_Main_Rig_Proxy';
    const followerProxyName = 'Sync_Error_Follower_Rig_Proxy';
    for (let i = 0; i < 5; i++) { // Poll a few times if needed
        const historyRes = await request.get('http://127.0.0.1:9000/api/history', {
            params: { limit: 500, proxy_name: mainProxyName } 
        });
        const history = await historyRes.json();
        mainRigFound = history.find(p => 
            p.proxy_name === mainProxyName && 
            p.direction === 'TX' && 
            p.data_str.includes(`F ${targetFreq}`)
        );
        if (mainRigFound) break;
        await new Promise(r => setTimeout(r, 500));
    }
    if (!mainRigFound) {
        const multirigServerDebugRes = await request.get('/api/debug/server');
        const multirigServerDebug = await multirigServerDebugRes.json();
        console.log("Multirig Server Debug:", JSON.stringify(multirigServerDebug, null, 2));
    }
    expect(mainRigFound).toBeTruthy();

    // Follower Rig's proxy: should NOT see the command
    let followerRigFound = undefined;
    for (let i = 0; i < 5; i++) {
        const historyRes = await request.get('http://127.0.0.1:9000/api/history', {
            params: { limit: 500, proxy_name: followerProxyName } 
        });
        const history = await historyRes.json();
        followerRigFound = history.find(p => 
            p.proxy_name === followerProxyName && 
            p.direction === 'TX' && 
            p.data_str.includes(`F ${targetFreq}`)
        );
        if (followerRigFound) break;
        await new Promise(r => setTimeout(r, 500));
    }
    expect(followerRigFound).toBeFalsy(); 

      await new Promise(r => setTimeout(r, 1500));
    
      let statusFound = false;
      for (let i = 0; i < 10; i++) {
          const statusRes = await request.get('/api/status');
          const status = await statusRes.json();
          const followerRigStatus = status.rigs[1];
          
          if (followerRigStatus && followerRigStatus.last_error && 
              followerRigStatus.last_error.includes("Frequency out of configured band ranges")) {
              statusFound = true;
              break;
          }
          await new Promise(r => setTimeout(r, 500));
      }
      expect(statusFound).toBeTruthy();
    } finally {
      await deleteProfile(request, profileName);
      await request.delete(`http://127.0.0.1:9000/api/proxies/${mainRigProxyPort}`).catch(() => {});
      await request.delete(`http://127.0.0.1:9000/api/proxies/${followerRigProxyPort}`).catch(() => {});
    }
  });
});
