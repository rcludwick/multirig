import { create } from 'zustand';
import { useConfigStore } from './configStore';

interface ProfileStore {
  profiles: string[];
  activeProfile: string;
  isLoading: boolean;
  error: string | null;

  // Actions
  loadProfiles: () => Promise<void>;
  selectProfile: (name: string) => Promise<void>;
  createProfile: (name: string) => Promise<void>;
  saveCurrentProfile: () => Promise<void>;
  renameProfile: (oldName: string, newName: string) => Promise<void>;
  duplicateProfile: (from: string, newName: string) => Promise<void>;
  deleteProfile: (name: string) => Promise<void>;
  setActiveProfile: (name: string) => void;
}

export const useProfileStore = create<ProfileStore>((set, get) => ({
  profiles: [],
  activeProfile: '',
  isLoading: false,
  error: null,

  loadProfiles: async () => {
    set({ isLoading: true, error: null });
    try {
      const res = await fetch('/api/config/profiles');
      const data = await res.json();
      set({ profiles: data.profiles || [] });

      // Also get active profile
      const activeRes = await fetch('/api/config/active_profile');
      const activeData = await activeRes.json();
      set({ activeProfile: activeData.name || '' });
    } catch (e) {
      set({ error: 'Failed to load profiles' });
    } finally {
      set({ isLoading: false });
    }
  },

  selectProfile: async (name) => {
    set({ isLoading: true, error: null });
    try {
      const res = await fetch(`/api/config/profiles/${encodeURIComponent(name)}/load`, {
        method: 'POST',
      });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.error || 'Failed to load profile');
      }
      set({ activeProfile: name });
      // Reload config after profile switch
      await useConfigStore.getState().loadConfig();
    } catch (e) {
      set({ error: e instanceof Error ? e.message : 'Failed to load profile' });
    } finally {
      set({ isLoading: false });
    }
  },

  createProfile: async (name) => {
    set({ isLoading: true, error: null });
    try {
      const res = await fetch(`/api/config/profiles/${encodeURIComponent(name)}/create`, {
        method: 'POST',
      });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.error || 'Failed to create profile');
      }
      set({ activeProfile: name });
      await get().loadProfiles();
    } catch (e) {
      set({ error: e instanceof Error ? e.message : 'Failed to create profile' });
      throw e;
    } finally {
      set({ isLoading: false });
    }
  },

  saveCurrentProfile: async () => {
    const { activeProfile } = get();
    if (!activeProfile) return;

    set({ isLoading: true, error: null });
    try {
      const res = await fetch(`/api/config/profiles/${encodeURIComponent(activeProfile)}`, {
        method: 'POST',
      });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.error || 'Failed to save profile');
      }
    } catch (e) {
      set({ error: e instanceof Error ? e.message : 'Failed to save profile' });
      throw e;
    } finally {
      set({ isLoading: false });
    }
  },

  renameProfile: async (oldName, newName) => {
    set({ isLoading: true, error: null });
    try {
      const res = await fetch(`/api/config/profiles/${encodeURIComponent(oldName)}/rename`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ new_name: newName }),
      });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.error || 'Failed to rename profile');
      }
      if (get().activeProfile === oldName) {
        set({ activeProfile: newName });
      }
      await get().loadProfiles();
    } catch (e) {
      set({ error: e instanceof Error ? e.message : 'Failed to rename profile' });
      throw e;
    } finally {
      set({ isLoading: false });
    }
  },

  duplicateProfile: async (from, newName) => {
    set({ isLoading: true, error: null });
    try {
      const res = await fetch(`/api/config/profiles/${encodeURIComponent(from)}/duplicate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ new_name: newName }),
      });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.error || 'Failed to duplicate profile');
      }
      await get().loadProfiles();
    } catch (e) {
      set({ error: e instanceof Error ? e.message : 'Failed to duplicate profile' });
      throw e;
    } finally {
      set({ isLoading: false });
    }
  },

  deleteProfile: async (name) => {
    set({ isLoading: true, error: null });
    try {
      const res = await fetch(`/api/config/profiles/${encodeURIComponent(name)}`, {
        method: 'DELETE',
      });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.error || 'Failed to delete profile');
      }
      await get().loadProfiles();
    } catch (e) {
      set({ error: e instanceof Error ? e.message : 'Failed to delete profile' });
      throw e;
    } finally {
      set({ isLoading: false });
    }
  },

  setActiveProfile: (name) => {
    set({ activeProfile: name });
  },
}));
