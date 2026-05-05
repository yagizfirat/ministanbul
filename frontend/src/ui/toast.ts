// Single module-level toast for small info messages; calling
// showToast() again before the previous one fades just updates the
// text and resets the dismiss timer.

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

// Test-only DOM cleanup.
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
