import { useRigStore } from '@/stores';
import { BANDS, bandForHz, QUICK_BAND_LABELS } from '@/utils';
import type { RigStatus } from '@/types';
import './BandButtons.css';

interface BandButtonsProps {
  rig: RigStatus;
}

/**
 * Band preset buttons for quick frequency switching.
 * Shows configured band presets, or quick defaults if none configured.
 */
export default function BandButtons({ rig }: BandButtonsProps) {
  const { setRigFrequency } = useRigStore();

  // Use band presets if configured, otherwise show quick defaults
  const presets = rig.band_presets?.filter((p) => p.enabled) ?? [];
  const hasPresets = presets.length > 0;

  const handleBandClick = (hz: number) => {
    if (!rig.enabled || !rig.connected) return;
    setRigFrequency(rig.index, hz);
  };

  // Get current band for highlighting
  const currentBand = bandForHz(rig.frequency_hz);

  if (hasPresets) {
    // Render configured presets
    const sortedPresets = [...presets].sort((a, b) => {
      // Sort by frequency (lower first)
      return a.frequency_hz - b.frequency_hz;
    });

    return (
      <div className="band-buttons" data-testid={`band-buttons-${rig.index}`}>
        {sortedPresets.map((preset, i) => {
          const isActive = preset.frequency_hz === rig.frequency_hz;
          return (
            <button
              key={`${preset.label}-${i}`}
              className={`band-btn ${isActive ? 'active' : ''}`}
              onClick={() => handleBandClick(preset.frequency_hz)}
              disabled={!rig.enabled || !rig.connected}
              title={`${(preset.frequency_hz / 1e6).toFixed(3)} MHz`}
            >
              {preset.label}
            </button>
          );
        })}
      </div>
    );
  }

  // Render quick default bands
  const quickBands = BANDS.filter((b) => QUICK_BAND_LABELS.includes(b.label));

  return (
    <div className="band-buttons" data-testid={`band-buttons-${rig.index}`}>
      {quickBands.map((band) => {
        const isActive = currentBand?.label === band.label;
        return (
          <button
            key={band.label}
            className={`band-btn ${isActive ? 'active' : ''}`}
            onClick={() => handleBandClick(band.default)}
            disabled={!rig.enabled || !rig.connected}
            title={`${(band.default / 1e6).toFixed(3)} MHz`}
          >
            {band.label}
          </button>
        );
      })}
    </div>
  );
}
