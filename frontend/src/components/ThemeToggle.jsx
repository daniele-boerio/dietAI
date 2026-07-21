import { useState } from 'react';
import { Moon, Sun } from 'lucide-react';

// Il tema vive su <html data-theme>: main.jsx lo applica prima del render, qui si
// cambia solo a runtime e si ricorda la scelta.
export default function ThemeToggle() {
  const [theme, setTheme] = useState(
    () => document.documentElement.getAttribute('data-theme') || 'light'
  );

  const toggle = () => {
    const next = theme === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('theme', next);
    setTheme(next);
  };

  return (
    <button
      className="icon-button"
      onClick={toggle}
      title={theme === 'dark' ? 'Tema chiaro' : 'Tema scuro'}
    >
      {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
    </button>
  );
}
