import { useUiStore } from '@/stores';
import './RigSection.css';

interface RigSectionProps {
  rigIndex: number;
  name: string;
  title: string;
  defaultCollapsed?: boolean;
  children: React.ReactNode;
}

/**
 * Collapsible section within a rig card.
 * State is persisted to localStorage via uiStore.
 */
export default function RigSection({
  rigIndex,
  name,
  title,
  defaultCollapsed = false,
  children,
}: RigSectionProps) {
  const { toggleSection } = useUiStore();

  // Check if this section has been explicitly toggled, otherwise use default
  const key = `rig-${rigIndex}-${name}`;
  const storedCollapsed = useUiStore((s) => s.collapsedSections[key]);
  const isCollapsed = storedCollapsed !== undefined ? storedCollapsed : defaultCollapsed;

  const handleToggle = () => {
    toggleSection(rigIndex, name);
  };

  return (
    <div
      className={`rig-section ${isCollapsed ? 'collapsed' : ''}`}
      data-section={name}
      data-testid={`rig-section-${rigIndex}-${name}`}
    >
      <button
        className="rig-section-header"
        onClick={handleToggle}
        type="button"
      >
        <span className="rig-section-title">{title}</span>
        <span className="rig-section-chevron">{isCollapsed ? '▸' : '▾'}</span>
      </button>
      {!isCollapsed && (
        <div className="rig-section-body">
          {children}
        </div>
      )}
    </div>
  );
}
