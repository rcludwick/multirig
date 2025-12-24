const { test, expect } = require('@playwright/test');

const { ensureProfileExists, deleteProfile } = require('./profile_helpers');

test.describe('Settings - autosave to active profile', () => {
  test('editing config autosaves to the loaded profile and applies to running config', async ({ page, request }) => {
    const profileName = 'test_autosave_profile_on_change';

    const initialConfig = {
      rigs: [
        {
          name: 'Autosave Rig',
          connection_type: 'rigctld',
          host: '127.0.0.1',
          port: 4532,
          poll_interval_ms: 5000,
          band_presets: [
            { label: '20m', frequency_hz: 14074000, enabled: true },
          ],
        },
      ],
      poll_interval_ms: 5000,
    };

    const configYaml = JSON.stringify(initialConfig);
    await ensureProfileExists(request, profileName, { allowCreate: true, configYaml });

    try {
      await page.goto('/settings');

      await page.locator('#profileSelectBtn').click();
      await page.locator('#profileSelectChoice').selectOption(profileName);
      await page.locator('#profileSelectConfirm').click();

      await expect(page.locator('#profileResult')).toContainText('Loaded profile');

      const rigFieldset = page.locator('#rigList fieldset').first();
      await expect(rigFieldset).toBeVisible();

      const rigPortInput = rigFieldset.locator('input[data-key="port"]');
      await expect(rigPortInput).toBeVisible();

      const newPort = 9990;
      await rigPortInput.fill(String(newPort));
      // Trigger change event explicitly to ensure autosave starts
      await rigPortInput.dispatchEvent('change');

      // Wait for debounced autosave to trigger (700ms) and complete the network requests.
      await page.waitForTimeout(1500);

      // Verify running config applied.
      let applied = false;
      for (let i = 0; i < 10; i++) {
        const res = await request.get('/api/config');
        const cfg = await res.json();
        if (cfg?.rigs?.[0]?.port === newPort) {
          applied = true;
          break;
        }
        await page.waitForTimeout(250);
      }
      expect(applied).toBeTruthy();

      // Verify profile persisted (export reflects new port).
      let saved = false;
      for (let i = 0; i < 10; i++) {
        const res = await request.get(`/api/config/profiles/${encodeURIComponent(profileName)}/export`);
        const text = await res.text();
        if (text.includes(`port: ${newPort}`)) {
          saved = true;
          break;
        }
        await page.waitForTimeout(250);
      }
      expect(saved).toBeTruthy();
    } finally {
      await deleteProfile(request, profileName);
    }

    await expect(
      ensureProfileExists(request, profileName, { allowCreate: false })
    ).rejects.toThrow(/profile not found/);
  });
});
