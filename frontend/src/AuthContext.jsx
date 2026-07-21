import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { api, setSessionExpiredHandler } from './api';

const AuthContext = createContext();
export const useAuth = () => useContext(AuthContext);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  // `loading` evita il lampo della pagina di login a ogni ricarica: i cookie sono
  // httpOnly, quindi l'unico modo di sapere se la sessione è viva è chiederlo al server.
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setSessionExpiredHandler(() => setUser(null));

    api.me()
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setLoading(false));
  }, []);

  const login = useCallback(async (email, password) => {
    const u = await api.login(email, password);
    setUser(u);
    return u;
  }, []);

  const logout = useCallback(async () => {
    // Anche se la chiamata fallisce l'utente esce comunque dal client: restare
    // "dentro" dopo aver premuto Esci sarebbe peggio di una revoca mancata.
    try {
      await api.logout();
    } finally {
      setUser(null);
    }
  }, []);

  // Rilegge il profilo: serve dopo l'onboarding, quando has_api_key e
  // has_active_diet cambiano e decidono cosa mostrare.
  const refreshUser = useCallback(async () => {
    const u = await api.me();
    setUser(u);
    return u;
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
}
