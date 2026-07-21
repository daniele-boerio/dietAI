import { createContext, useCallback, useContext, useState } from 'react';
import { NavLink, Navigate, Route, Routes } from 'react-router-dom';
import {
  CalendarDays,
  ChefHat,
  LayoutDashboard,
  LogOut,
  Menu,
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
import SettingsPage from './pages/SettingsPage';
import LoginPage from './pages/LoginPage';
import OnboardingPage from './pages/OnboardingPage';
import Toast from './components/Toast';
import ThemeToggle from './components/ThemeToggle';

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
  const [toasts, setToasts] = useState([]);
  const [navOpen, setNavOpen] = useState(false);

  const addToast = useCallback((message, type = 'success') => {
    const id = Date.now() + Math.random();
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 3600);
  }, []);

  const ctx = { addToast };

  // Finché mancano la API key o la dieta non c'è niente da pianificare: l'app
  // mostra solo il percorso guidato, non una interfaccia piena di stati vuoti.
  const needsOnboarding = !user.has_api_key || !user.has_active_diet;

  if (needsOnboarding) {
    return (
      <AppContext.Provider value={ctx}>
        <OnboardingPage />
        <Toast toasts={toasts} />
      </AppContext.Provider>
    );
  }

  const navLinks = [
    { to: '/', icon: LayoutDashboard, label: 'Oggi', end: true },
    { to: '/plan', icon: CalendarDays, label: 'Settimana' },
    { to: '/shopping', icon: ShoppingCart, label: 'Spesa' },
    { to: '/recipes', icon: ChefHat, label: 'Ricettario' },
    { to: '/tracking', icon: TrendingUp, label: 'Andamento' },
  ];

  return (
    <AppContext.Provider value={ctx}>
      <div className="app-layout">
        <header className="topbar">
          <button className="icon-button" onClick={() => setNavOpen(true)} aria-label="Apri menu">
            <Menu size={20} />
          </button>
          <span className="topbar-logo">DietAI</span>
        </header>

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
              to="/settings/diet"
              className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}
            >
              <Salad />
              <span>La mia dieta</span>
            </NavLink>
            <NavLink
              to="/settings/preferences"
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

        <main className="main-content">
          <Routes>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/plan" element={<PlanningPage />} />
            <Route path="/plan/next" element={<PlanningPage nextWeek />} />
            <Route path="/meals/:mealId" element={<MealDetailPage />} />
            <Route path="/shopping" element={<ShoppingPage />} />
            <Route path="/recipes" element={<RecipesPage />} />
            <Route path="/recipes/:recipeId" element={<RecipeDetailPage />} />
            <Route path="/tracking" element={<TrackingPage />} />
            <Route path="/settings" element={<Navigate to="/settings/diet" replace />} />
            <Route path="/settings/:tab" element={<SettingsPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>

      <Toast toasts={toasts} />
    </AppContext.Provider>
  );
}
