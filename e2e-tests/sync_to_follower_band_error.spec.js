const { test, expect } = require('@playwright/test');
const net = require('net');

const { ensureProfileExists, loadProfile, deleteProfile } = require('./profile_helpers');

test.describe('Sync to Follower Band Error', () => {
  test('should report error and not sync to follower if band is incompatible', async ({ request }) => {
    // 1. Setup Netmind Proxies: Rig 0 (Main) on 9008, Rig 1 (Follower) on 9009
    const mainRigProxyPort = 9008;
    const followerRigProxyPort = 9009;
    const targetRigctldPort = 4532; // rigctld dummy

    // Proxy for Main Rig (Rig 0)
    const mainProxyRes = await request.post('http://127.0.0.1:9000/api/proxies', {
      data: {
        local_port: mainRigProxyPort,
        target_host: '127.0.0.1',
        target_port: targetRigctldPort,
        name: 'Main_Rig_Proxy',
        protocol: 'hamlib'
      }
    });
    expect(mainProxyRes.ok()).toBeTruthy();

    // Proxy for Follower Rig (Rig 1)
    const followerProxyRes = await request.post('http://127.0.0.1:9000/api/proxies', {
      data: {
        local_port: followerRigProxyPort,
        target_host: '127.0.0.1',
        target_port: targetRigctldPort,
        name: 'Follower_Rig_Proxy',
        protocol: 'hamlib'
      }
    });
    expect(followerProxyRes.ok()).toBeTruthy();

    // 2. Configure Multirig with two rigs, sync_enabled: true
    // Follower rig only supports 20m, main supports 20m and 40m
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
          allow_out_of_band: false, // Enforce bands
          band_presets: [ 
            { label: "20m", frequency_hz: 14074000, enabled: true, lower_hz: 14000000, upper_hz: 14350000 }
            // 40m is missing/disabled for follower
          ]
        }
      ],
      sync_enabled: true, // <<<<<<<<<< IMPORTANT: Enable main -> followers sync
      sync_source_index: 0, // Rig 0 is the main rig
      poll_interval_ms: 200
    };
    
    const configYaml = JSON.stringify(config);

    const profileName = 'test_sync_to_follower_band_error';
    await ensureProfileExists(request, profileName, { allowCreate: true, configYaml });
    await loadProfile(request, profileName);
    try {
      // Give Multirig a moment to apply config and connect
      await new Promise(r => setTimeout(r, 2000)); // Increased wait time

    // 3. Send a frequency change to the Main Rig (40m) via Multirig's TCP listener
    const client = new net.Socket();
    const targetFreq = '7074000'; // 40m frequency
    const cmd = `F ${targetFreq}\n`;
    
    const sendPromise = new Promise((resolve, reject) => {
        client.connect(4534, '127.0.0.1', () => { // Connect to Multirig's rigctl listener
            client.write(cmd, () => {
                client.end();
                resolve();
            });
        });
        client.on('error', reject);
    });
    
    await sendPromise;
    
    // Allow time for command to process and sync
    await new Promise(r => setTimeout(r, 2500)); // Need enough time for SyncService to run

    // 4. Verify Netmind history and Multirig Status
    // Main Rig's proxy (9008): should see the command
    let mainRigFound = undefined;
    for (let i = 0; i < 5; i++) { // Poll a few times if needed
        const historyRes = await request.get('http://127.0.0.1:9000/api/history', {
            params: { limit: 100, proxy_name: 'Main_Rig_Proxy' } 
        });
        const history = await historyRes.json();
        mainRigFound = history.find(p => 
            p.proxy_name === 'Main_Rig_Proxy' && 
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

    // Follower Rig's proxy (9009): should NOT see the command
    let followerRigFound = undefined;
    for (let i = 0; i < 5; i++) {
        const historyRes = await request.get('http://127.0.0.1:9000/api/history', {
            params: { limit: 100, proxy_name: 'Follower_Rig_Proxy' } 
        });
        const history = await historyRes.json();
        followerRigFound = history.find(p => 
            p.proxy_name === 'Follower_Rig_Proxy' && 
            p.direction === 'TX' && 
            p.data_str.includes(`F ${targetFreq}`)
        );
        if (followerRigFound) break;
        await new Promise(r => setTimeout(r, 500));
    }
    expect(followerRigFound).toBeFalsy(); 

    // Verify Follower Rig's status API shows an error
    // Wait for sync service to run (poll_interval_ms is 1000ms)
    await new Promise(r => setTimeout(r, 1500));
    
    let statusFound = false;
    for (let i = 0; i < 10; i++) {
        const statusRes = await request.get('/api/status');
        const status = await statusRes.json();
        const followerRigStatus = status.rigs[1]; // Rig 1 is the follower
        
        if (followerRigStatus && followerRigStatus.last_error && 
            followerRigStatus.last_error.includes("Frequency out of configured band ranges")) {
            statusFound = true;
            break;
        }
        await new Promise(r => setTimeout(r, 500));
    }
    if (!statusFound) {
        const statusRes = await request.get('/api/status');
        const status = await statusRes.json();
        console.log("Final status:", JSON.stringify(status, null, 2));
    }
    expect(statusFound).toBeTruthy();
    } finally {
      await deleteProfile(request, profileName);
    }
    await expect(
      ensureProfileExists(request, profileName, { allowCreate: false })
    ).rejects.toThrow(/profile not found/);
  });
});
