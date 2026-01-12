import { useConfigStore } from '@/stores/configStore';
import type { RigModel } from '@/types';

/**
 * Hook to access rig models and lookup by ID.
 */
export function useRigModels() {
  const rigModels = useConfigStore((state) => state.rigModels);
  const rigModelById = useConfigStore((state) => state.rigModelById);

  const getModel = (modelId: number | null | undefined): RigModel | null => {
    if (modelId == null) return null;
    return rigModelById.get(String(modelId)) ?? null;
  };

  return {
    rigModels,
    getModel,
  };
}
