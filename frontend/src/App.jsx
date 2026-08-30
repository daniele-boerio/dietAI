import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { NavLink, Navigate, Route, Routes, useLocation } from 'react-router-dom';
import {
  CalendarDays,
  ChefHat,
  LayoutDashboard,
  LogOut,
  Menu,
  Refrigerator,
  Salad,
  Settings,
  ShoppingCart,
  Sprout,
  TrendingUp,
} from 'lucide-react';
import { useAuth } from './AuthContext';

import DashboardPage from './pages/DashboardPage';
import PlanningPage from './pages/PlanningPage';
import MealDetailPage from './pages/MealDetailPage';
import ShoppingPage from './pages/ShoppingPage';
import RecipesPage from './pages/RecipesPage';
import RecipeDetailPage from './pages/RecipeDetailPage';
import TrackingPage from './pages/TrackingPage';
import DietPage from './pages/DietPage';
import PantryPage from './pages/PantryPage';
import SettingsPage from './pages/SettingsPage';
import LoginPage from './pages/LoginPage';
import OnboardingPage from './pages/OnboardingPage';
import Toast from './components/Toast';
import ThemeToggle from './components/ThemeToggle';
import ErrorBoundary from './components/ErrorBoundary';

// ── Contesto globale: toast e poco altro ──
// Lo stato del server non si tiene qui: ogni pagina carica quello che le serve e lo
// ricarica dopo le mutazioni. Con un solo utente e dati che cambiano poco, una cache
// globale costerebbe più bug che millisecondi.
const AppContext = createContext();
export const useApp = () => useContext(AppContext);

export default function App() {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="auth-layout">
        <div className="spinner" />
      </div>
    );
  }

  if (!user) {
    return (
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    );
  }

  return <AuthenticatedApp key={user.id} />;
}

