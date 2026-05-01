// Faz 6 KM1 alt-iş g f-polish-3 — küçük bilgi mesajları için toast.
// Tek module-level element; üst üste çağrılarda mesaj güncellenir,
// timer reset'lenir.

let toastEl: HTMLElement | null = null;
let toastTimeout: ReturnType<typeof setTimeout> | null = null;

const DEFAULT_DURATION_MS = 3000;

export function showToast(message: string, durationMs = DEFAULT_DURATION_MS): HTMLElement {
  if (!toastEl) {
    toastEl = document.createElement('div');
    toastEl.className = 'toast';
    document.body.appendChild(toastEl);
  }
  toastEl.textContent = message;
  toastEl.dataset.visible = 'true';

  if (toastTimeout) clearTimeout(toastTimeout);
  toastTimeout = setTimeout(() => {
    if (toastEl) toastEl.dataset.visible = 'false';
    toastTimeout = null;
  }, durationMs);

  return toastEl;
}

// Test'te DOM temizlemek için.
export function _resetToastForTests(): void {
  if (toastTimeout) {
    clearTimeout(toastTimeout);
    toastTimeout = null;
  }
  if (toastEl) {
    toastEl.remove();
    toastEl = null;
  }
}
