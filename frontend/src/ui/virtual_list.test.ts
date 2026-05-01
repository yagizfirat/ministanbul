// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { createVirtualList } from './virtual_list';

const ITEM_HEIGHT = 40;
const VIEWPORT_HEIGHT = 400;
const OVERSCAN = 5;

// jsdom layout hesaplamaz — clientHeight + scrollTop manuel mock.
function setScrollMetrics(el: HTMLElement, viewportHeight: number, scrollTop = 0): void {
  Object.defineProperty(el, 'clientHeight', {
    value: viewportHeight,
    configurable: true,
  });
  Object.defineProperty(el, 'scrollTop', {
    value: scrollTop,
    writable: true,
    configurable: true,
  });
}

function makeContainer(viewportHeight = VIEWPORT_HEIGHT): HTMLElement {
  const c = document.createElement('div');
  c.id = 'vl-container';
  document.body.appendChild(c);
  setScrollMetrics(c, viewportHeight, 0);
  return c;
}

function makeRenderItem(): (item: number, index: number) => HTMLElement {
  return (item, index) => {
    const el = document.createElement('div');
    el.dataset.index = String(index);
    el.textContent = `item-${item}`;
    return el;
  };
}

afterEach(() => {
  document.body.innerHTML = '';
});

describe('createVirtualList — DOM setup', () => {
  it('inserts a spacer with height = items.length * itemHeight', () => {
    const container = makeContainer();
    createVirtualList({
      container,
      items: Array.from({ length: 1000 }, (_, i) => i),
      itemHeight: ITEM_HEIGHT,
      renderItem: makeRenderItem(),
      overscan: OVERSCAN,
    });
    const spacer = container.querySelector('.virtual-list__spacer') as HTMLElement;
    expect(spacer).not.toBeNull();
    expect(spacer.style.height).toBe(`${1000 * ITEM_HEIGHT}px`);
  });
});

describe('createVirtualList — initial render at scrollTop=0', () => {
  it('renders only viewport + 2*overscan items, not all 1000', () => {
    const container = makeContainer();
    const renderItem = vi.fn(makeRenderItem());
    createVirtualList({
      container,
      items: Array.from({ length: 1000 }, (_, i) => i),
      itemHeight: ITEM_HEIGHT,
      renderItem,
      overscan: OVERSCAN,
    });
    // Viewport 400 / 40 = 10 items + overscan 5 below = ~15.
    // (Top overscan clamp'lı: scrollTop=0 → start=max(0,-5)=0)
    const items = container.querySelectorAll('.virtual-list__item');
    expect(items.length).toBeLessThanOrEqual(20);
    expect(items.length).toBeGreaterThan(0);
    expect(renderItem).toHaveBeenCalledTimes(items.length);
  });

  it('positions item-0 at top:0px, item-1 at top:40px', () => {
    const container = makeContainer();
    createVirtualList({
      container,
      items: Array.from({ length: 100 }, (_, i) => i),
      itemHeight: ITEM_HEIGHT,
      renderItem: makeRenderItem(),
    });
    const items = container.querySelectorAll('.virtual-list__item');
    const byIndex = (n: number) =>
      Array.from(items).find((el) => (el as HTMLElement).dataset.index === String(n)) as HTMLElement;
    expect(byIndex(0).style.top).toBe('0px');
    expect(byIndex(1).style.top).toBe('40px');
    expect(byIndex(0).style.position).toBe('absolute');
  });
});

describe('createVirtualList — scroll', () => {
  it('renders items around the new scrollTop after a scroll event', () => {
    const container = makeContainer();
    createVirtualList({
      container,
      items: Array.from({ length: 1000 }, (_, i) => i),
      itemHeight: ITEM_HEIGHT,
      renderItem: makeRenderItem(),
      overscan: OVERSCAN,
    });
    setScrollMetrics(container, VIEWPORT_HEIGHT, 400);
    container.dispatchEvent(new Event('scroll'));
    const indices = Array.from(
      container.querySelectorAll<HTMLElement>('.virtual-list__item'),
    ).map((el) => Number(el.dataset.index));
    // scrollTop=400 → first visible = 400/40 = 10. start = 10 - 5 = 5.
    // end = ceil((400+400)/40) - 1 + 5 = 19 + 5 = 24.
    expect(Math.min(...indices)).toBeGreaterThanOrEqual(5);
    expect(Math.max(...indices)).toBeLessThanOrEqual(24);
    expect(indices).not.toContain(0);
  });
});

