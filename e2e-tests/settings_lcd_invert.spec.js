const { test, expect } = require('@playwright/test');
const { ensureProfileExists, loadProfile, deleteProfile } = require('./profile_helpers');

test.describe('Settings LCD Invert and Preview', () => {
    const profileName = 'test_settings_invert';
    const configYaml = `
rigs:
  - name: Rig 1
    connection_type: hamlib
    model_id: 1
    device: /dev/null
    baud: 38400
    color: "#a4c356"
poll_interval_ms: 1000
sync_enabled: true
sync_source_index: 0
`;

    test.beforeEach(async ({ request, page }) => {
        // Ensure fresh profile for each test
        await ensureProfileExists(request, profileName, { allowCreate: true, configYaml });
        // Clear local storage to prevent local overrides from interfering with backend config tests
        await page.goto('/');
        await page.evaluate(() => localStorage.clear());
    });

    test.afterEach(async ({ request }) => {
        await deleteProfile(request, profileName);
    });

    test('should toggle invert setting in config and update preview and dashboard', async ({ page }) => {
        await page.goto('/');
        await loadProfile(page.request, profileName);
        await page.reload();

        // 1. Navigate to Settings
        await page.getByRole('link', { name: 'Config' }).click();
        await expect(page).toHaveURL('/settings');

        const firstRig = page.locator('#rigList fieldset').first();
        const invertBox = firstRig.locator('input[data-key="inverted"]');
        const previewLcd = firstRig.locator('.lcd-preview-container .lcd');
        const colorInput = firstRig.locator('input[data-key="color"]');

        // 2. Verify Initial State (Off)
        await expect(invertBox).toBeVisible();
        await expect(previewLcd).toBeVisible();
        await expect(invertBox).not.toBeChecked();
        await expect(previewLcd).not.toHaveClass(/inverted/);

        // 3. Toggle Invert On
        await invertBox.check();
        await expect(previewLcd).toHaveClass(/inverted/);

        // 4. Change Color and Verify Preview
        await colorInput.fill('#ff0000');
        await colorInput.dispatchEvent('input');
        await expect(previewLcd).toHaveCSS('color', 'rgb(255, 0, 0)');

        // Reset Color
        const resetBtn = firstRig.locator('button[data-action="reset-color"]');
        await resetBtn.click();
        await expect(colorInput).toHaveValue('#a4c356');

        // 5. Save Config
        await page.getByRole('button', { name: 'Save' }).click();
        await expect(page.locator('#saveResult')).toHaveText('Saved');

        // 6. Navigate to Dashboard -> Check Inverted
        await page.getByRole('link', { name: 'Rigs' }).click();
        await expect(page).toHaveURL('/');

        const dashboardLcd = page.locator('#rig-0 .lcd');
        await expect(dashboardLcd).toHaveClass(/inverted/);
        await expect(dashboardLcd).toHaveCSS('color', 'rgb(164, 195, 86)');
    });

});
