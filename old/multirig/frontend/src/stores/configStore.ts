import { create } from 'zustand';
import type { AppConfig, RigConfig, RigModel } from '@/types';

interface ConfigStore {
  // Configuration state
  config: AppConfig | null;
  isDirty: boolean;
  isSaving: boolean;
  lastSaveError: string | null;

  // Rig models cache
  rigModels: RigModel[];
  rigModelById: Map<string, RigModel>;

  // Actions - config management
  setConfig: (config: AppConfig) => void;
  updateConfig: (partial: Partial<AppConfig>) => void;
  updateRigConfig: (index: number, partial: Partial<RigConfig>) => void;
  addRig: () => void;
  removeRig: (index: number) => void;

  // Persistence
  loadConfig: () => Promise<void>;
  saveConfig: () => Promise<void>;
  loadRigModels: () => Promise<void>;

  // Auto-save state management
  markDirty: () => void;
  markClean: () => void;
}

const DEFAULT_RIG_CONFIG: RigConfig = {
  name: 'New Rig',
  enabled: true,
  connection_type: 'rigctld',
  host: '127.0.0.1',
  port: 4532,
  managed: false,
  allow_out_of_band: false,
  band_presets: [],
  follow_main: true,
  poll_interval_ms: 1000,
  color: '#a4c356',
  inverted: false,
};

export const useConfigStore = create<ConfigStore>((set, get) => ({
  // Initial state
  config: null,
  isDirty: false,
  isSaving: false,
  lastSaveError: null,
  rigModels: [],
  rigModelById: new Map(),

  setConfig: (config) => {
    set({ config, isDirty: false });
  },

  updateConfig: (partial) => {
    const { config } = get();
    if (!config) return;
    set({
      config: { ...config, ...partial },
      isDirty: true,
    });
  },

  updateRigConfig: (index, partial) => {
    const { config } = get();
    if (!config || !config.rigs[index]) return;
    const updatedRigs = [...config.rigs];
    updatedRigs[index] = { ...updatedRigs[index], ...partial };
    set({
      config: { ...config, rigs: updatedRigs },
      isDirty: true,
    });
  },

  addRig: () => {
    const { config } = get();
    if (!config) return;
    const newRig: RigConfig = {
      ...DEFAULT_RIG_CONFIG,
      name: `Rig ${config.rigs.length + 1}`,
      port: 4532 + config.rigs.length,
    };
    set({
      config: { ...config, rigs: [...config.rigs, newRig] },
      isDirty: true,
    });
  },

  removeRig: (index) => {
    const { config } = get();
    if (!config || config.rigs.length <= 1) return;
    const updatedRigs = config.rigs.filter((_, i) => i !== index);
    // Adjust sync source if needed
    let syncSourceIndex = config.sync_source_index;
    if (syncSourceIndex >= updatedRigs.length) {
      syncSourceIndex = 0;
    }
    set({
      config: { ...config, rigs: updatedRigs, sync_source_index: syncSourceIndex },
      isDirty: true,
    });
  },

  loadConfig: async () => {
    try {
      const res = await fetch('/api/config');
      const config = await res.json();
      set({ config, isDirty: false, lastSaveError: null });
    } catch (e) {
      console.error('Failed to load config:', e);
    }
  },

  saveConfig: async () => {
    const { config } = get();
    if (!config) return;

    set({ isSaving: true, lastSaveError: null });
    try {
      const res = await fetch('/api/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config),
      });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.error || 'Failed to save config');
      }
      set({ isDirty: false });
    } catch (e) {
      const message = e instanceof Error ? e.message : 'Save failed';
      set({ lastSaveError: message });
      throw e;
    } finally {
      set({ isSaving: false });
    }
  },

  loadRigModels: async () => {
    try {
      const res = await fetch('/static/rig_models.json?ts=' + Date.now(), {
        cache: 'no-store',
      });
      const models: RigModel[] = await res.json();
      const modelById = new Map<string, RigModel>();
      for (const m of models) {
        if (m?.id != null) {
          modelById.set(String(m.id), m);
        }
      }
      set({ rigModels: models, rigModelById: modelById });
    } catch (e) {
      console.error('Failed to load rig models:', e);
      set({ rigModels: [], rigModelById: new Map() });
    }
  },

  markDirty: () => set({ isDirty: true }),
  markClean: () => set({ isDirty: false }),
}));
