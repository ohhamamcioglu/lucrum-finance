import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ConfirmDialog from './ConfirmDialog';

// ConfirmDialog, pozisyon/borç/hesap silme akışlarının hepsinde kullanılan tek
// onay bileşeni — tek tıkla kalıcı veri kaybını önleyen risk kontrolü burada.

describe('ConfirmDialog', () => {
  it('renders nothing when closed', () => {
    render(
      <ConfirmDialog
        open={false}
        title="Emin misiniz?"
        message="Bu işlem geri alınamaz."
        confirmLabel="Sil"
        cancelLabel="Vazgeç"
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />
    );
    expect(screen.queryByText('Emin misiniz?')).not.toBeInTheDocument();
  });

  it('renders title and message when open', () => {
    render(
      <ConfirmDialog
        open={true}
        title="Emin misiniz?"
        message="Bu pozisyon kalıcı olarak silinecek."
        confirmLabel="Sil"
        cancelLabel="Vazgeç"
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />
    );
    expect(screen.getByText('Emin misiniz?')).toBeInTheDocument();
    expect(screen.getByText('Bu pozisyon kalıcı olarak silinecek.')).toBeInTheDocument();
  });

  it('calls onConfirm when the confirm button is clicked', async () => {
    const onConfirm = vi.fn();
    const user = userEvent.setup();
    render(
      <ConfirmDialog
        open={true}
        title="Emin misiniz?"
        message="msg"
        confirmLabel="Sil"
        cancelLabel="Vazgeç"
        onConfirm={onConfirm}
        onCancel={vi.fn()}
      />
    );
    await user.click(screen.getByText('Sil'));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it('calls onCancel when the cancel button is clicked, not onConfirm', async () => {
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    const user = userEvent.setup();
    render(
      <ConfirmDialog
        open={true}
        title="Emin misiniz?"
        message="msg"
        confirmLabel="Sil"
        cancelLabel="Vazgeç"
        onConfirm={onConfirm}
        onCancel={onCancel}
      />
    );
    await user.click(screen.getByText('Vazgeç'));
    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it('calls onCancel when the backdrop is clicked', async () => {
    const onCancel = vi.fn();
    const user = userEvent.setup();
    const { container } = render(
      <ConfirmDialog
        open={true}
        title="Emin misiniz?"
        message="msg"
        confirmLabel="Sil"
        cancelLabel="Vazgeç"
        onConfirm={vi.fn()}
        onCancel={onCancel}
      />
    );
    // Backdrop: dış sarmalayıcı div (fixed inset-0 ...) — onCancel'a bağlı
    const backdrop = container.querySelector('.fixed.inset-0') as HTMLElement;
    await user.click(backdrop);
    expect(onCancel).toHaveBeenCalledTimes(1);
  });
});
