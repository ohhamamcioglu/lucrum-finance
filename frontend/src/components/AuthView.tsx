import React, { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Mail, Lock, User, Loader2, TrendingUp, AlertCircle, CheckCircle } from 'lucide-react';
import { api } from '../services/api';

const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID || '';

// Kayıt formunda şifre gücü için anlık geri bildirim yoktu — kullanıcı zayıf bir şifre
// girdiğini ancak submit ettikten sonra (backend min_length=8 hatasıyla) öğreniyordu.
function passwordStrength(pw: string): { score: 0 | 1 | 2 | 3 | 4; label: { tr: string; en: string } } {
  let score = 0;
  if (pw.length >= 8) score++;
  if (pw.length >= 12) score++;
  if (/[A-Z]/.test(pw) && /[a-z]/.test(pw)) score++;
  if (/[0-9]/.test(pw) && /[^A-Za-z0-9]/.test(pw)) score++;
  const labels: { tr: string; en: string }[] = [
    { tr: 'Çok zayıf', en: 'Very weak' },
    { tr: 'Zayıf', en: 'Weak' },
    { tr: 'Orta', en: 'Fair' },
    { tr: 'İyi', en: 'Good' },
    { tr: 'Güçlü', en: 'Strong' },
  ];
  return { score: score as 0 | 1 | 2 | 3 | 4, label: labels[score] };
}

interface AuthViewProps {
  onAuthSuccess: (token: string) => void;
  initialMode?: 'login' | 'register';
}

