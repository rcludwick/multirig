import { create } from 'zustand';
import type { RigStatus, ServerStatus } from '@/types';

interface RigStore {
  // State from WebSocket
  rigs: RigStatus[];
  syncEnabled: boolean;
  syncSourceIndex: number;
  rigctlToMainEnabled: boolean;
  allRigsEnabled: boolean;
  activeProfile: string;
  rigctlHost: string;
  rigctlPort: number;

  // UI state for optimistic updates
  pendingFollowUpdates: Map<number, boolean>;
  uiErrors: Map<number, string>;

  // Actions - update from WebSocket
  setStatus: (status: ServerStatus) => void;
  updateRig: (index: number, partial: Partial<RigStatus>) => void;

  // Rig control actions (call API)
  toggleRigEnabled: (index: number) => Promise<void>;
  toggleRigFollow: (index: number) => Promise<void>;
  setRigFrequency: (index: number, hz: number) => Promise<void>;
  setRigMode: (index: number, mode: string) => Promise<void>;
  setRigVfo: (index: number, vfo: string) => Promise<void>;
  syncRigFromSource: (index: number) => Promise<void>;

  // Server control actions
  setSyncEnabled: (enabled: boolean) => Promise<void>;
  setSyncSourceIndex: (index: number) => Promise<void>;
  setRigctlToMainEnabled: (enabled: boolean) => Promise<void>;
  setAllRigsEnabled: (enabled: boolean) => Promise<void>;

  // Error handling
  setUiError: (index: number, message: string) => void;
  clearUiError: (index: number) => void;
}

async function postJson<T>(url: string, data: unknown): Promise<T> {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return res.json();
}

export const useRigStore = create<RigStore>((set, get) => ({
  // Initial state
  rigs: [],
  syncEnabled: true,
  syncSourceIndex: 0,
  rigctlToMainEnabled: true,
  allRigsEnabled: true,
  activeProfile: '',
  rigctlHost: '127.0.0.1',
  rigctlPort: 4534,
  pendingFollowUpdates: new Map(),
  uiErrors: new Map(),

  // Update from WebSocket status broadcast
  setStatus: (status) => {
    set({
      rigs: status.rigs.map((r, i) => ({ ...r, index: i })),
      syncEnabled: status.sync_enabled,
      syncSourceIndex: status.sync_source_index,
      rigctlToMainEnabled: status.rigctl_to_main_enabled,
      allRigsEnabled: status.all_rigs_enabled,
      activeProfile: status.active_profile,
      rigctlHost: status.rigctl_host,
      rigctlPort: status.rigctl_port,
    });
  },

  updateRig: (index, partial) => {
    set((state) => ({
      rigs: state.rigs.map((r, i) => (i === index ? { ...r, ...partial } : r)),
    }));
  },

  // Rig control
  toggleRigEnabled: async (index) => {
    const rig = get().rigs[index];
    if (!rig) return;
    const newEnabled = !rig.enabled;
    // Optimistic update
    get().updateRig(index, { enabled: newEnabled });
    try {
      await postJson(`/api/rig/${index}/enabled`, { enabled: newEnabled });
    } catch (e) {
      // Revert on error
      get().updateRig(index, { enabled: !newEnabled });
      get().setUiError(index, 'Failed to toggle power');
    }
  },

  toggleRigFollow: async (index) => {
    const rig = get().rigs[index];
    if (!rig) return;
    const newFollow = !rig.follow_main;
    set((state) => ({
      pendingFollowUpdates: new Map(state.pendingFollowUpdates).set(index, newFollow),
    }));
    try {
      await postJson(`/api/rig/${index}/follow_main`, { follow_main: newFollow });
    } catch (e) {
      get().setUiError(index, 'Failed to toggle follow');
    } finally {
      set((state) => {
        const updated = new Map(state.pendingFollowUpdates);
        updated.delete(index);
        return { pendingFollowUpdates: updated };
      });
    }
  },

  setRigFrequency: async (index, hz) => {
    try {
      const res = await postJson<{ status: string; error?: string }>(
        `/api/rig/${index}/set`,
        { frequency_hz: Math.round(hz) }
      );
      if (res.status === 'error' && res.error) {
        get().setUiError(index, res.error);
      }
    } catch (e) {
      get().setUiError(index, 'Failed to set frequency');
    }
  },

  setRigMode: async (index, mode) => {
    try {
      await postJson(`/api/rig/${index}/set`, { mode });
    } catch (e) {
      get().setUiError(index, 'Failed to set mode');
    }
  },

  setRigVfo: async (index, vfo) => {
    try {
      await postJson(`/api/rig/${index}/set`, { vfo });
    } catch (e) {
      get().setUiError(index, 'Failed to set VFO');
    }
  },

  syncRigFromSource: async (index) => {
    try {
      await postJson(`/api/rig/${index}/sync_from_source`, {});
    } catch (e) {
      get().setUiError(index, 'Failed to sync');
    }
  },

  // Server control
  setSyncEnabled: async (enabled) => {
    set({ syncEnabled: enabled });
    await postJson('/api/sync', { enabled });
  },

  setSyncSourceIndex: async (index) => {
    set({ syncSourceIndex: index });
    await postJson('/api/sync', { source_index: index });
  },

  setRigctlToMainEnabled: async (enabled) => {
    set({ rigctlToMainEnabled: enabled });
    await postJson('/api/rigctl_to_main', { enabled });
  },

  setAllRigsEnabled: async (enabled) => {
    set({ allRigsEnabled: enabled });
    await postJson('/api/rig/enabled_all', { enabled });
  },

  // Error handling
  setUiError: (index, message) => {
    set((state) => ({
      uiErrors: new Map(state.uiErrors).set(index, message),
    }));
    // Auto-clear after 5 seconds
    setTimeout(() => get().clearUiError(index), 5000);
  },

  clearUiError: (index) => {
    set((state) => {
      const updated = new Map(state.uiErrors);
      updated.delete(index);
      return { uiErrors: updated };
    });
  },
}));
