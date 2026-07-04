import { createContext, useContext, useEffect, useState, ReactNode } from 'react';
import { api } from './services/api';

interface AuthProfile {
  name: string;
  email: string;
  subscription_tier: string;
}

interface AuthContextValue {
  token: string | null;
  setToken: (token: string | null) => void;
  authChecked: boolean;
  isAdmin: boolean;
  profile: AuthProfile | null;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setTokenState] = useState<string | null>(() => localStorage.getItem('lucrum_auth_token'));
  const [authChecked, setAuthChecked] = useState(false);
  const [isAdmin, setIsAdmin] = useState(false);
  const [profile, setProfile] = useState<AuthProfile | null>(null);

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

  // Token değiştikçe is_admin bayrağını ve profil bilgisini (isim/email/plan) tazele
  useEffect(() => {
    if (!token) {
      setIsAdmin(false);
      setProfile(null);
      return;
    }
    let cancelled = false;
    api.getUserProfile()
      .then((p) => {
        if (cancelled) return;
        setIsAdmin(!!p.is_admin);
        setProfile({ name: p.name, email: p.email, subscription_tier: p.subscription_tier });
      })
      .catch(() => {
        if (!cancelled) { setIsAdmin(false); setProfile(null); }
      });
    return () => { cancelled = true; };
  }, [token]);

  return (
    <AuthContext.Provider value={{ token, setToken, authChecked, isAdmin, profile }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth, AuthProvider içinde kullanılmalı');
  return ctx;
}
