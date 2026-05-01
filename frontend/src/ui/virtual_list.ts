// Faz 6 KM1 alt-iş f-4 — windowed rendering for the bus route list
// (9000+ items). Sabit yükseklikli item'lar, viewport içi + overscan
// kadar node DOM'da bulunur, gerisi spacer ile temsil edilir.
//
// Caller sözleşmesi:
//   - opts.container: position:relative, overflow:auto, fixed height
//     (CSS RoutePanel f-5'te ayarlanır)
//   - opts.itemHeight: sabit pixel; variable height yok (KM1 polish)
//   - opts.renderItem: absolute pozisyonlama bu modül uygular,
//     caller'ın inline top/left set etmesi gerekmez

const SPACER_CLASS = 'virtual-list__spacer';
const ITEM_CLASS = 'virtual-list__item';

export interface VirtualListOptions<T> {
  container: HTMLElement;
  items: T[];
  itemHeight: number;
  renderItem: (item: T, index: number) => HTMLElement;
  overscan?: number;
}

export interface VirtualListHandle<T> {
  setItems(items: T[]): void;
  scrollToIndex(index: number): void;
  destroy(): void;
}

export function createVirtualList<T>(opts: VirtualListOptions<T>): VirtualListHandle<T> {
  const overscan = opts.overscan ?? 5;
  let items = opts.items;

  const spacer = document.createElement('div');
  spacer.className = SPACER_CLASS;
  spacer.style.cssText = [
    'position: relative',
    `height: ${items.length * opts.itemHeight}px`,
    'pointer-events: none',
  ].join(';');
  opts.container.appendChild(spacer);

  const renderedNodes = new Map<number, HTMLElement>();

  function computeRange(): { start: number; end: number } {
    if (items.length === 0) return { start: 0, end: -1 };
    const scrollTop = opts.container.scrollTop;
    const viewportHeight = opts.container.clientHeight;
    const start = Math.max(0, Math.floor(scrollTop / opts.itemHeight) - overscan);
    const end = Math.min(
      items.length - 1,
      Math.ceil((scrollTop + viewportHeight) / opts.itemHeight) - 1 + overscan,
    );
    return { start, end };
  }

  function render(): void {
    const { start, end } = computeRange();
    // Çıkanları kaldır.
    for (const [idx, node] of renderedNodes) {
      if (idx < start || idx > end) {
        node.remove();
        renderedNodes.delete(idx);
      }
    }
    // Yenileri ekle (zaten render'lı olanlara dokunma).
    for (let i = start; i <= end; i++) {
      if (renderedNodes.has(i)) continue;
      const node = opts.renderItem(items[i], i);
      node.classList.add(ITEM_CLASS);
      node.style.position = 'absolute';
      node.style.top = `${i * opts.itemHeight}px`;
      node.style.left = '0';
      node.style.right = '0';
      node.style.height = `${opts.itemHeight}px`;
      opts.container.appendChild(node);
      renderedNodes.set(i, node);
    }
  }

  const onScroll = (): void => render();
  opts.container.addEventListener('scroll', onScroll);

  // İlk pencereyi doldur.
  render();

  return {
    setItems(newItems: T[]): void {
      items = newItems;
      spacer.style.height = `${items.length * opts.itemHeight}px`;
      // Tüm rendered node'ları temizle: indeks ↔ data eşleşmesi
      // değişti, hızlı yol cache invalidation.
      for (const node of renderedNodes.values()) node.remove();
      renderedNodes.clear();
      // scrollTop'u yeni bounds'a clamp'la (tarayıcı/jsdom kısa
      // listede otomatik düşürmeyebilir).
      const maxScroll = Math.max(
        0,
        items.length * opts.itemHeight - opts.container.clientHeight,
      );
      if (opts.container.scrollTop > maxScroll) {
        opts.container.scrollTop = maxScroll;
      }
      render();
    },

    scrollToIndex(index: number): void {
      opts.container.scrollTop = index * opts.itemHeight;
      render();
    },

    destroy(): void {
      opts.container.removeEventListener('scroll', onScroll);
      for (const node of renderedNodes.values()) node.remove();
      renderedNodes.clear();
      spacer.remove();
    },
  };
}
