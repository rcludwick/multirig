import { useRigStore } from '@/stores';
import { Switch } from '@/components/common';
import './ServerBar.css';

/**
 * Server control bar - sync toggle, main rig selector, rigctl status.
 */
export default function ServerBar() {
  const {
    rigs,
    syncEnabled,
    syncSourceIndex,
    rigctlToMainEnabled,
    allRigsEnabled,
    rigctlHost,
    rigctlPort,
    setSyncEnabled,
    setSyncSourceIndex,
    setRigctlToMainEnabled,
    setAllRigsEnabled,
  } = useRigStore();

  return (
    <div className="server-bar" data-testid="server-bar">
      {/* Sync toggle */}
      <div className="server-bar-item">
        <label className="server-bar-label">Sync</label>
        <Switch
          checked={syncEnabled}
          onChange={() => setSyncEnabled(!syncEnabled)}
          data-testid="sync-toggle"
        />
      </div>

      {/* Main rig selector */}
      <div className="server-bar-item">
        <label className="server-bar-label">Main Rig</label>
        <select
          className="server-bar-select"
          value={syncSourceIndex}
          onChange={(e) => setSyncSourceIndex(Number(e.target.value))}
          data-testid="main-rig-select"
        >
          {rigs.map((rig, i) => (
            <option key={i} value={i}>
              {rig.name}
            </option>
          ))}
        </select>
      </div>

      {/* Rigctl to main toggle */}
      <div className="server-bar-item">
        <label className="server-bar-label">Rigctl → Main</label>
        <Switch
          checked={rigctlToMainEnabled}
          onChange={() => setRigctlToMainEnabled(!rigctlToMainEnabled)}
          title="Forward rigctl commands to main rig"
          data-testid="rigctl-toggle"
        />
      </div>

      {/* Rigctl endpoint display */}
      <div className="server-bar-item server-bar-endpoint">
        <span className="server-bar-label">Rigctl</span>
        <code className="server-bar-code">{rigctlHost}:{rigctlPort}</code>
      </div>

      {/* All rigs power toggle */}
      <div className="server-bar-item">
        <label className="server-bar-label">All Rigs</label>
        <Switch
          variant="power"
          checked={allRigsEnabled}
          onChange={() => setAllRigsEnabled(!allRigsEnabled)}
          title={allRigsEnabled ? 'Disable all rigs' : 'Enable all rigs'}
          data-testid="all-rigs-toggle"
        />
      </div>
    </div>
  );
}
