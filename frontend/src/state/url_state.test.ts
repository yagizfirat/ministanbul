import { describe, expect, it } from 'vitest';
import {
  parseUrlState,
  serializeUrlState,
  type UrlStateDefaults,
} from './url_state';

const DEFAULTS: UrlStateDefaults = {
  routes: ['public:m2', 'public:m4', 'public:f1'],
  bus: true,
  metrobus: true,
  focus: null,
};

// ── parse ───────────────────────────────────────────────────────────
describe('parseUrlState', () => {
  it('returns empty object for empty search string', () => {
    expect(parseUrlState('')).toEqual({});
  });

  it('returns empty object for "?" only', () => {
    expect(parseUrlState('?')).toEqual({});
  });

  it('parses routes comma-separated', () => {
    const out = parseUrlState('?routes=public:m2,public:m4');
    expect(out.routes).toEqual(['public:m2', 'public:m4']);
  });

  it('parses bus=on as true, bus=off as false', () => {
    expect(parseUrlState('?bus=on').bus).toBe(true);
    expect(parseUrlState('?bus=off').bus).toBe(false);
  });

  it('parses metrobus=on as true, metrobus=off as false', () => {
    expect(parseUrlState('?metrobus=on').metrobus).toBe(true);
    expect(parseUrlState('?metrobus=off').metrobus).toBe(false);
  });

  it('parses focus comma-separated', () => {
    const out = parseUrlState('?focus=public:m2,public:m4');
    expect(out.focus).toEqual(['public:m2', 'public:m4']);
  });

  it('parses combined query string', () => {
    const out = parseUrlState(
      '?routes=public:m2,public:m4&bus=off&metrobus=off&focus=public:m2',
    );
    expect(out).toEqual({
      routes: ['public:m2', 'public:m4'],
      bus: false,
      metrobus: false,
      focus: ['public:m2'],
    });
  });

  it('routes= (empty value) → routes is empty array (Hiçbiri state)', () => {
    expect(parseUrlState('?routes=').routes).toEqual([]);
  });

  it('focus= (empty value) → focus undefined (no active focus)', () => {
    expect(parseUrlState('?focus=').focus).toBeUndefined();
  });

  it('unknown bus value (e.g. "true") → bus undefined', () => {
    expect(parseUrlState('?bus=true').bus).toBeUndefined();
  });

  it('routes deduplicate + trim', () => {
    const out = parseUrlState('?routes=public:m2, public:m2 ,public:m4');
    expect(out.routes).toEqual(['public:m2', 'public:m4']);
  });

  it('handles URL-encoded colon (%3A)', () => {
    const out = parseUrlState('?routes=public%3Am2');
    expect(out.routes).toEqual(['public:m2']);
  });

  it('ignores unknown keys silently', () => {
    const out = parseUrlState('?bogus=42&routes=public:m2');
    expect(out).toEqual({ routes: ['public:m2'] });
  });
});

// ── serialize ───────────────────────────────────────────────────────
describe('serializeUrlState — default-elision', () => {
  it('returns empty string when all state equals defaults', () => {
    const out = serializeUrlState(
      { routes: DEFAULTS.routes, bus: true, metrobus: true, focus: null },
      DEFAULTS,
    );
    expect(out).toBe('');
  });

  it('omits routes when same set (order-independent)', () => {
    const out = serializeUrlState(
      {
        routes: ['public:f1', 'public:m4', 'public:m2'], // reordered
        bus: true,
        metrobus: true,
        focus: null,
      },
      DEFAULTS,
    );
    expect(out).toBe('');
  });

  it('emits routes when different from defaults', () => {
    const out = serializeUrlState(
      { routes: ['public:m2'], bus: true, metrobus: true, focus: null },
      DEFAULTS,
    );
    expect(out).toBe('?routes=public:m2');
  });

  it('emits routes= (empty) when state is "Hiçbiri" (empty)', () => {
    const out = serializeUrlState(
      { routes: [], bus: true, metrobus: true, focus: null },
      DEFAULTS,
    );
    expect(out).toBe('?routes=');
  });

  it('emits bus=off when bus is false', () => {
    const out = serializeUrlState(
      { routes: DEFAULTS.routes, bus: false, metrobus: true, focus: null },
      DEFAULTS,
    );
    expect(out).toBe('?bus=off');
  });

  it('emits metrobus=off when metrobus is false', () => {
    const out = serializeUrlState(
      { routes: DEFAULTS.routes, bus: true, metrobus: false, focus: null },
      DEFAULTS,
    );
    expect(out).toBe('?metrobus=off');
  });

  it('emits focus when active', () => {
    const out = serializeUrlState(
      {
        routes: DEFAULTS.routes,
        bus: true,
        metrobus: true,
        focus: ['public:m2', 'public:m4'],
      },
      DEFAULTS,
    );
    expect(out).toBe('?focus=public:m2,public:m4');
  });

  it('combined non-default state', () => {
    const out = serializeUrlState(
      {
        routes: ['public:m2'],
        bus: false,
        metrobus: false,
        focus: ['public:m2'],
      },
      DEFAULTS,
    );
    expect(out).toBe(
      '?routes=public:m2&bus=off&metrobus=off&focus=public:m2',
    );
  });

  it('empty focus array treated as default null (no emit)', () => {
    const out = serializeUrlState(
      { routes: DEFAULTS.routes, bus: true, metrobus: true, focus: [] },
      DEFAULTS,
    );
    expect(out).toBe('');
  });
});

// ── round-trip ──────────────────────────────────────────────────────
describe('parse ∘ serialize round-trip', () => {
  it('non-default state → URL → parsed equals original (excluding defaults)', () => {
    const original = {
      routes: ['public:m2', 'public:m1a'],
      bus: false,
      metrobus: true,
      focus: ['public:m2'] as readonly string[] | null,
    };
    const url = serializeUrlState(original, DEFAULTS);
    const parsed = parseUrlState(url);
    expect(parsed.routes).toEqual(original.routes);
    expect(parsed.bus).toBe(false);
    // metrobus default → not emitted, undefined
    expect(parsed.metrobus).toBeUndefined();
    expect(parsed.focus).toEqual(['public:m2']);
  });

  it('all-default state → "" → parse returns {}', () => {
    const url = serializeUrlState(
      { routes: DEFAULTS.routes, bus: true, metrobus: true, focus: null },
      DEFAULTS,
    );
    expect(parseUrlState(url)).toEqual({});
  });
});
