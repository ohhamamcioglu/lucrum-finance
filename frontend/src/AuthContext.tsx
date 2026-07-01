import { createContext, useContext, useEffect, useState, ReactNode } from 'react';
import { api } from './services/api';

interface AuthContextValue {
  token: string | null;
  setToken: (token: string | null) => void;
  authChecked: boolean;
  isAdmin: boolean;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setTokenState] = useState<string | null>(() => localStorage.getItem('lucrum_auth_token'));
  const [authChecked, setAuthChecked] = useState(false);
  const [isAdmin, setIsAdmin] = useState(false);

  const setToken = (next: string | null) => {
    if (next) {
      localStorage.setItem('lucrum_auth_token', next);
    } else {
      localStorage.removeItem('lucrum_auth_token');
    }
    setTokenState(next);
  };

  // Mount: httpOnly refresh cookie üzerinden oturumu sessizce doğrula.
  useEffect(() => {
    api.tryRestoreSession()
      .then((restoredToken) => {
        setTokenState((prev) => {
          if (prev) return prev; // Bu sırada kullanıcı zaten manuel giriş yaptıysa dokunma
          if (restoredToken) {
            localStorage.setItem('lucrum_auth_token', restoredToken);
            return restoredToken;
          }
          localStorage.removeItem('lucrum_auth_token');
          return null;
        });
      })
      .finally(() => setAuthChecked(true));
  }, []);

  // Token değiştikçe is_admin bayrağını profile'dan tazele
  useEffect(() => {
    if (!token) {
      setIsAdmin(false);
      return;
    }
    let cancelled = false;
    api.getUserProfile()
      .then((profile) => {
        if (!cancelled) setIsAdmin(!!profile.is_admin);
      })
      .catch(() => {
        if (!cancelled) setIsAdmin(false);
      });
    return () => { cancelled = true; };
  }, [token]);

  return (
    <AuthContext.Provider value={{ token, setToken, authChecked, isAdmin }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth, AuthProvider içinde kullanılmalı');
  return ctx;
}
