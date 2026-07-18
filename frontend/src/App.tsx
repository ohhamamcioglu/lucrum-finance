import { useEffect, useState, lazy, Suspense, ReactElement } from 'react';
import { Routes, Route, Navigate, useNavigate, useSearchParams } from 'react-router-dom';
import { motion } from 'motion/react';

import { AuthProvider, useAuth } from './AuthContext';
import { api } from './services/api';

// Route-level code splitting — eskiden tüm sayfalar (Admin paneli, Pricing, Legal dahil)
// tek bir ~650KB bundle'da toplanıyordu; ilk ziyaretçi hiç görmeyeceği Admin panelini bile
// indiriyordu. Her rota artık ayrı bir chunk'a ayrılıyor, ilk yüklemede sadece o an
// gidilen rotanın kodu iniyor.
const LandingPage = lazy(() => import('./components/LandingPage'));
const PricingPage = lazy(() => import('./components/PricingPage'));
const LegalPage = lazy(() => import('./components/LegalPage'));
const AuthView = lazy(() => import('./components/AuthView'));
const ResetPasswordView = lazy(() => import('./components/ResetPasswordView'));
const AdminPage = lazy(() => import('./components/AdminPage'));
const DashboardApp = lazy(() => import('./DashboardApp'));

function LoadingSpinner() {
  return (
    <div className="min-h-screen bg-[#F9F7F2] flex flex-col items-center justify-center font-sans">
      <motion.div
        animate={{ rotate: 360 }}
        transition={{ repeat: Infinity, duration: 1.2, ease: 'linear' }}
        className="w-10 h-10 border-4 border-[#8C9A86] border-t-transparent rounded-full mb-4"
      />
    </div>
  );
}

function RequireAuth({ children }: { children: ReactElement }) {
  const { token, authChecked } = useAuth();
  if (!authChecked) return <LoadingSpinner />;
  if (!token) return <Navigate to="/login" replace />;
  return children;
}

function RequireAdmin({ children }: { children: ReactElement }) {
  const { token, authChecked, isAdmin } = useAuth();
  if (!authChecked) return <LoadingSpinner />;
  if (!token) return <Navigate to="/login" replace />;
  if (!isAdmin) return <Navigate to="/" replace />;
  return children;
}

function LoginRoute() {
  const { setToken } = useAuth();
  const navigate = useNavigate();
  return <AuthView initialMode="login" onAuthSuccess={(t) => { setToken(t); navigate('/app'); }} />;
}

function RegisterRoute() {
  const { setToken } = useAuth();
  const navigate = useNavigate();
  return <AuthView initialMode="register" onAuthSuccess={(t) => { setToken(t); navigate('/app'); }} />;
}

function ResetPasswordRoute() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const token = searchParams.get('token');
  if (!token) return <Navigate to="/" replace />;
  return <ResetPasswordView token={token} onDone={() => navigate('/login')} />;
}

// Email doğrulama, ayrı bir sayfa değil — hangi route'ta olursa olsun üstte bir bant gösterir.
function VerifyEmailBanner() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [verifyMessage, setVerifyMessage] = useState<string | null>(null);

  useEffect(() => {
    const verifyParam = searchParams.get('verify-email');
    if (!verifyParam) return;
    api.verifyEmail(verifyParam)
      .then((res) => setVerifyMessage(res.message))
      .catch(() => setVerifyMessage('Doğrulama bağlantısı geçersiz veya süresi dolmuş.'));
    const next = new URLSearchParams(searchParams);
    next.delete('verify-email');
    setSearchParams(next, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!verifyMessage) return null;
  return (
    <div className="fixed top-0 left-0 right-0 z-50 bg-[#8C9A86] text-white text-xs font-semibold text-center py-2 px-4 flex items-center justify-center gap-3">
      <span>{verifyMessage}</span>
      <button onClick={() => setVerifyMessage(null)} className="underline cursor-pointer">Kapat</button>
    </div>
  );
}

function AppRoutes() {
  return (
    <>
      <VerifyEmailBanner />
      <Suspense fallback={<LoadingSpinner />}>
        <Routes>
          <Route path="/" element={<LandingPage />} />
          <Route path="/pricing" element={<PricingPage />} />
          <Route path="/legal/kvkk" element={<LegalPage contentKey="kvkk" />} />
          <Route path="/legal/terms" element={<LegalPage contentKey="terms" />} />
          <Route path="/legal/privacy" element={<LegalPage contentKey="privacy" />} />
          <Route path="/login" element={<LoginRoute />} />
          <Route path="/register" element={<RegisterRoute />} />
          <Route path="/reset-password" element={<ResetPasswordRoute />} />
          <Route path="/app" element={<RequireAuth><DashboardApp /></RequireAuth>} />
          <Route path="/admin" element={<RequireAdmin><AdminPage /></RequireAdmin>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
    </>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <AppRoutes />
    </AuthProvider>
  );
}
