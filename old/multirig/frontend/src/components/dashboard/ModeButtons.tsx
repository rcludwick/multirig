import { useRigStore } from '@/stores';
import { getModeDescription, COMMON_MODES } from '@/utils';
import type { RigStatus } from '@/types';
import './ModeButtons.css';

interface ModeButtonsProps {
  rig: RigStatus;
}

/**
 * Mode selection buttons.
 * Shows modes supported by the rig, or common defaults.
 */
export default function ModeButtons({ rig }: ModeButtonsProps) {
  const { setRigMode } = useRigStore();

  // Use rig-reported modes if available, otherwise common defaults
  const modes = rig.modes && rig.modes.length > 0 ? rig.modes : COMMON_MODES;

  const handleModeClick = (mode: string) => {
    if (!rig.enabled || !rig.connected) return;
    setRigMode(rig.index, mode);
  };

  // Check if mode setting is supported
  const canSetMode = rig.caps?.mode_set !== false;

  return (
    <div className="mode-buttons" data-testid={`mode-buttons-${rig.index}`}>
      {modes.map((mode) => {
        const isActive = rig.mode?.toUpperCase() === mode.toUpperCase();
        const description = getModeDescription(mode);

        return (
          <button
            key={mode}
            className={`mode-btn ${isActive ? 'active' : ''}`}
            onClick={() => handleModeClick(mode)}
            disabled={!rig.enabled || !rig.connected || !canSetMode}
            title={description}
          >
            {mode}
          </button>
        );
      })}
    </div>
  );
}
