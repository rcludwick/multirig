import { InputHTMLAttributes } from 'react';
import './Switch.css';

interface SwitchProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'type'> {
  label?: string;
  variant?: 'default' | 'power' | 'follow';
}

export default function Switch({
  label,
  variant = 'default',
  className = '',
  ...props
}: SwitchProps) {
  return (
    <label className={`switch switch-${variant} ${className}`}>
      <input type="checkbox" {...props} />
      <span className="switch-slider" />
      {label && <span className="switch-label">{label}</span>}
    </label>
  );
}
