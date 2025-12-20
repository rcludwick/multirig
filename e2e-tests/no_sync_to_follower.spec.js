const { test, expect } = require('@playwright/test');
const net = require('net');

const { ensureProfileExists, loadProfile, deleteProfile, createProxy } = require('./profile_helpers');

test.describe('Sync to Followers disabled', () => {
  test('should NOT forward frequency change to follower rig when sync is disabled', async ({ request }) => {
    const mainRigProxyPort = 9025;
    const followerRigProxyPort = 9026;
    const targetRigctldPort = 4532;

    const mainProxyRes = await createProxy(request, {
      local_port: mainRigProxyPort,
      target_host: '127.0.0.1',
      target_port: targetRigctldPort,
      name: 'No_Sync_Main_Rig_Proxy',
      protocol: 'hamlib'
    });
    expect(mainProxyRes.ok()).toBeTruthy();

    const followerProxyRes = await createProxy(request, {
      local_port: followerRigProxyPort,
      target_host: '127.0.0.1',
      target_port: targetRigctldPort,
      name: 'No_Sync_Follower_Rig_Proxy',
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
          band_presets: [ { label: "20m", frequency_hz: 14074000, enabled: true } ]
        },
        {
          name: "Follower Rig",
          connection_type: "rigctld",
          host: "127.0.0.1",
          port: followerRigProxyPort,
          poll_interval_ms: 200,
          follow_main: true,
          band_presets: [ { label: "20m", frequency_hz: 14074000, enabled: true } ]
        }
      ],
      sync_enabled: false,
      sync_source_index: 0,
      poll_interval_ms: 200
    };
    
    const configYaml = JSON.stringify(config);

    const profileName = 'test_no_sync_to_follower';
    await ensureProfileExists(request, profileName, { allowCreate: true, configYaml });
    await loadProfile(request, profileName);
    try {
      await new Promise(r => setTimeout(r, 1500));

      const client = new net.Socket();
      const targetFreq = '14075000';
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
      await new Promise(r => setTimeout(r, 1000));

      const mainProxyName = 'No_Sync_Main_Rig_Proxy';
      const followerProxyName = 'No_Sync_Follower_Rig_Proxy';

      const mainRigHistoryRes = await request.get('http://127.0.0.1:9000/api/history', {
          params: { limit: 500, proxy_name: mainProxyName } 
      });
      const mainRigHistory = await mainRigHistoryRes.json();

      const mainRigFound = mainRigHistory.find(p => 
          p.proxy_name === mainProxyName && 
          p.direction === 'TX' && 
          p.data_str.includes(`F ${targetFreq}`)
      );
      expect(mainRigFound).toBeTruthy();

      const followerRigHistoryRes = await request.get('http://127.0.0.1:9000/api/history', {
          params: { limit: 500, proxy_name: followerProxyName } 
      });
      const followerRigHistory = await followerRigHistoryRes.json();

      const followerRigFound = followerRigHistory.find(p => 
          p.proxy_name === followerProxyName &&
          p.direction === 'TX' && 
          p.data_str.includes(`F ${targetFreq}`)
      );
      expect(followerRigFound).toBeFalsy(); 
    } finally {
      await deleteProfile(request, profileName);
      await request.delete(`http://127.0.0.1:9000/api/proxies/${mainRigProxyPort}`).catch(() => {});
      await request.delete(`http://127.0.0.1:9000/api/proxies/${followerRigProxyPort}`).catch(() => {});
    }
  });
});
