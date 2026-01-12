import { NavLink } from 'react-router-dom';
import { useAutoSave } from '@/hooks';
import './PageNav.css';

export default function PageNav() {
  const { isDirty, isSaving } = useAutoSave();

  return (
    <nav className="page-nav">
      <div className="page-nav-links">
        <NavLink
          to="/"
          className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
        >
          Dashboard
        </NavLink>
        <NavLink
          to="/settings"
          className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
        >
          Settings
        </NavLink>
      </div>
      <div className="page-nav-status">
        {isSaving && <span className="save-indicator saving">Saving...</span>}
        {isDirty && !isSaving && (
          <span className="save-indicator dirty">Unsaved</span>
        )}
      </div>
    </nav>
  );
}
