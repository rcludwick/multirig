import { useConfigStore } from '@/stores';
import { useAutoSave } from '@/hooks';
import ProfileSection from './settings/ProfileSection';
import RigctlSection from './settings/RigctlSection';
import RigConfigCard from './settings/RigConfigCard';
import './Settings.css';

/**
 * Settings page - configuration management.
 */
export default function Settings() {
  const { config, addRig, removeRig, updateRigConfig } = useConfigStore();
  const { isDirty, isSaving, lastSaveError } = useAutoSave();

  if (!config) {
    return (
      <div className="settings-loading">
        <p>Loading configuration...</p>
      </div>
    );
  }

  return (
    <div className="settings" data-testid="settings-page">
      {/* Save status */}
      {(isDirty || isSaving || lastSaveError) && (
        <div className={`settings-status ${lastSaveError ? 'error' : ''}`}>
          {isSaving && <span>Saving...</span>}
          {isDirty && !isSaving && <span>Unsaved changes</span>}
          {lastSaveError && <span>Error: {lastSaveError}</span>}
        </div>
      )}

      {/* Profile management */}
      <ProfileSection />

      {/* Rigctl listener settings */}
      <RigctlSection />

      {/* Rig list */}
      <section className="settings-section">
        <div className="section-header">
          <h2>Rigs</h2>
          <button
            className="btn btn-primary btn-sm"
            onClick={addRig}
            data-testid="add-rig-btn"
          >
            + Add Rig
          </button>
        </div>

        <div className="rig-list">
          {config.rigs.map((rig, index) => (
            <RigConfigCard
              key={index}
              index={index}
              rig={rig}
              onUpdate={(partial) => updateRigConfig(index, partial)}
              onRemove={() => removeRig(index)}
              canRemove={config.rigs.length > 1}
            />
          ))}
        </div>
      </section>
    </div>
  );
}
