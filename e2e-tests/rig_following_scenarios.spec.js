const { test, expect } = require('@playwright/test');
const net = require('net');

const { ensureProfileExists, loadProfile, deleteProfile, createProxy } = require('./profile_helpers');

test.describe.configure({ mode: 'serial' });

test.describe('Rig Following Scenarios', () => {
  
  test('follower with follow_main=true and band enabled should sync successfully', async ({ request, page }) => {
    const mainRigProxyPort = 9010;
    const followerRigProxyPort = 9011;
    const targetRigctldPort = 4532;

    const mainProxyRes = await createProxy(request, {
      local_port: mainRigProxyPort,
      target_host: '127.0.0.1',
      target_port: targetRigctldPort,
      name: 'Main_Rig_Follow_Test_1',
      protocol: 'hamlib'
    });
    expect(mainProxyRes.ok()).toBeTruthy();

    const followerProxyRes = await createProxy(request, {
      local_port: followerRigProxyPort,
      target_host: '127.0.0.1',
      target_port: targetRigctldPort,
      name: 'Follower_Rig_Follow_Test_1',
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
      sync_enabled: true,
      sync_source_index: 0,
      poll_interval_ms: 200
    };
    
    const configYaml = JSON.stringify(config);
    const profileName = 'test_rig_following_scenario_1';
    await ensureProfileExists(request, profileName, { allowCreate: true, configYaml });
    try {
      await loadProfile(request, profileName);
      // Reload page if provided to ensure UI reflects new profile
      if (page) await page.reload();
      await new Promise(r => setTimeout(r, 1500));

    const client = new net.Socket();
    const targetFreq = '14074000';
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

    let mainRigFound = undefined;
    for (let i = 0; i < 5; i++) {
      const historyRes = await request.get('http://127.0.0.1:9000/api/history', {
        params: { limit: 500, proxy_name: 'Main_Rig_Follow_Test_1' } 
      });
      const history = await historyRes.json();
      mainRigFound = history.find(p => 
        p.proxy_name === 'Main_Rig_Follow_Test_1' && 
        p.direction === 'TX' && 
        p.data_str.includes(`F ${targetFreq}`)
      );
      if (mainRigFound) break;
      await new Promise(r => setTimeout(r, 500));
    }
    expect(mainRigFound).toBeTruthy();

    let followerRigFound = undefined;
    for (let i = 0; i < 5; i++) {
      const historyRes = await request.get('http://127.0.0.1:9000/api/history', {
        params: { limit: 500, proxy_name: 'Follower_Rig_Follow_Test_1' } 
      });
      const history = await historyRes.json();
      followerRigFound = history.find(p => 
        p.proxy_name === 'Follower_Rig_Follow_Test_1' && 
        p.direction === 'TX' && 
        p.data_str.includes(`F ${targetFreq}`)
      );
      if (followerRigFound) break;
      await new Promise(r => setTimeout(r, 500));
    }
    expect(followerRigFound).toBeTruthy();
    } finally {
      await deleteProfile(request, profileName);
      await request.delete('http://127.0.0.1:9000/api/proxies/9010').catch(() => {});
      await request.delete('http://127.0.0.1:9000/api/proxies/9011').catch(() => {});
    }
    await expect(
      ensureProfileExists(request, profileName, { allowCreate: false })
    ).rejects.toThrow(/profile not found/);
  });

  test('follower with follow_main=false should NOT sync', async ({ request, page }) => {
    const mainRigProxyPort = 9012;
    const followerRigProxyPort = 9013;
    const targetRigctldPort = 4532;

    const mainProxyRes = await createProxy(request, {
      local_port: mainRigProxyPort,
      target_host: '127.0.0.1',
      target_port: targetRigctldPort,
      name: 'Main_Rig_Follow_Test_2',
      protocol: 'hamlib'
    });
    expect(mainProxyRes.ok()).toBeTruthy();

    const followerProxyRes = await createProxy(request, {
      local_port: followerRigProxyPort,
      target_host: '127.0.0.1',
      target_port: targetRigctldPort,
      name: 'Follower_Rig_Follow_Test_2',
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
          follow_main: false,
          band_presets: [ { label: "20m", frequency_hz: 14074000, enabled: true } ]
        }
      ],
      sync_enabled: true,
      sync_source_index: 0,
      poll_interval_ms: 200
    };
    
    const configYaml = JSON.stringify(config);
    const profileName = 'test_rig_following_scenario_2';
    await ensureProfileExists(request, profileName, { allowCreate: true, configYaml });
    try {
      await loadProfile(request, profileName);
      if (page) await page.reload();
      await new Promise(r => setTimeout(r, 1500));

    const client = new net.Socket();
    const targetFreq = '14074000';
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

    let mainRigFound = undefined;
    for (let i = 0; i < 5; i++) {
      const historyRes = await request.get('http://127.0.0.1:9000/api/history', {
        params: { limit: 500, proxy_name: 'Main_Rig_Follow_Test_2' } 
      });
      const history = await historyRes.json();
      mainRigFound = history.find(p => 
        p.proxy_name === 'Main_Rig_Follow_Test_2' && 
        p.direction === 'TX' && 
        p.data_str.includes(`F ${targetFreq}`)
      );
      if (mainRigFound) break;
      await new Promise(r => setTimeout(r, 500));
    }
    expect(mainRigFound).toBeTruthy();

    let followerRigFound = undefined;
    for (let i = 0; i < 5; i++) {
      const historyRes = await request.get('http://127.0.0.1:9000/api/history', {
        params: { limit: 500, proxy_name: 'Follower_Rig_Follow_Test_2' } 
      });
      const history = await historyRes.json();
      followerRigFound = history.find(p => 
        p.proxy_name === 'Follower_Rig_Follow_Test_2' && 
        p.direction === 'TX' && 
        p.data_str.includes(`F ${targetFreq}`)
      );
      if (followerRigFound) break;
      await new Promise(r => setTimeout(r, 500));
    }
    expect(followerRigFound).toBeFalsy();
    } finally {
      await deleteProfile(request, profileName);
      await request.delete('http://127.0.0.1:9000/api/proxies/9012').catch(() => {});
      await request.delete('http://127.0.0.1:9000/api/proxies/9013').catch(() => {});
    }
    await expect(
      ensureProfileExists(request, profileName, { allowCreate: false })
    ).rejects.toThrow(/profile not found/);
  });

  test('follower with band disabled should NOT sync and report error', async ({ request, page }) => {
    const mainRigProxyPort = 9014;
    const followerRigProxyPort = 9015;
    const targetRigctldPort = 4532;

    const mainProxyRes = await createProxy(request, {
      local_port: mainRigProxyPort,
      target_host: '127.0.0.1',
      target_port: targetRigctldPort,
      name: 'Main_Rig_Follow_Test_3',
      protocol: 'hamlib'
    });
    expect(mainProxyRes.ok()).toBeTruthy();

    const followerProxyRes = await createProxy(request, {
      local_port: followerRigProxyPort,
      target_host: '127.0.0.1',
      target_port: targetRigctldPort,
      name: 'Follower_Rig_Follow_Test_3',
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
    const profileName = 'test_rig_following_scenario_3';
    await ensureProfileExists(request, profileName, { allowCreate: true, configYaml });
    try {
      await loadProfile(request, profileName);
      if (page) await page.reload();
      await new Promise(r => setTimeout(r, 1500));

    const client = new net.Socket();
    const targetFreq = '7074000'; // 40m - follower only has 20m
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

    let mainRigFound = undefined;
    for (let i = 0; i < 5; i++) {
      const historyRes = await request.get('http://127.0.0.1:9000/api/history', {
        params: { limit: 500, proxy_name: 'Main_Rig_Follow_Test_3' } 
      });
      const history = await historyRes.json();
      mainRigFound = history.find(p => 
        p.proxy_name === 'Main_Rig_Follow_Test_3' && 
        p.direction === 'TX' && 
        p.data_str.includes(`F ${targetFreq}`)
      );
      if (mainRigFound) break;
      await new Promise(r => setTimeout(r, 500));
    }
    expect(mainRigFound).toBeTruthy();

    let followerRigFound = undefined;
    for (let i = 0; i < 5; i++) {
      const historyRes = await request.get('http://127.0.0.1:9000/api/history', {
        params: { limit: 500, proxy_name: 'Follower_Rig_Follow_Test_3' } 
      });
      const history = await historyRes.json();
      followerRigFound = history.find(p => 
        p.proxy_name === 'Follower_Rig_Follow_Test_3' && 
        p.direction === 'TX' && 
        p.data_str.includes(`F ${targetFreq}`)
      );
      if (followerRigFound) break;
      await new Promise(r => setTimeout(r, 500));
    }
    expect(followerRigFound).toBeFalsy();

    let statusFound = false;
    for (let i = 0; i < 5; i++) {
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
      await request.delete('http://127.0.0.1:9000/api/proxies/9014').catch(() => {});
      await request.delete('http://127.0.0.1:9000/api/proxies/9015').catch(() => {});
    }
    await expect(
      ensureProfileExists(request, profileName, { allowCreate: false })
    ).rejects.toThrow(/profile not found/);
  });

  test('follower with allow_out_of_band=true should sync even if band disabled', async ({ request, page }) => {
    const mainRigProxyPort = 9016;
    const followerRigProxyPort = 9017;
    const targetRigctldPort = 4532;

    const mainProxyRes = await createProxy(request, {
      local_port: mainRigProxyPort,
      target_host: '127.0.0.1',
      target_port: targetRigctldPort,
      name: 'Main_Rig_Follow_Test_4',
      protocol: 'hamlib'
    });
    expect(mainProxyRes.ok()).toBeTruthy();

    const followerProxyRes = await createProxy(request, {
      local_port: followerRigProxyPort,
      target_host: '127.0.0.1',
      target_port: targetRigctldPort,
      name: 'Follower_Rig_Follow_Test_4',
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
          allow_out_of_band: true,
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
    const profileName = 'test_rig_following_scenario_4';
    await ensureProfileExists(request, profileName, { allowCreate: true, configYaml });
    try {
      await loadProfile(request, profileName);
      if (page) await page.reload();
      await new Promise(r => setTimeout(r, 1500));

    const client = new net.Socket();
    const targetFreq = '14074000';
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

    let mainRigFound = undefined;
    for (let i = 0; i < 5; i++) {
      const historyRes = await request.get('http://127.0.0.1:9000/api/history', {
        params: { limit: 500, proxy_name: 'Main_Rig_Follow_Test_4' } 
      });
      const history = await historyRes.json();
      mainRigFound = history.find(p => 
        p.proxy_name === 'Main_Rig_Follow_Test_4' && 
        p.direction === 'TX' && 
        p.data_str.includes(`F ${targetFreq}`)
      );
      if (mainRigFound) break;
      await new Promise(r => setTimeout(r, 500));
    }
    expect(mainRigFound).toBeTruthy();

    let followerRigFound = undefined;
    for (let i = 0; i < 5; i++) {
      const historyRes = await request.get('http://127.0.0.1:9000/api/history', {
        params: { limit: 500, proxy_name: 'Follower_Rig_Follow_Test_4' } 
      });
      const history = await historyRes.json();
      followerRigFound = history.find(p => 
        p.proxy_name === 'Follower_Rig_Follow_Test_4' && 
        p.direction === 'TX' && 
        p.data_str.includes(`F ${targetFreq}`)
      );
      if (followerRigFound) break;
      await new Promise(r => setTimeout(r, 500));
    }
    expect(followerRigFound).toBeTruthy();
    } finally {
      await deleteProfile(request, profileName);
      await request.delete('http://127.0.0.1:9000/api/proxies/9016').catch(() => {});
      await request.delete('http://127.0.0.1:9000/api/proxies/9017').catch(() => {});
    }
    await expect(
      ensureProfileExists(request, profileName, { allowCreate: false })
    ).rejects.toThrow(/profile not found/);
  });

  test('multiple followers with mixed configurations', async ({ request, page }) => {
    const mainRigProxyPort = 9050;
    const follower1ProxyPort = 9051;
    const follower2ProxyPort = 9052;
    const targetRigctldPort = 4532;

    const mainProxyRes = await createProxy(request, {
      local_port: mainRigProxyPort,
      target_host: '127.0.0.1',
      target_port: targetRigctldPort,
      name: 'Main_Rig_Follow_Test_6',
      protocol: 'hamlib'
    });
    expect(mainProxyRes.ok()).toBeTruthy();

    const follower1ProxyRes = await createProxy(request, {
      local_port: follower1ProxyPort,
      target_host: '127.0.0.1',
      target_port: targetRigctldPort,
      name: 'Follower1_Rig_Follow_Test_6',
      protocol: 'hamlib'
    });
    expect(follower1ProxyRes.ok()).toBeTruthy();

    const follower2ProxyRes = await createProxy(request, {
      local_port: follower2ProxyPort,
      target_host: '127.0.0.1',
      target_port: targetRigctldPort,
      name: 'Follower2_Rig_Follow_Test_6',
      protocol: 'hamlib'
    });
    expect(follower2ProxyRes.ok()).toBeTruthy();

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
          name: "Follower1 Rig",
          connection_type: "rigctld",
          host: "127.0.0.1",
          port: follower1ProxyPort,
          poll_interval_ms: 200,
          follow_main: true,
          band_presets: [ { label: "20m", frequency_hz: 14074000, enabled: true } ]
        },
        {
          name: "Follower2 Rig",
          connection_type: "rigctld",
          host: "127.0.0.1",
          port: follower2ProxyPort,
          poll_interval_ms: 200,
          follow_main: false,
          band_presets: [ { label: "20m", frequency_hz: 14074000, enabled: true } ]
        }
      ],
      sync_enabled: true,
      sync_source_index: 0,
      poll_interval_ms: 200
    };
    
    const configYaml = JSON.stringify(config);
    const profileName = 'test_rig_following_scenario_6';
    await ensureProfileExists(request, profileName, { allowCreate: true, configYaml });
    try {
      await loadProfile(request, profileName);
      if (page) await page.reload();

      // Wait for config to be applied and rigs to connect
      await new Promise(r => setTimeout(r, 3000));

    const client = new net.Socket();
    const targetFreq = '14200000'; // Use different freq to ensure sync service detects change
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
    // Wait for sync service to propagate (poll_interval_ms is 2000ms)
    await new Promise(r => setTimeout(r, 5000));

    let mainRigFound = undefined;
    for (let i = 0; i < 10; i++) {
      const historyRes = await request.get('http://127.0.0.1:9000/api/history', {
        params: { limit: 500, proxy_name: 'Main_Rig_Follow_Test_6' } 
      });
      const history = await historyRes.json();
      mainRigFound = history.find(p => 
        p.proxy_name === 'Main_Rig_Follow_Test_6' && 
        p.direction === 'TX' && 
        p.data_str.includes(`F ${targetFreq}`)
      );
      if (mainRigFound) break;
      await new Promise(r => setTimeout(r, 500));
    }
    expect(mainRigFound).toBeTruthy();

    let follower1Found = undefined;
    for (let i = 0; i < 10; i++) {
      const historyRes = await request.get('http://127.0.0.1:9000/api/history', {
        params: { limit: 500, proxy_name: 'Follower1_Rig_Follow_Test_6' } 
      });
      const history = await historyRes.json();
      follower1Found = history.find(p => 
        p.proxy_name === 'Follower1_Rig_Follow_Test_6' && 
        p.direction === 'TX' && 
        p.data_str.includes(`F ${targetFreq}`)
      );
      if (follower1Found) break;
      await new Promise(r => setTimeout(r, 500));
    }
    expect(follower1Found).toBeTruthy();

    let follower2Found = undefined;
    for (let i = 0; i < 10; i++) {
      const historyRes = await request.get('http://127.0.0.1:9000/api/history', {
        params: { limit: 500, proxy_name: 'Follower2_Rig_Follow_Test_6' } 
      });
      const history = await historyRes.json();
      follower2Found = history.find(p => 
        p.proxy_name === 'Follower2_Rig_Follow_Test_6' && 
        p.direction === 'TX' && 
        p.data_str.includes(`F ${targetFreq}`)
      );
      if (follower2Found) break;
      await new Promise(r => setTimeout(r, 500));
    }
    expect(follower2Found).toBeFalsy();
    } finally {
      await deleteProfile(request, profileName);
      await request.delete('http://127.0.0.1:9000/api/proxies/9050').catch(() => {});
      await request.delete('http://127.0.0.1:9000/api/proxies/9051').catch(() => {});
      await request.delete('http://127.0.0.1:9000/api/proxies/9052').catch(() => {});
    }
    await expect(
      ensureProfileExists(request, profileName, { allowCreate: false })
    ).rejects.toThrow(/profile not found/);
  });

});
