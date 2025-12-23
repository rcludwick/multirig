const { test, expect } = require('@playwright/test');

 const { ensureProfileExists, loadProfile, deleteProfile } = require('./profile_helpers');

 const profileName = 'test_ui_default';
 const configYaml = JSON.stringify({
   rigs: [
     {
       name: 'UI Test Rig',
       connection_type: 'rigctld',
       host: '127.0.0.1',
       port: 4532,
       poll_interval_ms: 200,
     },
   ],
   poll_interval_ms: 200,
 });

 test.beforeAll(async ({ request }) => {
   await ensureProfileExists(request, profileName, { allowCreate: true, configYaml });
   await loadProfile(request, profileName);
 });

 test.afterAll(async ({ request }) => {
   await deleteProfile(request, profileName);
 });

test.describe('Dashboard UI', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    // Use request context to load profile to avoid page reload race conditions
    await loadProfile(page.request, profileName);
    await page.reload();
  });

  test('Sync all once button should be removed', async ({ page }) => {
    const btn = page.locator('#syncAllOnce');
    await expect(btn).not.toBeVisible();
  });

  test('Server Debug should be a turnstile', async ({ page }) => {
    const section = page.locator('#serverDebugSection');
    const toggle = page.locator('#toggleServerDebug');
    
    // Should be visible
    await expect(section).toBeVisible();
    
    // Should be collapsed by default (checking class)
    await expect(section).toHaveClass(/collapsed/);
    
    // Toggle button should contain correct text including port placeholder or actual port
    await expect(toggle).toContainText('TCP Traffic');
    // The port is updated dynamically, so it might be a number or 'TCP'
    await expect(toggle).toHaveText(/TCP Traffic \((TCP|\d+)\)/);
    
    // Turnstile icon should be ▼
    const icon = toggle.locator('.turnstile');
    await expect(icon).toHaveText('▼');

    // Expand
    await toggle.click();
    // Wait for the collapse animation/state change
    await expect(section).not.toHaveClass(/collapsed/);
    
    // Log should be visible
    const log = page.locator('#serverDebugLog');
    await expect(log).toBeVisible();
  });

  test('Main rig should not show Sync button', async ({ page }) => {
    // Wait for rig grid to populate
    await expect(page.locator('.rig-card').first()).toBeVisible();

    // Assuming Rig 0 is the main rig by default
    const rig0 = page.locator('#rig-0');
    await expect(rig0).toBeVisible();
    
    const syncBtn = rig0.locator('button[data-action="sync"]');
    // The styling sets display: none, so it should be hidden
    await expect(syncBtn).toBeHidden();
  });

  test('Turnstile arrow direction consistency', async ({ page }) => {
    // Check rig sections (e.g., VFO, Bands)
    await expect(page.locator('.rig-card').first()).toBeVisible();
    
    const rig0 = page.locator('#rig-0');
    await expect(rig0).toBeVisible();

    const vfoSection = rig0.locator('.rig-section[data-section="vfo"]');
    const vfoHeader = vfoSection.locator('.rig-section-header');
    const vfoIcon = vfoHeader.locator('.turnstile');

    // Should be ▼
    await expect(vfoIcon).toHaveText('▼');
  });
});

test.describe('Settings UI', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/settings');
  });

  test('Band presets turnstile should use correct icon', async ({ page }) => {
    // Wait for rig list to populate (async fetch)
    const rigList = page.locator('#rigList');
    await expect(rigList).toBeVisible();
    await expect(rigList.locator('fieldset').first()).toBeVisible();

    const rig0 = rigList.locator('fieldset').first();
    const bandSection = rig0.locator('.rig-section[data-role="band-presets-section"]');
    const header = bandSection.locator('.rig-section-header');
    const icon = header.locator('.turnstile');

    await expect(icon).toHaveText('▼');
  });
});
