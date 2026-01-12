import { useConfigStore } from '@/stores';
import './RigctlSection.css';

/**
 * Rigctl listener configuration section.
 */
export default function RigctlSection() {
  const { config, updateConfig } = useConfigStore();

  if (!config) return null;

  const handleHostChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    updateConfig({ rigctl_listen_host: e.target.value });
  };

  const handlePortChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const port = parseInt(e.target.value, 10);
    if (!isNaN(port) && port > 0 && port < 65536) {
      updateConfig({ rigctl_listen_port: port });
    }
  };

  return (
    <section className="settings-section rigctl-section">
      <h2>Rigctl Listener</h2>
      <p className="section-desc">
        External applications (like WSJT-X) connect to this address.
      </p>

      <div className="rigctl-fields">
        <div className="form-field">
          <label>Listen Address</label>
          <select
            value={config.rigctl_listen_host}
            onChange={handleHostChange}
            data-testid="rigctl-host"
          >
            <option value="127.0.0.1">127.0.0.1 (localhost only)</option>
            <option value="0.0.0.0">0.0.0.0 (all interfaces)</option>
          </select>
        </div>

        <div className="form-field">
          <label>Port</label>
          <input
            type="number"
            value={config.rigctl_listen_port}
            onChange={handlePortChange}
            min={1}
            max={65535}
            data-testid="rigctl-port"
          />
        </div>
      </div>
    </section>
  );
}
