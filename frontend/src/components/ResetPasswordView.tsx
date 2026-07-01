import React, { useState } from 'react';
import { motion } from 'motion/react';
import { Lock, Loader2, TrendingUp, AlertCircle, CheckCircle } from 'lucide-react';
import { api } from '../services/api';

interface ResetPasswordViewProps {
  token: string;
  onDone: () => void;
}

export default function ResetPasswordView({ token, onDone }: ResetPasswordViewProps) {
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [successMsg, setSuccessMsg] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (password.length < 8) {
      setError('Şifre en az 8 karakter olmalıdır.');
      return;
    }
    if (password !== confirmPassword) {
      setError('Şifreler eşleşmiyor.');
      return;
    }

    setLoading(true);
    try {
      const res = await api.resetPassword(token, password);
      setSuccessMsg(res.message || 'Şifreniz güncellendi.');
      setTimeout(onDone, 1800);
    } catch (err: any) {
      setError(err?.message || 'Bağlantı geçersiz veya süresi dolmuş olabilir.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen w-full flex items-center justify-center bg-[#F9F7F2] relative overflow-hidden font-sans">
      <div className="absolute top-[-20%] left-[-10%] w-[500px] h-[500px] rounded-full bg-[#8C9A86]/20 blur-[120px] pointer-events-none" />
      <div className="absolute bottom-[-20%] right-[-10%] w-[600px] h-[600px] rounded-full bg-[#9E958C]/20 blur-[150px] pointer-events-none" />

      <div className="w-full max-w-md p-8 m-4 bg-[#FAF8F5]/85 backdrop-blur-md border border-[#8C9A86]/20 shadow-2xl rounded-2xl z-10 flex flex-col items-center">
        <div className="flex items-center gap-3 mb-2">
          <div className="w-10 h-10 rounded-xl bg-[#8C9A86] flex items-center justify-center shadow-lg shadow-[#8C9A86]/30">
            <TrendingUp className="w-6 h-6 text-white" />
          </div>
          <span className="text-2xl font-black tracking-widest text-[#4A443F] font-serif">LUCRUM</span>
        </div>
        <p className="text-xs text-[#9E958C] font-semibold tracking-wider text-center uppercase mb-8">Şifre Sıfırlama</p>

        <form onSubmit={handleSubmit} className="w-full space-y-4">
          <div className="space-y-1">
            <label className="text-xs font-bold text-[#4A443F] uppercase tracking-wider block ml-1">Yeni Şifre</label>
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
          </div>

          <div className="space-y-1">
            <label className="text-xs font-bold text-[#4A443F] uppercase tracking-wider block ml-1">Yeni Şifre (Tekrar)</label>
            <div className="relative">
              <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#9E958C]" />
              <input
                type="password"
                required
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder="••••••••"
                className="w-full pl-10 pr-4 py-2.5 bg-[#F2EDE4]/40 border border-[#8C9A86]/20 focus:border-[#8C9A86] focus:bg-white rounded-xl text-sm text-[#4A443F] outline-none transition-all"
              />
            </div>
          </div>

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

          <button
            type="submit"
            disabled={loading}
            className="w-full py-3 bg-[#8C9A86] hover:bg-[#7A8875] disabled:bg-[#8C9A86]/60 text-white font-bold text-xs uppercase tracking-wider rounded-xl shadow-lg shadow-[#8C9A86]/20 transition-all flex items-center justify-center gap-2 mt-4 cursor-pointer"
          >
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
            <span>{loading ? 'Güncelleniyor...' : 'Şifreyi Güncelle'}</span>
          </button>

          <button
            type="button"
            onClick={onDone}
            className="w-full text-center text-xs text-[#9E958C] hover:text-[#4A443F] font-semibold cursor-pointer"
          >
            Giriş sayfasına dön
          </button>
        </form>
      </div>
    </div>
  );
}