function AuthenticatedApp() {
  const { user, logout } = useAuth();
  const { pathname } = useLocation();
  const [toasts, setToasts] = useState([]);
  const [navOpen, setNavOpen] = useState(false);

  const addToast = useCallback((message, type = 'success') => {
    const id = Date.now() + Math.random();
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 3600);
  }, []);

  // Col menu aperto la pagina dietro non deve scorrere: sul telefono il dito prende
  // quasi sempre la pagina invece del cassetto, e si finisce altrove senza capire perché.
  useEffect(() => {
    if (!navOpen) return undefined;
    const precedente = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = precedente;
    };
  }, [navOpen]);

  // `apriMenu` sta nel contesto perché il piano si tiene la propria testata: sul
  // telefono la barra dell'app e quella della pagina erano due, 219px prima del primo
  // piatto, e per fonderle in una sola serve che quella pagina possa aprire il menu.
  const ctx = { addToast, apriMenu: () => setNavOpen(true) };

  // Finché mancano la API key o la dieta non c'è niente da pianificare: l'app
  // mostra solo il percorso guidato, non una interfaccia piena di stati vuoti.
  //
  // La chiave conta però solo per chi la gestisce: chi genera con quella
  // dell'amministratore non ha nessuno schermo da cui inserirla, e se pesasse anche
  // per lui resterebbe chiuso nell'onboarding per sempre — con tutti i passi fatti e
  // nessun modo di uscirne.
  const needsOnboarding =
    (user.can_manage_api_key && !user.has_api_key) || !user.has_active_diet;

  if (needsOnboarding) {
    return (
      <AppContext.Provider value={ctx}>
        <OnboardingPage />
        <Toast toasts={toasts} />
      </AppContext.Provider>
    );
  }

  // Solo il piano, per ora: è la pagina che si scorre a lungo con una mano sola.
  const testataPropria = pathname === '/plan' || pathname.startsWith('/plan/');

  const navLinks = [
    { to: '/', icon: LayoutDashboard, label: 'Oggi', end: true },
    { to: '/plan', icon: CalendarDays, label: 'Settimana' },
    { to: '/shopping', icon: ShoppingCart, label: 'Spesa' },
    // La dispensa sta accanto alla spesa perché ne è l'altra metà: la lista è quello
    // che manca, la dispensa quello che c'è già — e la seconda si sottrae dalla prima.
    { to: '/pantry', icon: Refrigerator, label: 'Dispensa' },
    { to: '/recipes', icon: ChefHat, label: 'Ricettario' },
    { to: '/tracking', icon: TrendingUp, label: 'Andamento' },
  ];

  return (
    <AppContext.Provider value={ctx}>
      <div className="app-layout">
        {/* Il piano ha una testata sua che fa anche da barra dell'app: titolo, frecce
            e la striscia dei sette giorni stanno insieme, e restano ferme mentre la
            settimana scorre. Averne due, una sopra l'altra, voleva dire cominciare a
            leggere i pasti a 219px dal bordo dello schermo. */}
        {!testataPropria && (
          <header className="topbar">
            <button className="icon-button" onClick={() => setNavOpen(true)} aria-label="Apri menu">
              <Menu size={20} />
            </button>
            <span className="topbar-logo">DietAI</span>
          </header>
        )}

        {navOpen && <div className="sidebar-backdrop" onClick={() => setNavOpen(false)} />}

        <nav
          className={`sidebar ${navOpen ? 'open' : ''}`}
          onClick={(e) => {
            if (e.target.closest('a')) setNavOpen(false);
          }}
        >
          <div className="sidebar-logo">
            <Sprout size={22} />
            DietAI
          </div>

          <div className="sidebar-nav">
            {navLinks.map(({ to, icon: Icon, label, end }) => (
              <NavLink
                key={to}
                to={to}
                end={end}
                className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}
              >
                <Icon />
                <span>{label}</span>
              </NavLink>
            ))}

            <div className="sidebar-section">Configurazione</div>
            <NavLink
              to="/diet"
              className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}
            >
              <Salad />
              <span>La mia dieta</span>
            </NavLink>
            {/* Le impostazioni sono più di una scheda: la voce punta alla pagina, non
                a una scheda in particolare, o le due voci del menu si accenderebbero
                a vicenda a seconda di dove sei dentro. */}
            <NavLink
              to="/settings"
              className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}
            >
              <Settings />
              <span>Impostazioni</span>
            </NavLink>
          </div>

          <div className="sidebar-footer">
            <div className="sidebar-user">
              <span className="sidebar-username" title={user.email}>
                {user.email}
              </span>
              <ThemeToggle />
              <button className="icon-button danger" onClick={logout} title="Esci">
                <LogOut size={16} />
              </button>
            </div>
          </div>
        </nav>

        <main className={`main-content ${testataPropria ? 'senza-topbar' : ''}`}>
          {/* Un errore in una pagina non deve spegnere l'app: senza questa rete
              resterebbe una finestra vuota, nera col tema scuro, e sul telefono
              nemmeno un modo per capire cosa sia successo. */}
          <ErrorBoundary resetKey={pathname}>
            <Routes>
              <Route path="/" element={<DashboardPage />} />
              <Route path="/plan" element={<PlanningPage />} />
              {/* Il lunedì della settimana da aprire, o `next` — l'indirizzo di prima,
                  che resta valido dovunque sia già linkato. */}
              <Route path="/plan/:weekStart" element={<PlanningPage />} />
              <Route path="/meals/:mealId" element={<MealDetailPage />} />
              <Route path="/shopping" element={<ShoppingPage />} />
              <Route path="/recipes" element={<RecipesPage />} />
              <Route path="/recipes/:recipeId" element={<RecipeDetailPage />} />
              <Route path="/tracking" element={<TrackingPage />} />
              <Route path="/diet" element={<DietPage />} />
              <Route path="/pantry" element={<PantryPage />} />
              {/* Dieta e dispensa stavano fra le impostazioni: i vecchi indirizzi restano
                  validi per i collegamenti già in giro (e per chi li aveva nei preferiti). */}
              <Route path="/settings/diet" element={<Navigate to="/diet" replace />} />
              <Route path="/settings/pantry" element={<Navigate to="/pantry" replace />} />
              {/* Sempre con la scheda nell'indirizzo: così quella aperta risulta anche
                  accesa nell'elenco a fianco, e il link si può mandare a qualcuno. */}
              <Route path="/settings" element={<Navigate to="/settings/preferences" replace />} />
              <Route path="/settings/:tab" element={<SettingsPage />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </ErrorBoundary>
        </main>
      </div>

      <Toast toasts={toasts} />
    </AppContext.Provider>
  );
}
