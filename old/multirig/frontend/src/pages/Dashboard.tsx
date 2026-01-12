import { useRigStore } from '@/stores';
import { ServerBar, RigCard } from '@/components/dashboard';
import './Dashboard.css';

/**
 * Dashboard page - main rig control interface.
 */
export default function Dashboard() {
  const { rigs } = useRigStore();

  return (
    <div className="dashboard" data-testid="dashboard-page">
      <ServerBar />

      <div className="rig-grid">
        {rigs.map((rig) => (
          <RigCard key={rig.index} rig={rig} />
        ))}
      </div>

      {rigs.length === 0 && (
        <div className="dashboard-empty">
          <p>No rigs configured.</p>
          <p className="dashboard-empty-hint">
            Go to Settings to add your first rig.
          </p>
        </div>
      )}
    </div>
  );
}
