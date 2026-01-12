import { useState } from 'react';
import { useConfigStore } from '@/stores';
import { BANDS } from '@/utils';
import type { RigConfig, BandPreset } from '@/types';
import './RigConfigCard.css';

interface RigConfigCardProps {
  index: number;
  rig: RigConfig;
  onUpdate: (partial: Partial<RigConfig>) => void;
  onRemove: () => void;
  canRemove: boolean;
}

/**
 * Individual rig configuration card.
 */
export default function RigConfigCard({
  index,
  rig,
  onUpdate,
  onRemove,
  canRemove,
}: RigConfigCardProps) {
  const { rigModels } = useConfigStore();
  const [showBandEditor, setShowBandEditor] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const isRigctld = rig.connection_type === 'rigctld';

  const handleInputChange = (key: keyof RigConfig, value: string | number | boolean) => {
    onUpdate({ [key]: value });
  };

  const handleRemove = () => {
    if (confirmDelete) {
      onRemove();
    } else {
      setConfirmDelete(true);
      setTimeout(() => setConfirmDelete(false), 3000);
    }
  };

  // Band preset management
  const handleBandToggle = (label: string, enabled: boolean) => {
    const presets = [...(rig.band_presets || [])];
    const existing = presets.find((p) => p.label === label);
    if (existing) {
      existing.enabled = enabled;
    } else {
      const band = BANDS.find((b) => b.label === label);
      if (band) {
        presets.push({
          label,
          frequency_hz: band.default,
          enabled,
          lower_hz: band.lo,
          upper_hz: band.hi,
        });
      }
    }
    onUpdate({ band_presets: presets });
  };

  const handleBandFreqChange = (label: string, hz: number) => {
    const presets = [...(rig.band_presets || [])];
    const existing = presets.find((p) => p.label === label);
    if (existing) {
      existing.frequency_hz = hz;
      onUpdate({ band_presets: presets });
    }
  };

  const getPreset = (label: string): BandPreset | undefined => {
    return rig.band_presets?.find((p) => p.label === label);
  };

  return (
    <div className="rig-config-card" data-testid={`rig-config-${index}`}>
      <div className="rig-config-header">
        <div
          className="rig-color-indicator"
          style={{ background: rig.color }}
        />
        <input
          type="text"
          className="rig-name-input"
          value={rig.name}
          onChange={(e) => handleInputChange('name', e.target.value)}
          placeholder="Rig name"
          data-testid={`rig-name-${index}`}
        />
        <button
          className={`btn btn-sm ${confirmDelete ? 'btn-danger' : 'btn-ghost'}`}
          onClick={handleRemove}
          disabled={!canRemove}
          title={confirmDelete ? 'Click again to confirm' : 'Remove rig'}
        >
          {confirmDelete ? 'Confirm?' : 'Remove'}
        </button>
      </div>

      {/* Connection type */}
      <div className="form-row">
        <label>Connection</label>
        <select
          value={rig.connection_type}
          onChange={(e) => handleInputChange('connection_type', e.target.value)}
          data-testid={`connection-type-${index}`}
        >
          <option value="rigctld">rigctld (TCP)</option>
          <option value="hamlib">hamlib (Direct)</option>
        </select>
      </div>

      {/* Connection settings based on type */}
      {isRigctld ? (
        <>
          <div className="form-row">
            <label>Host</label>
            <input
              type="text"
              value={rig.host}
              onChange={(e) => handleInputChange('host', e.target.value)}
              placeholder="127.0.0.1"
              data-testid={`rig-host-${index}`}
            />
          </div>
          <div className="form-row">
            <label>Port</label>
            <input
              type="number"
              value={rig.port}
              onChange={(e) => handleInputChange('port', parseInt(e.target.value, 10) || 4532)}
              min={1}
              max={65535}
              data-testid={`rig-port-${index}`}
            />
          </div>
          <div className="form-row">
            <label>Managed</label>
            <input
              type="checkbox"
              checked={rig.managed || false}
              onChange={(e) => handleInputChange('managed', e.target.checked)}
              data-testid={`rig-managed-${index}`}
            />
            <span className="form-hint">Start rigctld automatically</span>
          </div>
        </>
      ) : (
        <>
          <div className="form-row">
            <label>Model</label>
            <select
              value={rig.model_id || ''}
              onChange={(e) => handleInputChange('model_id', parseInt(e.target.value, 10) || 0)}
              data-testid={`rig-model-${index}`}
            >
              <option value="">Select model...</option>
              {rigModels.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.label || `${m.manufacturer} ${m.model}`}
                </option>
              ))}
            </select>
          </div>
          <div className="form-row">
            <label>Device</label>
            <input
              type="text"
              value={rig.device || ''}
              onChange={(e) => handleInputChange('device', e.target.value)}
              placeholder="/dev/ttyUSB0"
              data-testid={`rig-device-${index}`}
            />
          </div>
          <div className="form-row">
            <label>Baud Rate</label>
            <select
              value={rig.baud || ''}
              onChange={(e) => handleInputChange('baud', parseInt(e.target.value, 10) || 0)}
            >
              <option value="">Auto</option>
              {[4800, 9600, 19200, 38400, 57600, 115200].map((b) => (
                <option key={b} value={b}>{b}</option>
              ))}
            </select>
          </div>
          <div className="form-row">
            <label>Serial Options</label>
            <input
              type="text"
              value={rig.serial_opts || ''}
              onChange={(e) => handleInputChange('serial_opts', e.target.value)}
              placeholder="8N1"
            />
          </div>
          <div className="form-row">
            <label>Extra Args</label>
            <input
              type="text"
              value={rig.extra_args || ''}
              onChange={(e) => handleInputChange('extra_args', e.target.value)}
              placeholder="-vvv"
            />
          </div>
        </>
      )}

      {/* Visual settings */}
      <div className="form-row">
        <label>Color</label>
        <input
          type="color"
          value={rig.color}
          onChange={(e) => handleInputChange('color', e.target.value)}
          data-testid={`rig-color-${index}`}
        />
      </div>

      <div className="form-row">
        <label>Inverted LCD</label>
        <input
          type="checkbox"
          checked={rig.inverted}
          onChange={(e) => handleInputChange('inverted', e.target.checked)}
          data-testid={`rig-inverted-${index}`}
        />
      </div>

      <div className="form-row">
        <label>Allow Out-of-Band</label>
        <input
          type="checkbox"
          checked={rig.allow_out_of_band}
          onChange={(e) => handleInputChange('allow_out_of_band', e.target.checked)}
        />
      </div>

      <div className="form-row">
        <label>Poll Interval (ms)</label>
        <input
          type="number"
          value={rig.poll_interval_ms}
          onChange={(e) => handleInputChange('poll_interval_ms', parseInt(e.target.value, 10) || 1000)}
          min={100}
          max={10000}
          step={100}
        />
      </div>

      {/* Band presets */}
      <div className="band-presets">
        <button
          className="btn btn-ghost btn-sm"
          onClick={() => setShowBandEditor(!showBandEditor)}
        >
          {showBandEditor ? 'Hide' : 'Edit'} Band Presets
        </button>

        {showBandEditor && (
          <div className="band-editor">
            {BANDS.map((band) => {
              const preset = getPreset(band.label);
              const enabled = preset?.enabled ?? false;
              const freqHz = preset?.frequency_hz ?? band.default;

              return (
                <div key={band.label} className="band-row">
                  <input
                    type="checkbox"
                    checked={enabled}
                    onChange={(e) => handleBandToggle(band.label, e.target.checked)}
                  />
                  <span className="band-label">{band.label}</span>
                  <input
                    type="number"
                    value={freqHz / 1e6}
                    onChange={(e) => handleBandFreqChange(band.label, parseFloat(e.target.value) * 1e6)}
                    step={0.001}
                    disabled={!enabled}
                    className="band-freq"
                  />
                  <span className="band-unit">MHz</span>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
