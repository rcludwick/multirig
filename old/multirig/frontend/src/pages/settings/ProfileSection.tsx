import { useState, useEffect } from 'react';
import { useProfileStore, useConfigStore, useRigStore } from '@/stores';
import './ProfileSection.css';

/**
 * Profile management section - select, create, rename, duplicate, delete profiles.
 */
export default function ProfileSection() {
  const { activeProfile } = useRigStore();
  const {
    profiles,
    loadProfiles,
    selectProfile,
    createProfile,
    renameProfile,
    duplicateProfile,
    deleteProfile,
  } = useProfileStore();
  const { loadConfig } = useConfigStore();

  const [showDialog, setShowDialog] = useState<string | null>(null);
  const [inputValue, setInputValue] = useState('');
  const [selectedProfile, setSelectedProfile] = useState('');
  const [message, setMessage] = useState<{ text: string; ok: boolean } | null>(null);

  useEffect(() => {
    loadProfiles();
  }, [loadProfiles]);

  const showMessage = (text: string, ok: boolean) => {
    setMessage({ text, ok });
    setTimeout(() => setMessage(null), 4000);
  };

  const handleSelect = async () => {
    if (!selectedProfile) return;
    try {
      await selectProfile(selectedProfile);
      await loadConfig();
      showMessage(`Switched to "${selectedProfile}"`, true);
      setShowDialog(null);
    } catch (e) {
      showMessage('Failed to switch profile', false);
    }
  };

  const handleCreate = async () => {
    const name = inputValue.trim();
    if (!name) return;
    try {
      await createProfile(name);
      await loadProfiles();
      showMessage(`Created profile "${name}"`, true);
      setShowDialog(null);
      setInputValue('');
    } catch (e) {
      showMessage('Failed to create profile', false);
    }
  };

  const handleRename = async () => {
    const newName = inputValue.trim();
    if (!selectedProfile || !newName) return;
    try {
      await renameProfile(selectedProfile, newName);
      await loadProfiles();
      showMessage(`Renamed to "${newName}"`, true);
      setShowDialog(null);
      setInputValue('');
    } catch (e) {
      showMessage('Failed to rename profile', false);
    }
  };

  const handleDuplicate = async () => {
    const newName = inputValue.trim();
    if (!selectedProfile || !newName) return;
    try {
      await duplicateProfile(selectedProfile, newName);
      await loadProfiles();
      showMessage(`Duplicated as "${newName}"`, true);
      setShowDialog(null);
      setInputValue('');
    } catch (e) {
      showMessage('Failed to duplicate profile', false);
    }
  };

  const handleDelete = async () => {
    if (!selectedProfile) return;
    try {
      await deleteProfile(selectedProfile);
      await loadProfiles();
      showMessage(`Deleted "${selectedProfile}"`, true);
      setShowDialog(null);
    } catch (e) {
      showMessage('Failed to delete profile', false);
    }
  };

  const openDialog = (type: string) => {
    setShowDialog(type);
    setInputValue('');
    setSelectedProfile(activeProfile || profiles[0] || '');
  };

  return (
    <section className="settings-section profile-section">
      <h2>Profile</h2>

      <div className="profile-current">
        <span className="profile-label">Active:</span>
        <span className="profile-name" data-testid="active-profile">
          {activeProfile || '(none)'}
        </span>
      </div>

      <div className="profile-actions">
        <button className="btn btn-ghost btn-sm" onClick={() => openDialog('select')}>
          Switch
        </button>
        <button className="btn btn-ghost btn-sm" onClick={() => openDialog('create')}>
          New
        </button>
        <button className="btn btn-ghost btn-sm" onClick={() => openDialog('rename')}>
          Rename
        </button>
        <button className="btn btn-ghost btn-sm" onClick={() => openDialog('duplicate')}>
          Duplicate
        </button>
        <button
          className="btn btn-ghost btn-sm btn-danger"
          onClick={() => openDialog('delete')}
          disabled={profiles.length <= 1}
        >
          Delete
        </button>
      </div>

      {message && (
        <div className={`profile-message ${message.ok ? 'success' : 'error'}`}>
          {message.text}
        </div>
      )}

      {/* Select dialog */}
      {showDialog === 'select' && (
        <div className="profile-dialog">
          <h3>Switch Profile</h3>
          <select
            value={selectedProfile}
            onChange={(e) => setSelectedProfile(e.target.value)}
          >
            {profiles.map((p) => (
              <option key={p} value={p}>{p}</option>
            ))}
          </select>
          <div className="dialog-actions">
            <button className="btn btn-ghost" onClick={() => setShowDialog(null)}>
              Cancel
            </button>
            <button className="btn btn-primary" onClick={handleSelect}>
              Switch
            </button>
          </div>
        </div>
      )}

      {/* Create dialog */}
      {showDialog === 'create' && (
        <div className="profile-dialog">
          <h3>Create Profile</h3>
          <input
            type="text"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            placeholder="Profile name"
            autoFocus
          />
          <div className="dialog-actions">
            <button className="btn btn-ghost" onClick={() => setShowDialog(null)}>
              Cancel
            </button>
            <button className="btn btn-primary" onClick={handleCreate} disabled={!inputValue.trim()}>
              Create
            </button>
          </div>
        </div>
      )}

      {/* Rename dialog */}
      {showDialog === 'rename' && (
        <div className="profile-dialog">
          <h3>Rename Profile</h3>
          <select
            value={selectedProfile}
            onChange={(e) => setSelectedProfile(e.target.value)}
          >
            {profiles.map((p) => (
              <option key={p} value={p}>{p}</option>
            ))}
          </select>
          <input
            type="text"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            placeholder="New name"
          />
          <div className="dialog-actions">
            <button className="btn btn-ghost" onClick={() => setShowDialog(null)}>
              Cancel
            </button>
            <button className="btn btn-primary" onClick={handleRename} disabled={!inputValue.trim()}>
              Rename
            </button>
          </div>
        </div>
      )}

      {/* Duplicate dialog */}
      {showDialog === 'duplicate' && (
        <div className="profile-dialog">
          <h3>Duplicate Profile</h3>
          <select
            value={selectedProfile}
            onChange={(e) => setSelectedProfile(e.target.value)}
          >
            {profiles.map((p) => (
              <option key={p} value={p}>{p}</option>
            ))}
          </select>
          <input
            type="text"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            placeholder="New profile name"
          />
          <div className="dialog-actions">
            <button className="btn btn-ghost" onClick={() => setShowDialog(null)}>
              Cancel
            </button>
            <button className="btn btn-primary" onClick={handleDuplicate} disabled={!inputValue.trim()}>
              Duplicate
            </button>
          </div>
        </div>
      )}

      {/* Delete dialog */}
      {showDialog === 'delete' && (
        <div className="profile-dialog">
          <h3>Delete Profile</h3>
          <p className="dialog-warning">This cannot be undone.</p>
          <select
            value={selectedProfile}
            onChange={(e) => setSelectedProfile(e.target.value)}
          >
            {profiles.map((p) => (
              <option key={p} value={p}>{p}</option>
            ))}
          </select>
          <div className="dialog-actions">
            <button className="btn btn-ghost" onClick={() => setShowDialog(null)}>
              Cancel
            </button>
            <button className="btn btn-danger" onClick={handleDelete}>
              Delete
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
