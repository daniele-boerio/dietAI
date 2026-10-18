import { Suspense, createContext, lazy, useCallback, useContext, useMemo, useState } from 'react';
import { NavLink, Navigate, Route, Routes, useLocation } from 'react-router-dom';
import {
  CalendarDays,
  ChefHat,
  Ellipsis,
  LayoutDashboard,
  LogOut,
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
import ShoppingPage from './pages/ShoppingPage';
import AltroPage from './pages/AltroPage';
import LoginPage from './pages/LoginPage';

// Le schede di tutti i giorni (home, piano, spesa) arrivano subito; il resto si
// scarica quando lo si apre. Prima il login portava con sé anche Impostazioni,
// Onboarding e Dieta — un bundle unico da 390 kB su una rete da supermercato.
const MealDetailPage = lazy(() => import('./pages/MealDetailPage'));
const RecipesPage = lazy(() => import('./pages/RecipesPage'));
const RecipeDetailPage = lazy(() => import('./pages/RecipeDetailPage'));
const TrackingPage = lazy(() => import('./pages/TrackingPage'));
const DietPage = lazy(() => import('./pages/DietPage'));
const PantryPage = lazy(() => import('./pages/PantryPage'));
const SettingsPage = lazy(() => import('./pages/SettingsPage'));
const OnboardingPage = lazy(() => import('./pages/OnboardingPage'));
import Toast from './components/Toast';
import ThemeToggle from './components/ThemeToggle';
import ErrorBoundary from './components/ErrorBoundary';
import LoadError from './components/LoadError';

// ── Contesto globale: toast e poco altro ──
// Lo stato del server non si tiene qui: ogni pagina carica quello che le serve e lo
// ricarica dopo le mutazioni. Con un solo utente e dati che cambiano poco, una cache
// globale costerebbe più bug che millisecondi.
const AppContext = createContext();
export const useApp = () => useContext(AppContext);

export default function App() {
  const { user, loading, startupError, retry } = useAuth();

  if (loading) {
    return (
      <div className="auth-layout">
        <div className="spinner" />
      </div>
    );
  }

  // Non si sa se la sessione c'è: senza rete il login sarebbe una bugia.
  if (startupError) {
    return (
      <div className="auth-layout">
        <LoadError
          message={`${startupError}. Controlla la connessione e riprova.`}
          onRetry={retry}
        />
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

  const closeToast = useCallback(
    (id) => setToasts((prev) => prev.filter((t) => t.id !== id)),
    []
  );

  // Gli errori restano più a lungo: sono l'unico segno che un'azione non è andata, e
  // tre secondi e mezzo non bastano a leggerli (tanto meno con un lettore di schermo).
  // Si chiudono anche a mano.
  const addToast = useCallback(
    (message, type = 'success') => {
      const id = Date.now() + Math.random();
      setToasts((prev) => [...prev, { id, message, type }]);
      setTimeout(() => closeToast(id), type === 'error' ? 8000 : 3600);
    },
    [closeToast]
  );

  // Un oggetto nuovo a ogni render ridisegnava ogni pagina a ogni avviso.
  const ctx = useMemo(() => ({ addToast }), [addToast]);

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
        {/* Il login non naviga: nell'app ci pensa la rotta `*`, ma qui non ci sono
            rotte e l'onboarding restava sull'indirizzo `/login`. */}
        {pathname === '/login' && <Navigate to="/" replace />}
        <Suspense fallback={<div className="spinner" />}>
          <OnboardingPage />
        </Suspense>
        <Toast toasts={toasts} onClose={closeToast} />
      </AppContext.Provider>
    );
  }

  // Il dettaglio del pasto la barra in fondo ce l'ha già — «l'ho seguito», «ho
  // mangiato altro» e la chat — e due barre impilate sono centotrenta pixel di
  // comandi sopra la piega. Lì le schede si tolgono di mezzo: da quella schermata si
  // torna indietro col tondo sulla fascia del piatto.
  const senzaSchede = pathname.startsWith('/meals/');

  // Due nomi per voce: quello intero per il menu del desktop, quello corto per la
  // stecca di icone, dove sotto l'icona ci stanno sei lettere. Non sono due menu
  // diversi — è la stessa voce, con l'etichetta che si accorcia.
  const navLinks = [
    { to: '/', icon: LayoutDashboard, label: 'Oggi', short: 'Oggi', end: true },
    { to: '/plan', icon: CalendarDays, label: 'Settimana', short: 'Sett.' },
    { to: '/shopping', icon: ShoppingCart, label: 'Spesa', short: 'Spesa' },
    // La dispensa sta accanto alla spesa perché ne è l'altra metà: la lista è quello
    // che manca, la dispensa quello che c'è già — e la seconda si sottrae dalla prima.
    { to: '/pantry', icon: Refrigerator, label: 'Dispensa', short: 'Disp.' },
    { to: '/recipes', icon: ChefHat, label: 'Ricettario', short: 'Ricette' },
    { to: '/tracking', icon: TrendingUp, label: 'Andamento', short: 'Trend' },
  ];

  // Le schede del telefono sono cinque e non otto: quattro sono i posti in cui si
  // sta — cosa mangio, la settimana, la spesa, il ricettario — e la quinta raccoglie
  // tutto il resto in una pagina sua. Non è la stessa cosa del menu qui sopra, e non
  // si può ricavare da quello: un cassetto può permettersi otto voci, cinque schede
  // larghe 78px no.
  const schede = [
    { to: '/', icon: LayoutDashboard, label: 'Oggi', end: true },
    { to: '/plan', icon: CalendarDays, label: 'Settimana' },
    { to: '/shopping', icon: ShoppingCart, label: 'Spesa' },
    { to: '/recipes', icon: ChefHat, label: 'Ricette' },
    { to: '/altro', icon: Ellipsis, label: 'Altro' },
  ];

  return (
    <AppContext.Provider value={ctx}>
      <div className="app-layout">
        {/* Da tastiera il primo Tab porta qui: senza, per arrivare alla pagina si
            attraversava tutta la navigazione a ogni cambio di schermata. */}
        <a className="skip-link" href="#contenuto">
          Vai al contenuto
        </a>
        {/* La stecca di icone è del monitor: sul telefono si nasconde e al suo
            posto ci sono le schede in fondo. Prima qui c'era un cassetto che entrava
            da sinistra, aperto da un pulsante in una barra in alto: due elementi
            fermi per arrivare dove adesso si arriva con un pollice. */}
        <nav className="sidebar" aria-label="Navigazione principale">
          <div className="sidebar-logo">
            <Sprout />
            <span>DietAI</span>
          </div>

          <div className="sidebar-nav">
            {navLinks.map(({ to, icon: Icon, label, short, end }) => (
              <NavLink
                key={to}
                to={to}
                end={end}
                title={label}
                className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}
              >
                <Icon />
                <span className="sidebar-label">{label}</span>
                <span className="sidebar-short">{short}</span>
              </NavLink>
            ))}

            {/* Quello che si imposta una volta sta in fondo, staccato: nella stecca
                lo separa lo spazio vuoto invece del titoletto «Configurazione», che
                sarebbe una parola più larga della stecca. */}
            <div className="sidebar-config">
              <div className="sidebar-section">Configurazione</div>
              <NavLink
                to="/diet"
                title="La mia dieta"
                className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}
              >
                <Salad />
                <span className="sidebar-label">La mia dieta</span>
                <span className="sidebar-short">Dieta</span>
              </NavLink>
              {/* Le impostazioni sono più di una scheda: la voce punta alla pagina, non
                  a una scheda in particolare, o le due voci del menu si accenderebbero
                  a vicenda a seconda di dove sei dentro. */}
              <NavLink
                to="/settings"
                title="Impostazioni"
                className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}
              >
                <Settings />
                <span className="sidebar-label">Impostazioni</span>
                <span className="sidebar-short">Setup</span>
              </NavLink>
            </div>
          </div>

          <div className="sidebar-footer">
            <div className="sidebar-user">
              <span className="sidebar-username" title={user.email}>
                {user.email}
              </span>
              <ThemeToggle />
              <button className="icon-button danger" onClick={logout} title={`Esci (${user.email})`}>
                <LogOut size={16} />
              </button>
            </div>
          </div>
        </nav>

        <main
          id="contenuto"
          tabIndex={-1}
          className={`main-content ${senzaSchede ? 'senza-schede' : ''}`}
        >
          {/* Un errore in una pagina non deve spegnere l'app: senza questa rete
              resterebbe una finestra vuota, nera col tema scuro, e sul telefono
              nemmeno un modo per capire cosa sia successo. */}
          <ErrorBoundary resetKey={pathname}>
            <Suspense fallback={<div className="spinner" />}>
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
              {/* La quinta scheda del telefono: tutto quello che non sta nelle
                  quattro. Sul monitor non c'è una voce che ci porti — quelle cose
                  sono già nella stecca — ma la rotta vale lo stesso, ed è solo un
                  elenco di collegamenti. */}
              <Route path="/altro" element={<AltroPage />} />
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
            </Suspense>
          </ErrorBoundary>
        </main>

        {/* Le schede stanno in fondo, dove arriva il pollice. Renderizzate sempre e
            nascoste dal foglio di stile sopra i 769px: sul monitor il loro posto ce
            l'ha già la stecca di icone a sinistra. */}
        {!senzaSchede && (
          <nav className="tabbar" aria-label="Schede">
            {schede.map(({ to, icon: Icon, label, end }) => (
              <NavLink
                key={to}
                to={to}
                end={end}
                className={({ isActive }) => `tab ${isActive ? 'active' : ''}`}
              >
                <Icon />
                <span>{label}</span>
              </NavLink>
            ))}
          </nav>
        )}
      </div>

      <Toast toasts={toasts} onClose={closeToast} />
    </AppContext.Provider>
  );
}
