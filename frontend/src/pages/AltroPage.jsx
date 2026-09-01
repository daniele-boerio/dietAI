import { Link } from 'react-router-dom';
import {
  Ban,
  Carrot,
  ChevronRight,
  Cpu,
  LogOut,
  Merge,
  Refrigerator,
  Salad,
  SlidersHorizontal,
  TrendingUp,
  UserRound,
  Users,
} from 'lucide-react';
import { useAuth } from '../AuthContext';
import ThemeToggle from '../components/ThemeToggle';

// La quinta scheda del telefono.
//
// Le altre quattro sono i posti in cui si sta — cosa mangio, la settimana, la spesa,
// il ricettario. Qui c'è tutto il resto: quello che si apre una volta ogni tanto (la
// dieta, la dispensa, l'andamento) e quello che si imposta una volta e poi resta.
// Non è una griglia di riquadri ma un **elenco**: sono voci che si leggono in fila e
// si toccano una alla volta, e in riquadri sarebbero dodici scatole da scandagliare.
//
// Sul monitor questa pagina non ha una voce che ci porti — quelle cose stanno già
// nella stecca di icone — ma la rotta vale lo stesso: è un elenco di collegamenti, e
// arrivarci non fa danno.
const CUCINA = [
  { to: '/diet', icon: Salad, label: 'La mia dieta' },
  { to: '/pantry', icon: Refrigerator, label: 'Dispensa' },
  { to: '/tracking', icon: TrendingUp, label: 'Andamento' },
  { to: '/settings/preferences', icon: SlidersHorizontal, label: 'Preferenze di cucina' },
  { to: '/settings/base', icon: Carrot, label: 'Ingredienti di base' },
  { to: '/settings/excluded', icon: Ban, label: 'Alimenti esclusi' },
];

// Le stesse tre schede riservate di `SettingsPage`: l'anagrafica è una sola per
// tutti, la chiave la paga una persona sola, e gli account li crea lei.
const AMMINISTRAZIONE = [
  { to: '/settings/models', icon: Cpu, label: 'Modelli AI' },
  { to: '/settings/normalization', icon: Merge, label: 'Nomi e accorpamenti' },
  { to: '/settings/users', icon: Users, label: 'Utenti' },
];

function Voce({ to, icon: Icon, label }) {
  return (
    <Link className="altro-voce" to={to}>
      <Icon />
      <span>{label}</span>
      <ChevronRight className="altro-freccia" />
    </Link>
  );
}

export default function AltroPage() {
  const { user, logout } = useAuth();

  return (
    <>
      <div className="page-header">
        <div>
          <h1 className="page-title">Altro</h1>
          <p className="page-subtitle">Quello che non sta nelle quattro schede</p>
        </div>
      </div>

      {/* Chi sei, in cima: è la prima domanda a cui una pagina di impostazioni deve
          rispondere, e da qui si arriva alla password. */}
      <Link className="card altro-account" to="/settings/account">
        <span className="altro-avatar">
          <UserRound />
        </span>
        <div>
          <strong>{user.email}</strong>
          <span>{user.is_admin ? 'amministratore' : 'account'}</span>
        </div>
        <ChevronRight className="altro-freccia" />
      </Link>

      <div className="altro-gruppo">Cucina</div>
      <div className="altro-elenco">
        {CUCINA.map((v) => (
          <Voce key={v.to} {...v} />
        ))}
      </div>

      {user.is_admin && (
        <>
          <div className="altro-gruppo">Amministrazione</div>
          <div className="altro-elenco">
            {AMMINISTRAZIONE.map((v) => (
              <Voce key={v.to} {...v} />
            ))}
          </div>
        </>
      )}

      {/* Le due cose che non sono pagine: cambiare tema e uscire. In riga, in fondo,
          perché sono comandi e non destinazioni. */}
      <div className="altro-piede">
        <ThemeToggle esteso />
        <button className="altro-esci" onClick={logout}>
          <LogOut size={18} />
          Esci
        </button>
      </div>
    </>
  );
}
