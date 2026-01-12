import { useRigStore } from '@/stores';
import './TopBar.css';

export default function TopBar() {
  const activeProfile = useRigStore((s) => s.activeProfile);
  const rigctlHost = useRigStore((s) => s.rigctlHost);
  const rigctlPort = useRigStore((s) => s.rigctlPort);

  return (
    <header className="topbar">
      <div className="topbar-brand">
        <span className="topbar-logo">MultiRig</span>
        {activeProfile && (
          <span className="topbar-profile">{activeProfile}</span>
        )}
      </div>
      <div className="topbar-meta">
        <span className="topbar-listener">
          rigctl: {rigctlHost}:{rigctlPort}
        </span>
      </div>
    </header>
  );
}
