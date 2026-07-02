import { useState } from 'react';
import { api } from '../services/api';

/**
 * Pricing sayfası ve Settings'teki abonelik kartında ortak checkout mantığı:
 * tek sağlayıcı (Lemon Squeezy) olduğu için doğrudan hosted checkout'a yönlendirir.
 */
export function useCheckout() {
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const startCheckout = async (plan: string) => {
    setError(null);
    setSubmitting(true);
    try {
      const res = await api.createLemonSqueezyCheckout(plan);
      window.location.href = res.checkout_url;
    } catch (err: any) {
      setSubmitting(false);
      setError(err?.message || null);
    }
  };

  return {
    submitting,
    error,
    startCheckout,
    clearError: () => setError(null),
  };
}
