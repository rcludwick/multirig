import { useState, useCallback, useRef, useEffect } from 'react';
import { useRigStore, useUiStore } from '@/stores';
import { formatFreq, parseFrequencyInput, bandLabelForHz, getModeDescription } from '@/utils';
import type { RigStatus } from '@/types';

interface LcdDisplayProps {
  rig: RigStatus;
}

/**
 * LCD Display component - preserves original ham radio aesthetic.
 * Shows frequency, mode, and VFO information.
 */
export default function LcdDisplay({ rig }: LcdDisplayProps) {
  const { setRigFrequency } = useRigStore();
  const { activeFreqEditor, openFreqEditor, closeFreqEditor, getFreqUnit, setFreqUnit } = useUiStore();

  const isEditing = activeFreqEditor === rig.index;
  const [inputValue, setInputValue] = useState('');
  const [selectedUnit, setSelectedUnit] = useState<'auto' | 'mhz' | 'khz' | 'hz'>('auto');
  const inputRef = useRef<HTMLInputElement>(null);

  const { value: freqDisplay, unit: freqUnit } = formatFreq(rig.frequency_hz);
  const band = bandLabelForHz(rig.frequency_hz);
  const modeDesc = getModeDescription(rig.mode);

  // Determine LCD state classes
  const lcdClasses = [
    'lcd',
    !rig.connected && 'disconnected',
    !rig.enabled && 'disabled',
    rig.inverted && 'inverted',
  ].filter(Boolean).join(' ');

  // Compute inline styles for rig color
  const lcdStyle: React.CSSProperties = {};
  if (rig.enabled && rig.connected) {
    if (rig.inverted) {
      // Inverted: dark bg, colored text with glow
      lcdStyle.color = rig.color;
      lcdStyle.textShadow = `0 0 8px ${rig.color}, 0 0 16px ${rig.color}`;
    } else {
      // Normal: colored gradient background
      lcdStyle.background = `linear-gradient(180deg, ${rig.color}ee, ${rig.color}cc)`;
    }
  }

  const handleFreqClick = useCallback(() => {
    if (!rig.enabled || !rig.connected) return;
    const { value } = formatFreq(rig.frequency_hz);
    setInputValue(value);
    setSelectedUnit(getFreqUnit(rig.index));
    openFreqEditor(rig.index);
  }, [rig, openFreqEditor, getFreqUnit]);

  const handleSave = useCallback(() => {
    const hz = parseFrequencyInput(inputValue, selectedUnit);
    if (hz != null && hz > 0) {
      setRigFrequency(rig.index, hz);
      setFreqUnit(rig.index, selectedUnit);
    }
    closeFreqEditor();
  }, [inputValue, selectedUnit, rig.index, setRigFrequency, setFreqUnit, closeFreqEditor]);

  const handleCancel = useCallback(() => {
    closeFreqEditor();
  }, [closeFreqEditor]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleSave();
    } else if (e.key === 'Escape') {
      handleCancel();
    }
  }, [handleSave, handleCancel]);

  // Focus input when editor opens
  useEffect(() => {
    if (isEditing && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [isEditing]);

  // Format VFO frequencies
  const hasVfoB = rig.frequency_a_hz != null || rig.frequency_b_hz != null;
  const vfoA = formatFreq(rig.frequency_a_hz ?? rig.frequency_hz);
  const vfoB = formatFreq(rig.frequency_b_hz);
  const activeVfo = rig.vfo?.includes('B') ? 'B' : 'A';

  return (
    <div
      className={lcdClasses}
      style={lcdStyle}
      data-testid={`rig-lcd-${rig.index}`}
    >
      {/* Main frequency row */}
      <div className="lcd-row">
        <button
          className="freq-btn"
          onClick={handleFreqClick}
          disabled={!rig.enabled || !rig.connected}
          data-testid={`rig-frequency-${rig.index}`}
        >
          <span className="freq">{freqDisplay}</span>
          <span className="unit">{freqUnit}</span>
        </button>
        {band && <span className="band">{band}</span>}
      </div>

      {/* Mode row */}
      <div className="lcd-subrow">
        <span className="mode" title={modeDesc}>
          {rig.mode || '---'}
        </span>
      </div>

      {/* VFO frequencies (when dual VFO) */}
      {hasVfoB && (
        <div className="vfo-freqs">
          <span className={activeVfo === 'A' ? 'vfo-active' : ''}>
            <span className="vfo-label">A</span>
            {vfoA.value} {vfoA.unit}
          </span>
          <span className={activeVfo === 'B' ? 'vfo-active' : ''}>
            <span className="vfo-label">B</span>
            {vfoB.value} {vfoB.unit}
          </span>
        </div>
      )}

      {/* Frequency editor (inline) */}
      {isEditing && (
        <div className="freq-editor">
          <input
            ref={inputRef}
            type="text"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Enter frequency"
          />
          <select
            value={selectedUnit}
            onChange={(e) => setSelectedUnit(e.target.value as typeof selectedUnit)}
          >
            <option value="auto">Auto</option>
            <option value="mhz">MHz</option>
            <option value="khz">kHz</option>
            <option value="hz">Hz</option>
          </select>
          <button className="btn-save" onClick={handleSave}>
            Save
          </button>
          <button className="btn-cancel" onClick={handleCancel}>
            Cancel
          </button>
        </div>
      )}
    </div>
  );
}
