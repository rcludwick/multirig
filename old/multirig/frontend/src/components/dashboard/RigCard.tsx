import { useRigStore } from '@/stores';
import { Switch } from '@/components/common';
import LcdDisplay from './LcdDisplay';
import BandButtons from './BandButtons';
import ModeButtons from './ModeButtons';
import RigSection from './RigSection';
import type { RigStatus } from '@/types';
import './RigCard.css';

interface RigCardProps {
  rig: RigStatus;
}

export default function RigCard({ rig }: RigCardProps) {
  const {
    syncSourceIndex,
    toggleRigEnabled,
    toggleRigFollow,
    syncRigFromSource,
    uiErrors,
  } = useRigStore();

  const isMain = rig.index === syncSourceIndex;
  const uiError = uiErrors.get(rig.index);
  const showError = rig.error || rig.last_error || uiError;

  const handlePowerToggle = () => {
    toggleRigEnabled(rig.index);
  };

  const handleFollowToggle = () => {
    toggleRigFollow(rig.index);
  };

  const handleSync = () => {
    syncRigFromSource(rig.index);
  };

  return (
    <div
      className={`rig-card ${!rig.enabled ? 'disabled' : ''}`}
      data-testid={`rig-card-${rig.index}`}
      data-enabled={rig.enabled}
    >
      {/* Header */}
      <div className="rig-header">
        <div className="rig-header-left">
          <h3 className="rig-title">{rig.name}</h3>
          <div className="rig-badges">
            {isMain && <span className="badge badge-accent">MAIN</span>}
            {rig.connected && <span className="badge badge-success">Connected</span>}
            {!rig.connected && rig.enabled && (
              <span className="badge badge-danger">Disconnected</span>
            )}
            {rig.ptt && <span className="badge badge-danger">PTT</span>}
          </div>
        </div>
        <div className="rig-header-right">
          {/* Sync button (not for main rig) */}
          {!isMain && rig.enabled && rig.connected && (
            <button
              className="btn btn-ghost btn-sm"
              onClick={handleSync}
              title="Sync from main rig"
              data-testid={`sync-button-${rig.index}`}
            >
              Sync
            </button>
          )}

          {/* Follow toggle (not for main rig) */}
          {!isMain && (
            <Switch
              variant="follow"
              checked={rig.follow_main}
              onChange={handleFollowToggle}
              disabled={!rig.enabled}
              title={rig.follow_main ? 'Following main' : 'Manual control'}
              data-testid={`follow-switch-${rig.index}`}
            />
          )}

          {/* Power toggle */}
          <Switch
            variant="power"
            checked={rig.enabled}
            onChange={handlePowerToggle}
            title={rig.enabled ? 'Disable rig' : 'Enable rig'}
            data-testid={`power-switch-${rig.index}`}
          />
        </div>
      </div>

      {/* LCD Display */}
      <LcdDisplay rig={rig} />

      {/* Error display */}
      {showError && (
        <div className="rig-error" data-testid={`rig-error-${rig.index}`}>
          <span className="rig-error-icon">⚠</span>
          <span className="rig-error-body">
            {uiError || rig.last_error || rig.error}
          </span>
        </div>
      )}

      {/* Collapsible sections */}
      <RigSection rigIndex={rig.index} name="bands" title="Bands" defaultCollapsed>
        <BandButtons rig={rig} />
      </RigSection>

      <RigSection rigIndex={rig.index} name="modes" title="Modes" defaultCollapsed>
        <ModeButtons rig={rig} />
      </RigSection>
    </div>
  );
}
