import { useEffect, useRef } from 'react';
import { useConfigStore } from '@/stores/configStore';
import { useProfileStore } from '@/stores/profileStore';

const AUTOSAVE_DELAY_MS = 700;

/**
 * Auto-save hook for configuration changes.
 * Debounces saves and syncs to active profile.
 */
export function useAutoSave() {
  const { config, isDirty, saveConfig, markClean, isSaving, lastSaveError } = useConfigStore();
  const { activeProfile, saveCurrentProfile } = useProfileStore();

  const timerRef = useRef<number | null>(null);
  const inFlightRef = useRef(false);
  const pendingRef = useRef(false);

  useEffect(() => {
    // Don't save if not dirty or already saving
    if (!isDirty || isSaving) return;

    // Clear existing timer
    if (timerRef.current) {
      clearTimeout(timerRef.current);
    }

    timerRef.current = window.setTimeout(async () => {
      // If a save is in flight, mark as pending
      if (inFlightRef.current) {
        pendingRef.current = true;
        return;
      }

      inFlightRef.current = true;

      try {
        // 1. Apply config to running server
        await saveConfig();

        // 2. Save to active profile on disk
        if (activeProfile) {
          await saveCurrentProfile();
        }

        markClean();
      } catch (error) {
        console.error('[AutoSave] Failed:', error);
        // Don't mark clean on error - will retry
      } finally {
        inFlightRef.current = false;

        // If there was a pending save, trigger another cycle
        if (pendingRef.current) {
          pendingRef.current = false;
          useConfigStore.getState().markDirty();
        }
      }
    }, AUTOSAVE_DELAY_MS);

    return () => {
      if (timerRef.current) {
        clearTimeout(timerRef.current);
      }
    };
  }, [isDirty, config, activeProfile, saveConfig, saveCurrentProfile, markClean, isSaving]);

  return {
    isDirty,
    isSaving,
    lastSaveError,
  };
}