describe('createVirtualList — setItems', () => {
  it('shrinking the list updates the spacer and clamps scrollTop', () => {
    const container = makeContainer();
    const handle = createVirtualList({
      container,
      items: Array.from({ length: 1000 }, (_, i) => i),
      itemHeight: ITEM_HEIGHT,
      renderItem: makeRenderItem(),
    });
    setScrollMetrics(container, VIEWPORT_HEIGHT, 30000);
    handle.setItems([0, 1, 2, 3, 4]);
    const spacer = container.querySelector('.virtual-list__spacer') as HTMLElement;
    expect(spacer.style.height).toBe(`${5 * ITEM_HEIGHT}px`);
    // 5 items × 40px = 200px total < 400px viewport → maxScroll=0.
    expect(container.scrollTop).toBe(0);
    expect(container.querySelectorAll('.virtual-list__item').length).toBe(5);
  });

  it('growing the list refills the viewport with the new items', () => {
    const container = makeContainer();
    const handle = createVirtualList({
      container,
      items: [0, 1, 2],
      itemHeight: ITEM_HEIGHT,
      renderItem: makeRenderItem(),
    });
    handle.setItems(Array.from({ length: 500 }, (_, i) => i + 1000));
    const items = container.querySelectorAll<HTMLElement>('.virtual-list__item');
    expect(items.length).toBeGreaterThan(0);
    // İlk item'ın text'i 1000 olmalı (yeni veri set'inden).
    const first = Array.from(items).find((el) => el.dataset.index === '0');
    expect(first?.textContent).toBe('item-1000');
  });
});

describe('createVirtualList — scrollToIndex', () => {
  it('sets scrollTop to index * itemHeight', () => {
    const container = makeContainer();
    const handle = createVirtualList({
      container,
      items: Array.from({ length: 1000 }, (_, i) => i),
      itemHeight: ITEM_HEIGHT,
      renderItem: makeRenderItem(),
    });
    handle.scrollToIndex(500);
    expect(container.scrollTop).toBe(500 * ITEM_HEIGHT);
  });
});

describe('createVirtualList — destroy', () => {
  it('removes the spacer + items and stops responding to scroll', () => {
    const container = makeContainer();
    const renderItem = vi.fn(makeRenderItem());
    const handle = createVirtualList({
      container,
      items: Array.from({ length: 1000 }, (_, i) => i),
      itemHeight: ITEM_HEIGHT,
      renderItem,
      overscan: OVERSCAN,
    });
    const callCountBefore = renderItem.mock.calls.length;
    handle.destroy();
    expect(container.querySelector('.virtual-list__spacer')).toBeNull();
    expect(container.querySelectorAll('.virtual-list__item').length).toBe(0);
    setScrollMetrics(container, VIEWPORT_HEIGHT, 800);
    container.dispatchEvent(new Event('scroll'));
    expect(renderItem.mock.calls.length).toBe(callCountBefore);
  });
});

describe('createVirtualList — defaults & edge cases', () => {
  it('uses overscan=5 by default', () => {
    const container = makeContainer();
    createVirtualList({
      container,
      items: Array.from({ length: 1000 }, (_, i) => i),
      itemHeight: ITEM_HEIGHT,
      renderItem: makeRenderItem(),
      // overscan omitted
    });
    // Viewport 400/40 = 10 visible. With overscan=5 below at top
    // (clamped to 0), expect ~15 items rendered.
    const n = container.querySelectorAll('.virtual-list__item').length;
    expect(n).toBeGreaterThanOrEqual(10);
    expect(n).toBeLessThanOrEqual(20);
  });

  it('renders nothing for an empty items array', () => {
    const container = makeContainer();
    const renderItem = vi.fn(makeRenderItem());
    createVirtualList({
      container,
      items: [],
      itemHeight: ITEM_HEIGHT,
      renderItem,
    });
    const spacer = container.querySelector('.virtual-list__spacer') as HTMLElement;
    expect(spacer.style.height).toBe('0px');
    expect(container.querySelectorAll('.virtual-list__item').length).toBe(0);
    expect(renderItem).not.toHaveBeenCalled();
  });
});
