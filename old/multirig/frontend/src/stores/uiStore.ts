import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface UiStore {
  // Section collapse state (persisted to localStorage)
  collapsedSections: Record<string, boolean>;

  // Frequency editor state
  activeFreqEditor: number | null;
  freqUnitPreference: Record<number, 'auto' | 'mhz' | 'khz' | 'hz'>;

  // VFO frequency cache (for display of inactive VFO)
  vfoFreqCache: Record<number, { A?: number; B?: number }>;

  // Debug section state
  serverDebugCollapsed: boolean;

  // Actions
  toggleSection: (rigIndex: number, section: string) => void;
  getSectionCollapsed: (rigIndex: number, section: string) => boolean;
  openFreqEditor: (rigIndex: number) => void;
  closeFreqEditor: () => void;
  setFreqUnit: (rigIndex: number, unit: 'auto' | 'mhz' | 'khz' | 'hz') => void;
  getFreqUnit: (rigIndex: number) => 'auto' | 'mhz' | 'khz' | 'hz';
  updateVfoCache: (rigIndex: number, vfo: 'A' | 'B', hz: number) => void;
  toggleServerDebug: () => void;
}

export const useUiStore = create<UiStore>()(
  persist(
    (set, get) => ({
      // Initial state
      collapsedSections: {},
      activeFreqEditor: null,
      freqUnitPreference: {},
      vfoFreqCache: {},
      serverDebugCollapsed: true,

      toggleSection: (rigIndex, section) => {
        const key = `rig-${rigIndex}-${section}`;
        set((state) => ({
          collapsedSections: {
            ...state.collapsedSections,
            [key]: !state.collapsedSections[key],
          },
        }));
      },

      getSectionCollapsed: (rigIndex, section) => {
        const key = `rig-${rigIndex}-${section}`;
        return get().collapsedSections[key] ?? false;
      },

      openFreqEditor: (rigIndex) => {
        set({ activeFreqEditor: rigIndex });
      },

      closeFreqEditor: () => {
        set({ activeFreqEditor: null });
      },

      setFreqUnit: (rigIndex, unit) => {
        set((state) => ({
          freqUnitPreference: {
            ...state.freqUnitPreference,
            [rigIndex]: unit,
          },
        }));
      },

      getFreqUnit: (rigIndex) => {
        return get().freqUnitPreference[rigIndex] ?? 'auto';
      },

      updateVfoCache: (rigIndex, vfo, hz) => {
        set((state) => ({
          vfoFreqCache: {
            ...state.vfoFreqCache,
            [rigIndex]: {
              ...state.vfoFreqCache[rigIndex],
              [vfo]: hz,
            },
          },
        }));
      },

      toggleServerDebug: () => {
        set((state) => ({
          serverDebugCollapsed: !state.serverDebugCollapsed,
        }));
      },
    }),
    {
      name: 'multirig-ui',
      partialize: (state) => ({
        collapsedSections: state.collapsedSections,
        freqUnitPreference: state.freqUnitPreference,
        serverDebugCollapsed: state.serverDebugCollapsed,
      }),
    }
  )
);
