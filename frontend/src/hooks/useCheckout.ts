import { useState } from 'react';
import { api } from '../services/api';
import { IyzicoBuyerInfo } from '../components/IyzicoBuyerModal';

/**
 * Pricing sayfası ve Settings'teki abonelik kartında ortak checkout mantığı:
 * Stripe doğrudan yönlendirir, iyzico önce buyer bilgisi modalını açar.
 */
export function useCheckout() {
  const [iyzicoPlan, setIyzicoPlan] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const startStripeCheckout = async (plan: string) => {
    setError(null);
    setSubmitting(true);
    try {
      const res = await api.createStripeCheckout(plan);
      window.location.href = res.checkout_url;
    } catch (err: any) {
      setSubmitting(false);
      setError(err?.message || null);
    }
  };

  const startIyzicoCheckout = (plan: string) => {
    setError(null);
    setIyzicoPlan(plan);
  };

  const cancelIyzicoModal = () => {
    setIyzicoPlan(null);
  };

  const submitIyzicoBuyer = async (buyer: IyzicoBuyerInfo) => {
    if (!iyzicoPlan) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await api.createIyzicoCheckout(iyzicoPlan, buyer);
      window.location.href = res.checkout_url;
    } catch (err: any) {
      setSubmitting(false);
      setError(err?.message || null);
    }
  };

  return {
    iyzicoPlan,
    submitting,
    error,
    startStripeCheckout,
    startIyzicoCheckout,
    cancelIyzicoModal,
    submitIyzicoBuyer,
    clearError: () => setError(null),
  };
}
