const { test, expect } = require('@playwright/test');
const net = require('net');

const { ensureProfileExists, loadProfile, deleteProfile } = require('./profile_helpers');

test.describe('Sync to Followers disabled', () => {
  test('should NOT forward frequency change to follower rig when sync is disabled', async ({ request }) => {
    // 1. Setup Netmind Proxies: Rig 0 (Main) on 9006, Rig 1 (Follower) on 9007
    const mainRigProxyPort = 9006;
    const followerRigProxyPort = 9007;
    const targetPort = 4532; // rigctld dummy

    // Proxy for Main Rig (Rig 0)
    const mainProxyRes = await request.post('http://127.0.0.1:9000/api/proxies', {
      data: {
        local_port: mainRigProxyPort,
        target_host: '127.0.0.1',
        target_port: targetPort,
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
        target_port: targetPort,
        name: 'Follower_Rig_Proxy',
        protocol: 'hamlib'
      }
    });
    expect(followerProxyRes.ok()).toBeTruthy();

    // 2. Configure Multirig with two rigs and sync_enabled: false
    const config = {
      rigs: [
        {
          name: "Main Rig",
          connection_type: "rigctld",
          host: "127.0.0.1",
          port: mainRigProxyPort,
          poll_interval_ms: 200,
          band_presets: [ { label: "20m", frequency_hz: 14074000, enabled: true } ]
        },
        {
          name: "Follower Rig",
          connection_type: "rigctld",
          host: "127.0.0.1",
          port: followerRigProxyPort,
          poll_interval_ms: 200,
          follow_main: true, // This rig is configured to follow the main by default
          band_presets: [ { label: "20m", frequency_hz: 14074000, enabled: true } ]
        }
      ],
      sync_enabled: false, // <<<<<<<<<< IMPORTANT: Disable main -> followers sync
      sync_source_index: 0, // Rig 0 is the main rig
      poll_interval_ms: 200
    };
    
    const configYaml = JSON.stringify(config);

    const profileName = 'test_no_sync_to_follower';
    await ensureProfileExists(request, profileName, { allowCreate: true, configYaml });
    await loadProfile(request, profileName);
    try {
      // Give Multirig a moment to apply config and connect
      await new Promise(r => setTimeout(r, 1500));

    // 3. Send a frequency change to the Main Rig via Multirig's TCP listener
    // Multirig's TCP listener acts as a rigctl for the main rig (index 0 by default)
    const client = new net.Socket();
    const targetFreq = '14075000'; // 20m
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
    
    // Allow time for command to process and propagate (or not propagate)
    await new Promise(r => setTimeout(r, 1000));

    // 4. Verify Netmind history
    // Check Main Rig's proxy (9006): should see the command
    const mainRigHistoryRes = await request.get('http://127.0.0.1:9000/api/history', {
        params: { limit: 100, proxy_name: 'Main_Rig_Proxy' } 
    });
    const mainRigHistory = await mainRigHistoryRes.json();
    console.log("Main Rig History:", JSON.stringify(mainRigHistory, null, 2));

    const mainRigFound = mainRigHistory.find(p => 
        p.proxy_name === 'Main_Rig_Proxy' && 
        p.direction === 'TX' && 
        p.data_str.includes(`F ${targetFreq}`)
    );

    if (!mainRigFound) {
        console.log("Command not found in Main Rig Netmind history. Fetching Multirig server debug log:");
        const multirigServerDebugRes = await request.get('/api/debug/server');
        const multirigServerDebug = await multirigServerDebugRes.json();
        console.log("Multirig Server Debug:", JSON.stringify(multirigServerDebug, null, 2));
    }
    expect(mainRigFound).toBeTruthy();

    // Check Follower Rig's proxy (9007): should NOT see the command
    const followerRigHistoryRes = await request.get('http://127.0.0.1:9000/api/history', {
        params: { limit: 100, proxy_name: 'Follower_Rig_Proxy' } 
    });
    const followerRigHistory = await followerRigHistoryRes.json();
    console.log("Follower Rig History:", JSON.stringify(followerRigHistory, null, 2));

    const followerRigFound = followerRigHistory.find(p => 
        p.proxy_name === 'Follower_Rig_Proxy' && // Explicitly filter
        p.direction === 'TX' && 
        p.data_str.includes(`F ${targetFreq}`)
    );
    // Expect it to be undefined because sync is disabled
    expect(followerRigFound).toBeFalsy(); 
    } finally {
      await deleteProfile(request, profileName);
    }
    await expect(
      ensureProfileExists(request, profileName, { allowCreate: false })
    ).rejects.toThrow(/profile not found/);
  });
});
