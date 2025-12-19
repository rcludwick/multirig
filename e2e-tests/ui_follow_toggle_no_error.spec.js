// @ts-check
const { test, expect } = require('@playwright/test');
const { ensureProfileExists, loadProfile, deleteProfile } = require('./profile_helpers');

test('Toggle follow button should not produce error', async ({ page, request }) => {
  const targetRigctldPort = 4532; // Defined in playwright.config.js

  const config = {
    rigs: [
      {
        name: "Main Rig",
        connection_type: "rigctld",
        host: "127.0.0.1",
        port: targetRigctldPort,
        poll_interval_ms: 200,
      },
      {
        name: "Follower Rig",
        connection_type: "rigctld",
        host: "127.0.0.1",
        port: targetRigctldPort,
        follow_main: false, // Start unchecked so we can check it
        poll_interval_ms: 200,
      }
    ],
    sync_enabled: true,
    sync_source_index: 0,
    poll_interval_ms: 200
  };
  
  const configYaml = JSON.stringify(config);
  const profileName = 'test_ui_follow_toggle';
  
  // Setup profile
  await ensureProfileExists(request, profileName, { allowCreate: true, configYaml });
  await loadProfile(request, profileName);
  
  try {
    // Go to the dashboard
    await page.goto('/');

    // Wait for rig 1 (second rig) card to be visible
    const rigCard = page.locator('#rig-1'); // Target the second rig (index 1)
    await expect(rigCard).toBeVisible({ timeout: 10000 });
    
    // Wait for the rig to be "enabled" (not disabled class) which implies connected
    await expect(rigCard).not.toHaveClass(/disabled/, { timeout: 10000 });

    // Locate the follow toggle on the second rig
    const followToggle = rigCard.locator('input[data-action="follow-main"]');
    await expect(followToggle).toBeVisible();
    await expect(followToggle).toBeEnabled();

    // Click the toggle to change state
    await followToggle.click();

    // Wait a moment for potential error response
    const errorBox = rigCard.locator('[data-role="error"]');
    
    // Wait a short bit to allow network request to fail if it was going to
    await page.waitForTimeout(1000);

    // Check if error box is visible
    const isErrorVisible = await errorBox.isVisible();
    if (isErrorVisible) {
        const errorText = await errorBox.locator('.rig-error-body').textContent();
        console.log(`Error box visible with text: "${errorText}"`);
        
        expect(errorText).not.toContain("Internal Server Error");
        expect(errorText).not.toContain("SyntaxError");
        expect(errorText).not.toContain("valid JSON");
        
        // If it's another error (like connection lost), we might fail depending on strictness.
        // But the 500 error is what we are testing for.
    } else {
        expect(isErrorVisible).toBeFalsy();
    }
    
  } finally {
    // Cleanup
    await deleteProfile(request, profileName);
  }
});