import { useState, FormEvent } from 'react';
import { X, Loader2 } from 'lucide-react';
import { useT } from '../i18n';
import type { Language } from '../i18n';

export interface IyzicoBuyerInfo {
  identity_number: string;
  phone: string;
  address: string;
  city: string;
  country: string;
}

interface IyzicoBuyerModalProps {
  lang: Language;
  submitting: boolean;
  onCancel: () => void;
  onSubmit: (buyer: IyzicoBuyerInfo) => void;
}

export default function IyzicoBuyerModal({ lang, submitting, onCancel, onSubmit }: IyzicoBuyerModalProps) {
  const t = useT(lang);
  const [identityNumber, setIdentityNumber] = useState('');
  const [phone, setPhone] = useState('');
  const [address, setAddress] = useState('');
  const [city, setCity] = useState('');
  const [country, setCountry] = useState('Türkiye');
  const [error, setError] = useState('');

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    setError('');

    if (!/^\d{11}$/.test(identityNumber)) {
      setError(t.iyzicoIdentityInvalid);
      return;
    }
    if (!phone.trim() || !address.trim() || !city.trim() || !country.trim()) {
      setError(t.iyzicoFieldRequired);
      return;
    }

    onSubmit({ identity_number: identityNumber, phone, address, city, country });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-md bg-white rounded-2xl shadow-2xl p-6 relative">
        <button
          onClick={onCancel}
          className="absolute top-4 right-4 text-[#9E958C] hover:text-[#4A443F] cursor-pointer"
        >
          <X className="w-5 h-5" />
        </button>

        <h2 className="text-base font-bold text-[#4A443F] mb-1">{t.iyzicoModalTitle}</h2>
        <p className="text-xs text-[#9E958C] mb-6">{t.iyzicoModalSubtitle}</p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1">
            <label className="text-xs font-bold text-[#4A443F] uppercase tracking-wider block">
              {t.iyzicoIdentityNumber}
            </label>
            <input
              type="text"
              inputMode="numeric"
              maxLength={11}
              value={identityNumber}
              onChange={(e) => setIdentityNumber(e.target.value.replace(/\D/g, ''))}
              placeholder="12345678901"
              className="w-full px-3 py-2.5 bg-[#F2EDE4]/40 border border-[#8C9A86]/20 focus:border-[#8C9A86] rounded-xl text-sm outline-none transition-all"
            />
          </div>

          <div className="space-y-1">
            <label className="text-xs font-bold text-[#4A443F] uppercase tracking-wider block">
              {t.iyzicoPhone}
            </label>
            <input
              type="tel"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="5XXXXXXXXX"
              className="w-full px-3 py-2.5 bg-[#F2EDE4]/40 border border-[#8C9A86]/20 focus:border-[#8C9A86] rounded-xl text-sm outline-none transition-all"
            />
          </div>

          <div className="space-y-1">
            <label className="text-xs font-bold text-[#4A443F] uppercase tracking-wider block">
              {t.iyzicoAddress}
            </label>
            <input
              type="text"
              value={address}
              onChange={(e) => setAddress(e.target.value)}
              className="w-full px-3 py-2.5 bg-[#F2EDE4]/40 border border-[#8C9A86]/20 focus:border-[#8C9A86] rounded-xl text-sm outline-none transition-all"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className="text-xs font-bold text-[#4A443F] uppercase tracking-wider block">
                {t.iyzicoCity}
              </label>
              <input
                type="text"
                value={city}
                onChange={(e) => setCity(e.target.value)}
                className="w-full px-3 py-2.5 bg-[#F2EDE4]/40 border border-[#8C9A86]/20 focus:border-[#8C9A86] rounded-xl text-sm outline-none transition-all"
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-bold text-[#4A443F] uppercase tracking-wider block">
                {t.iyzicoCountry}
              </label>
              <input
                type="text"
                value={country}
                onChange={(e) => setCountry(e.target.value)}
                className="w-full px-3 py-2.5 bg-[#F2EDE4]/40 border border-[#8C9A86]/20 focus:border-[#8C9A86] rounded-xl text-sm outline-none transition-all"
              />
            </div>
          </div>

          {error && (
            <p className="text-xs text-red-600 font-semibold">{error}</p>
          )}

          <div className="flex gap-3 pt-2">
            <button
              type="button"
              onClick={onCancel}
              className="flex-1 py-2.5 rounded-xl border border-[#8C9A86]/20 text-xs font-bold uppercase tracking-wider text-[#4A443F] cursor-pointer"
            >
              {t.iyzicoCancel}
            </button>
            <button
              type="submit"
              disabled={submitting}
              className="flex-1 py-2.5 rounded-xl bg-[#8C9A86] hover:bg-[#7A8875] disabled:bg-[#8C9A86]/60 text-white text-xs font-bold uppercase tracking-wider cursor-pointer flex items-center justify-center gap-2"
            >
              {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
              {t.iyzicoContinue}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
