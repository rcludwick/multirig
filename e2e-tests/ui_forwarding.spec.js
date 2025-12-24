const { test, expect } = require('@playwright/test');
const { ensureProfileExists, loadProfile, deleteProfile } = require('./profile_helpers');
const net = require('net');

test.describe('UI Forwarding Inhibition', () => {
    const profileName = 'test_forwarding';
    const configYaml = `
rigs:
  - name: Test Rig
    connection_type: hamlib
    model_id: 1
    device: /dev/null
    baud: 38400
poll_interval_ms: 200
sync_enabled: true
sync_source_index: 0
`;

    test.beforeEach(async ({ request, page }) => {
        await ensureProfileExists(request, profileName, { allowCreate: true, configYaml });
        await page.goto('/');
        await loadProfile(page.request, profileName);
        await page.reload();
    });

    test.afterEach(async ({ request }) => {
        await deleteProfile(request, profileName);
    });

    test('should NOT forward UI band clicks to TCP client', async ({ page }) => {
        // 1. Connect a TCP client to rigctld
        const client = new net.Socket();
        const receivedData = [];

        await new Promise((resolve, reject) => {
            client.connect(4532, '127.0.0.1', () => {
                console.log('Test client connected to rigctld');
                resolve();
            });
            client.on('error', reject);
        });

        // 2. Listen for data
        client.on('data', (data) => {
            console.log('Received unexpected data:', data.toString());
            receivedData.push(data.toString());
        });

        // 3. User clicks a band button (e.g., 40m)
        const rigCard = page.locator('#rig-0');
        await expect(rigCard).toBeVisible();
        await rigCard.locator('.band-btn', { hasText: '40m' }).click();

        // 4. Wait a short period to see if any data is emitted
        await page.waitForTimeout(1000);

        // 5. Assert NO data was received
        expect(receivedData.length).toBe(0);

        client.destroy();
    });
});
