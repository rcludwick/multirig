/**
 * Playwright E2E helpers for MultiRig configuration profiles.
 *
 * Profiles are server-side snapshots of the MultiRig `AppConfig`.
 *
 * Note:
 *   Test profiles should be prefixed with `test_` so they are easy to identify.
 */

/**
 * Best-effort parse a Playwright API response.
 *
 * @param {import('@playwright/test').APIResponse} res
 * @returns {Promise<any>} Parsed JSON or an object shaped like `{ error: string }`.
 */
async function _jsonOrText(res) {
  try {
    return await res.json();
  } catch (e) {
    try {
      return { error: await res.text() };
    } catch (e2) {
      return { error: '' };
    }
  }
}

/**
 * List configuration profiles known to the MultiRig server.
 *
 * @param {import('@playwright/test').APIRequestContext} request
 * @returns {Promise<string[]>} Sorted list of profile names.
 * @throws {Error} If the server returns a non-2xx response.
 */
async function listProfiles(request) {
  const res = await request.get('/api/config/profiles');
  if (!res.ok()) {
    const body = await _jsonOrText(res);
    throw new Error(body?.error || `failed to list profiles (${res.status()})`);
  }
  const json = await res.json();
  const profiles = Array.isArray(json?.profiles) ? json.profiles : [];
  return profiles.map((p) => String(p));
}

/**
 * Ensure a configuration profile exists.
 *
 * This is used by Playwright E2E tests to make setup resilient; if the profile
 * is missing, the helper can create it.
 *
 * Creation strategy:
 * - Prefer applying config via `POST /api/config` (JSON) so tests can still
 *   set up even if YAML import has regressed.
 * - Fallback to `POST /api/config/import` when JSON parsing fails or applying
 *   via JSON fails.
 * - Persist as a profile via `POST /api/config/profiles/{name}`.
 *
 * @param {import('@playwright/test').APIRequestContext} request
 * @param {string} name
 * @param {{allowCreate?: boolean, configYaml?: string}=} opts
 * @returns {Promise<void>}
 * @throws {Error} If `allowCreate` is false and the profile does not exist.
 * @throws {Error} If applying config or saving the profile fails.
 */
async function ensureProfileExists(request, name, opts) {
  const allowCreate = opts?.allowCreate !== false;
  const configYaml = opts?.configYaml;

  const profiles = await listProfiles(request);
  if (profiles.includes(name)) return;

  if (!allowCreate) {
    throw new Error(`profile not found: ${name}`);
  }
  if (!configYaml) {
    throw new Error(`profile missing and no config provided: ${name}`);
  }

  let cfgObj = null;
  try {
    cfgObj = JSON.parse(configYaml);
  } catch (e) {
    cfgObj = null;
  }

  // Prefer /api/config (JSON) so tests can still set up even if YAML import breaks.
  let applied = false;
  if (cfgObj && typeof cfgObj === 'object') {
    const res = await request.post('/api/config', { data: cfgObj });
    if (res.ok()) {
      applied = true;
    }
  }

  // Fallback to YAML import if needed.
  if (!applied) {
    const importRes = await request.post('/api/config/import', {
      data: configYaml,
      headers: { 'Content-Type': 'text/yaml' },
    });
    if (!importRes.ok()) {
      const body = await _jsonOrText(importRes);
      throw new Error(body?.error || `failed to apply config (import) (${importRes.status()})`);
    }
  }

  const saveRes = await request.post(
    `/api/config/profiles/${encodeURIComponent(name)}`,
    {}
  );
  if (!saveRes.ok()) {
    const body = await _jsonOrText(saveRes);
    throw new Error(body?.error || `failed to save profile (${saveRes.status()})`);
  }

  const profiles2 = await listProfiles(request);
  if (!profiles2.includes(name)) {
    throw new Error(`profile save did not persist: ${name}`);
  }
}

/**
 * Load a configuration profile into the running MultiRig server.
 *
 * @param {import('@playwright/test').APIRequestContext} request
 * @param {string} name
 * @returns {Promise<void>}
 * @throws {Error} If the profile does not exist or fails validation.
 */
async function loadProfile(request, name) {
  const res = await request.post(
    `/api/config/profiles/${encodeURIComponent(name)}/load`,
    {}
  );
  if (!res.ok()) {
    const body = await _jsonOrText(res);
    throw new Error(body?.error || `failed to load profile (${res.status()})`);
  }
  const json = await res.json();
  if (json?.status !== 'ok') {
    throw new Error(json?.error || 'failed to load profile');
  }
}

/**
 * Delete a configuration profile.
 *
 * @param {import('@playwright/test').APIRequestContext} request
 * @param {string} name
 * @returns {Promise<boolean>} True if deleted, false if the profile did not exist.
 * @throws {Error} If the server returns an unexpected error.
 */
async function deleteProfile(request, name) {
  const res = await request.delete(
    `/api/config/profiles/${encodeURIComponent(name)}`
  );
  if (!res.ok()) {
    if (res.status() === 404) return false;
    const body = await _jsonOrText(res);
    throw new Error(body?.error || `failed to delete profile (${res.status()})`);
  }
  const json = await res.json();
  if (json?.status !== 'ok') {
    throw new Error(json?.error || 'failed to delete profile');
  }
  return true;
}

/**
 * Create a NetMind proxy with pre-cleanup.
 * 
 * @param {import('@playwright/test').APIRequestContext} request 
 * @param {object} proxyData Proxy configuration data
 * @returns {Promise<import('@playwright/test').APIResponse>}
 */
async function createProxy(request, proxyData) {
  const { local_port } = proxyData;
  // Cleanup before start
  await request.delete(`http://127.0.0.1:9000/api/proxies/${local_port}`).catch(() => {});
  
  const res = await request.post('http://127.0.0.1:9000/api/proxies', {
    data: proxyData
  });
  return res;
}

module.exports = {
  ensureProfileExists,
  loadProfile,
  deleteProfile,
  listProfiles,
  createProxy,
};
