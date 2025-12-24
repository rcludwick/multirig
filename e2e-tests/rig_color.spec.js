const { test, expect } = require('@playwright/test');
const { ensureProfileExists, loadProfile, deleteProfile } = require('./profile_helpers');

test.describe('Rig Color Customization', () => {
  const profileName = 'test_rig_color';
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

  test.beforeAll(async ({ request }) => {
    await ensureProfileExists(request, profileName, { allowCreate: true, configYaml });
  });

  test.afterAll(async ({ request }) => {
    await deleteProfile(request, profileName);
  });

  test('should allow setting and resetting rig color', async ({ page }) => {
    await page.goto('/');
    // Use request context to load profile to avoid page reload race conditions
    await loadProfile(page.request, profileName);
    await page.reload();

    // Navigate to settings
    await page.getByRole('link', { name: 'Config' }).click();
    await expect(page).toHaveURL('/settings');

    // Change the color of the first rig
    const firstRig = page.locator('#rigList fieldset').first();
    const colorInput = firstRig.locator('input[data-key="color"]');
    await expect(colorInput).toBeVisible();
    await colorInput.fill('#ff0000');

    // Verify the color is set in the input
    await expect(colorInput).toHaveValue('#ff0000');

    // Save the configuration explicitly to avoid race condition with autosave
    await page.getByRole('button', { name: 'Save' }).click();
    await expect(page.locator('#saveResult')).toHaveText('Saved');

    // Navigate back to the dashboard and check the color
    await page.getByRole('link', { name: 'Rigs' }).click();
    await expect(page).toHaveURL('/');
    
    const rigCard = page.locator('#rig-0');
    const lcd = rigCard.locator('.lcd');
    await expect(lcd).toBeVisible();

    // The background is a gradient. Browsers may normalize colors (e.g. to rgba), so we use a flexible regex.
    // We check for linear-gradient and the presence of the red color (hex or rgb).
    // #ff0000 is 255, 0, 0
    await expect(lcd).toHaveAttribute('style', /linear-gradient.*(?:#ff0000|255,\s*0,\s*0)/i);

    // Go back to settings and reset the color
    await page.getByRole('link', { name: 'Config' }).click();
    await expect(page).toHaveURL('/settings');
    
    const colorResetBtn = firstRig.locator('button[data-action="reset-color"]');
    await colorResetBtn.click();

    // Verify the color is reset in the input
    await expect(colorInput).toHaveValue('#a4c356');

    // Save again after reset
    await page.getByRole('button', { name: 'Save' }).click();
    await expect(page.locator('#saveResult')).toHaveText('Saved');

    // Navigate back to the dashboard and check the color again
    await page.getByRole('link', { name: 'Rigs' }).click();
    await expect(page).toHaveURL('/');
    
    // #a4c356 is 164, 195, 86
    await expect(lcd).toHaveAttribute('style', /linear-gradient.*(?:#a4c356|164,\s*195,\s*86)/i);
  });
});