export default function AuthView({ onAuthSuccess, initialMode = 'login' }: AuthViewProps) {
  const [mode, setMode] = useState<'login' | 'register' | 'forgot'>(initialMode);
  const isLogin = mode === 'login';
  const [email, setEmail] = useState('');
  const [name, setName] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [successMsg, setSuccessMsg] = useState('');
  const [lang, setLang] = useState<'tr' | 'en'>('tr');
  const googleBtnRef = useRef<HTMLDivElement>(null);

  const handleGoogleCredential = async (response: { credential: string }) => {
    setLoading(true);
    setError('');
    try {
      const data = await api.googleLogin(response.credential);
      localStorage.setItem('lucrum_auth_token', data.access_token);
      onAuthSuccess(data.access_token);
    } catch (err: any) {
      setError(err?.message || (lang === 'tr' ? 'Google ile giriş başarısız.' : 'Google sign-in failed.'));
      setLoading(false);
    }
  };

  // Google Identity Services script'ini yükle ve butonu render et (login/register sekmelerinde).
  useEffect(() => {
    if (!GOOGLE_CLIENT_ID || mode === 'forgot' || !googleBtnRef.current) return;

    const renderButton = () => {
      if (!(window as any).google || !googleBtnRef.current) return;
      (window as any).google.accounts.id.initialize({
        client_id: GOOGLE_CLIENT_ID,
        callback: handleGoogleCredential,
      });
      googleBtnRef.current.innerHTML = '';
      (window as any).google.accounts.id.renderButton(googleBtnRef.current, {
        theme: 'outline', size: 'large', width: 360, text: 'continue_with', locale: lang,
      });
    };

    const existing = document.getElementById('google-identity-script');
    if (existing) {
      renderButton();
      return;
    }
    const script = document.createElement('script');
    script.id = 'google-identity-script';
    script.src = 'https://accounts.google.com/gsi/client';
    script.async = true;
    script.defer = true;
    script.onload = renderButton;
    document.body.appendChild(script);
  }, [mode, lang]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    setSuccessMsg('');

    try {
      if (mode === 'forgot') {
        const res = await api.forgotPassword(email);
        setSuccessMsg(res.message);
      } else if (mode === 'login') {
        const data = await api.login(email, password);
        localStorage.setItem('lucrum_auth_token', data.access_token);
        onAuthSuccess(data.access_token);
      } else {
        if (!name.trim()) {
          throw new Error(lang === 'tr' ? 'Lütfen adınızı girin.' : 'Please enter your name.');
        }
        const data = await api.register(email, name, password);
        setSuccessMsg(lang === 'tr' ? 'Kayıt başarılı! Giriş yapılıyor...' : 'Registration successful! Logging in...');

        // Wait a second for success visual feedback, then proceed
        setTimeout(() => {
          localStorage.setItem('lucrum_auth_token', data.access_token);
          onAuthSuccess(data.access_token);
        }, 1200);
      }
    } catch (err: any) {
      setError(err?.message || (lang === 'tr' ? 'Bir hata oluştu.' : 'An error occurred.'));
    } finally {
      if (mode !== 'register') setLoading(false);
    }
  };

  const texts = {
    tr: {
      title: 'LUCRUM',
      subtitle: 'Kurumsal Portföy ve Analiz Platformu',
      loginTab: 'Giriş Yap',
      registerTab: 'Kayıt Ol',
      nameLabel: 'Ad Soyad',
      emailLabel: 'E-posta Adresi',
      passwordLabel: 'Şifre',
      loginBtn: 'Giriş Yap',
      registerBtn: 'Kayıt Ol',
      loggingIn: 'Giriş yapılıyor...',
      registering: 'Kayıt ediliyor...',
      demoAccount: 'Demo Giriş Bilgileri:',
      demoCreds: 'E-posta: demo@lucrum.finance / Şifre: demo123',
    },
    en: {
      title: 'LUCRUM',
      subtitle: 'Institutional Portfolio & Analytics Platform',
      loginTab: 'Login',
      registerTab: 'Register',
      nameLabel: 'Full Name',
      emailLabel: 'Email Address',
      passwordLabel: 'Password',
      loginBtn: 'Login',
      registerBtn: 'Register',
      loggingIn: 'Logging in...',
      registering: 'Registering...',
      demoAccount: 'Demo Credentials:',
      demoCreds: 'Email: demo@lucrum.finance / Password: demo123',
    }
  };

  const t = texts[lang];

  return (
    <div className="min-h-screen w-full flex items-center justify-center bg-[#F9F7F2] relative overflow-hidden font-sans">
      {/* Premium Background Graphics / Abstract Shapes */}
      <div className="absolute top-[-20%] left-[-10%] w-[500px] h-[500px] rounded-full bg-[#8C9A86]/20 blur-[120px] pointer-events-none" />
      <div className="absolute bottom-[-20%] right-[-10%] w-[600px] h-[600px] rounded-full bg-[#9E958C]/20 blur-[150px] pointer-events-none" />
      <div className="absolute top-[40%] right-[10%] w-[300px] h-[300px] rounded-full bg-[#8C9A86]/10 blur-[80px] pointer-events-none" />

      {/* Language Toggle */}
      <div className="absolute top-6 right-8 z-10 flex gap-2">
        <button
          onClick={() => setLang('tr')}
          className={`px-3 py-1 text-xs font-semibold rounded-md border transition-all cursor-pointer ${
            lang === 'tr'
              ? 'bg-[#8C9A86] text-white border-[#8C9A86]'
              : 'text-[#4A443F] border-[#4A443F]/20 hover:bg-[#8C9A86]/10'
          }`}
        >
          TR
        </button>
        <button
          onClick={() => setLang('en')}
          className={`px-3 py-1 text-xs font-semibold rounded-md border transition-all cursor-pointer ${
            lang === 'en'
              ? 'bg-[#8C9A86] text-white border-[#8C9A86]'
              : 'text-[#4A443F] border-[#4A443F]/20 hover:bg-[#8C9A86]/10'
          }`}
        >
          EN
        </button>
      </div>

      <div className="w-full max-w-md p-8 m-4 bg-[#FAF8F5]/85 backdrop-blur-md border border-[#8C9A86]/20 shadow-2xl rounded-2xl z-10 flex flex-col items-center">
        {/* Brand / Logo */}
        <div className="flex items-center gap-3 mb-2">
          <div className="w-10 h-10 rounded-xl bg-[#8C9A86] flex items-center justify-center shadow-lg shadow-[#8C9A86]/30">
            <TrendingUp className="w-6 h-6 text-white" />
          </div>
          <span className="text-2xl font-black tracking-widest text-[#4A443F] font-serif">{t.title}</span>
        </div>
        <p className="text-xs text-[#9E958C] font-semibold tracking-wider text-center uppercase mb-8">{t.subtitle}</p>

        {/* Tab Selection */}
        {mode !== 'forgot' && (
          <div className="flex w-full bg-[#F2EDE4] p-1 rounded-xl mb-6 border border-[#8C9A86]/10">
            <button
              type="button"
              onClick={() => { setMode('login'); setError(''); }}
              className={`flex-1 py-2 text-xs font-bold uppercase tracking-wider rounded-lg transition-all cursor-pointer ${
                isLogin
                  ? 'bg-white text-[#4A443F] shadow-sm'
                  : 'text-[#9E958C] hover:text-[#4A443F]'
              }`}
            >
              {t.loginTab}
            </button>
            <button
              type="button"
              onClick={() => { setMode('register'); setError(''); }}
              className={`flex-1 py-2 text-xs font-bold uppercase tracking-wider rounded-lg transition-all cursor-pointer ${
                mode === 'register'
                  ? 'bg-white text-[#4A443F] shadow-sm'
                  : 'text-[#9E958C] hover:text-[#4A443F]'
              }`}
            >
              {t.registerTab}
            </button>
          </div>
        )}

        {mode !== 'forgot' && GOOGLE_CLIENT_ID && (
          <div className="w-full mb-6">
            <div ref={googleBtnRef} className="w-full flex justify-center" />
            <div className="flex items-center gap-3 mt-5">
              <div className="h-px flex-1 bg-[#8C9A86]/20" />
              <span className="text-[10px] text-[#9E958C] font-bold uppercase tracking-wider">
                {lang === 'tr' ? 'veya' : 'or'}
              </span>
              <div className="h-px flex-1 bg-[#8C9A86]/20" />
            </div>
          </div>
        )}

        {mode === 'forgot' && (
          <p className="text-xs text-[#4A443F] text-center mb-6">
            {lang === 'tr' ? 'E-posta adresinize şifre sıfırlama bağlantısı gönderelim.' : "We'll send a password reset link to your email."}
          </p>
        )}

        {/* Form */}
        <form onSubmit={handleSubmit} className="w-full space-y-4">
          <AnimatePresence mode="wait">
            {mode === 'register' && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                exit={{ opacity: 0, height: 0 }}
                transition={{ duration: 0.2 }}
                className="space-y-1"
              >
                <label className="text-xs font-bold text-[#4A443F] uppercase tracking-wider block ml-1">
                  {t.nameLabel}
                </label>
                <div className="relative">
                  <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#9E958C]" />
                  <input
                    type="text"
                    required={mode === 'register'}
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="John Doe"
                    className="w-full pl-10 pr-4 py-2.5 bg-[#F2EDE4]/40 border border-[#8C9A86]/20 focus:border-[#8C9A86] focus:bg-white rounded-xl text-sm text-[#4A443F] outline-none transition-all"
                  />
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          <div className="space-y-1">
            <label className="text-xs font-bold text-[#4A443F] uppercase tracking-wider block ml-1">
              {t.emailLabel}
            </label>
            <div className="relative">
              <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#9E958C]" />
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="example@domain.com"
                className="w-full pl-10 pr-4 py-2.5 bg-[#F2EDE4]/40 border border-[#8C9A86]/20 focus:border-[#8C9A86] focus:bg-white rounded-xl text-sm text-[#4A443F] outline-none transition-all"
              />
            </div>
          </div>

          {mode !== 'forgot' && (
            <div className="space-y-1">
              <div className="flex items-center justify-between ml-1">
                <label className="text-xs font-bold text-[#4A443F] uppercase tracking-wider block">
                  {t.passwordLabel}
                </label>
                {isLogin && (
                  <button
                    type="button"
                    onClick={() => { setMode('forgot'); setError(''); setSuccessMsg(''); }}
                    className="text-[10px] text-[#8C9A86] hover:text-[#4A443F] font-semibold cursor-pointer"
                  >
                    {lang === 'tr' ? 'Şifremi unuttum' : 'Forgot password?'}
                  </button>
                )}
              </div>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#9E958C]" />
                <input
                  type="password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  className="w-full pl-10 pr-4 py-2.5 bg-[#F2EDE4]/40 border border-[#8C9A86]/20 focus:border-[#8C9A86] focus:bg-white rounded-xl text-sm text-[#4A443F] outline-none transition-all"
                />
              </div>
              {mode === 'register' && password.length > 0 && (() => {
                const { score, label } = passwordStrength(password);
                const colors = ['#B5836F', '#B5836F', '#D1A86A', '#8C9A86', '#7A8874'];
                return (
                  <div className="pt-1">
                    <div className="flex gap-1 h-1">
                      {[0, 1, 2, 3].map(i => (
                        <div key={i} className="flex-1 rounded-full bg-[#E8E2D9] overflow-hidden">
                          <div
                            className="h-full rounded-full transition-all"
                            style={{ width: i < score ? '100%' : '0%', backgroundColor: colors[score] }}
                          />
                        </div>
                      ))}
                    </div>
                    <span className="text-[10px] font-semibold mt-1 block" style={{ color: colors[score] }}>
                      {lang === 'tr' ? label.tr : label.en}
                    </span>
                  </div>
                );
              })()}
            </div>
          )}

          {/* Feedback alerts */}
          {error && (
            <motion.div
              initial={{ opacity: 0, y: -5 }}
              animate={{ opacity: 1, y: 0 }}
              className="flex items-center gap-2 p-3 bg-red-50 border border-red-200 text-red-700 rounded-xl text-xs"
            >
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span>{error}</span>
            </motion.div>
          )}

          {successMsg && (
            <motion.div
              initial={{ opacity: 0, y: -5 }}
              animate={{ opacity: 1, y: 0 }}
              className="flex items-center gap-2 p-3 bg-green-50 border border-green-200 text-green-700 rounded-xl text-xs"
            >
              <CheckCircle className="w-4 h-4 shrink-0" />
              <span>{successMsg}</span>
            </motion.div>
          )}

          {/* Submit Button */}
          <button
            type="submit"
            disabled={loading}
            className="w-full py-3 bg-[#8C9A86] hover:bg-[#7A8875] disabled:bg-[#8C9A86]/60 text-white font-bold text-xs uppercase tracking-wider rounded-xl shadow-lg shadow-[#8C9A86]/20 transition-all flex items-center justify-center gap-2 mt-4 cursor-pointer"
          >
            {loading ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : null}
            <span>
              {mode === 'forgot'
                ? (loading ? (lang === 'tr' ? 'Gönderiliyor...' : 'Sending...') : (lang === 'tr' ? 'Sıfırlama Bağlantısı Gönder' : 'Send Reset Link'))
                : (loading ? (isLogin ? t.loggingIn : t.registering) : (isLogin ? t.loginBtn : t.registerBtn))}
            </span>
          </button>

          {mode === 'forgot' && (
            <button
              type="button"
              onClick={() => { setMode('login'); setError(''); setSuccessMsg(''); }}
              className="w-full text-center text-xs text-[#9E958C] hover:text-[#4A443F] font-semibold cursor-pointer"
            >
              {lang === 'tr' ? 'Giriş sayfasına dön' : 'Back to login'}
            </button>
          )}
        </form>

        {/* Demo Credential Note */}
        {isLogin && (
          <div className="w-full mt-8 p-3 bg-[#F2EDE4]/65 border border-[#8C9A86]/10 rounded-xl text-[10px] text-[#9E958C] font-semibold text-center">
            <span className="block text-[#4A443F] font-bold mb-1">{t.demoAccount}</span>
            <span>{t.demoCreds}</span>
          </div>
        )}
      </div>
    </div>
  );
}
