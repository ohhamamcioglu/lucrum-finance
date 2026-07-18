import { AnimatePresence, motion } from 'motion/react';
import { AlertCircle } from 'lucide-react';

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  message: string;
  confirmLabel: string;
  cancelLabel: string;
  onConfirm: () => void;
  onCancel: () => void;
}

// Markaya uygun, stilize edilebilir onay modalı — native window.confirm() yerine kullanılır.
// window.confirm() hem markaya uymuyordu hem de otomatik tarayıcı testlerinde (CDP) tüm
// sekmeyi donduruyordu; ayrıca Pozisyon silme hiçbir onay istemiyordu (tek tıkla kalıcı
// veri kaybı riski) — bu bileşen her iki sorunu da tek yerden çözer.
export default function ConfirmDialog({ open, title, message, confirmLabel, cancelLabel, onConfirm, onCancel }: ConfirmDialogProps) {
  return (
    <AnimatePresence>
      {open && (
        <div className="fixed inset-0 bg-[#2D2926]/40 backdrop-blur-md z-[100] flex items-center justify-center p-4" onClick={onCancel}>
          <motion.div
            initial={{ scale: 0.95, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.95, opacity: 0 }}
            onClick={(e) => e.stopPropagation()}
            className="bg-[#F9F7F2] border border-[#E8E2D9] rounded-2xl shadow-2xl w-full max-w-sm overflow-hidden"
          >
            <div className="p-6">
              <div className="w-10 h-10 rounded-full bg-[#B5836F]/10 flex items-center justify-center mb-4">
                <AlertCircle className="w-5 h-5 text-[#B5836F]" />
              </div>
              <h3 className="font-serif text-lg font-bold text-[#2D2926] mb-1.5">{title}</h3>
              <p className="text-sm text-[#6B645E]">{message}</p>
            </div>
            <div className="flex border-t border-[#E8E2D9]">
              <button
                type="button"
                onClick={onCancel}
                className="flex-1 py-3.5 text-sm font-bold text-[#6B645E] hover:bg-[#F1EFE9] transition-colors"
              >
                {cancelLabel}
              </button>
              <button
                type="button"
                onClick={onConfirm}
                className="flex-1 py-3.5 text-sm font-bold text-white bg-[#B5836F] hover:bg-[#A3735F] transition-colors"
              >
                {confirmLabel}
              </button>
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}
