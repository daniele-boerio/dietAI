import { useState } from 'react';
import { Moon, Sun } from 'lucide-react';

// Il tema vive su <html data-theme>: main.jsx lo applica prima del render, qui si
// cambia solo a runtime e si ricorda la scelta.
// `esteso`: nella pagina «Altro» del telefono non è un'icona in un angolo ma una
// riga come le altre — icona, parola, e l'interruttore a destra. È lo stesso comando,
// e non merita un secondo componente.
export default function ThemeToggle({ esteso = false }) {
  const [theme, setTheme] = useState(
    () => document.documentElement.getAttribute('data-theme') || 'dark'
  );

  const toggle = () => {
    const next = theme === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('theme', next);
    setTheme(next);
  };

  if (esteso) {
    return (
      <button className="altro-tema" onClick={toggle}>
        {theme === 'dark' ? <Moon size={17} /> : <Sun size={17} />}
        <span>Tema scuro</span>
        <span className={`toggle ${theme === 'dark' ? 'on' : ''}`}>
          <i />
        </span>
      </button>
    );
  }

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
