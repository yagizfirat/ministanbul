// URL state persistence for the panel's visibility toggles, so a
// shareable link reproduces the same view.
//
//   parse:     pure; missing fields stay undefined for the caller
//              to merge with its defaults.
//   serialize: takes the full state + defaults and omits fields that
//              equal the defaults (default-elision keeps URLs short).
//
// Wire format:
//   ?routes=id1,id2&bus=off&metrobus=off&focus=id1
//   - routes / focus: comma-separated; serializer writes them raw
//     (`public:m2`), parser uses URLSearchParams which also accepts
//     percent-encoded forms (`%3A`).
//   - bus / metrobus: literal "on" / "off".

export interface UrlState {
  routes?: readonly string[];
  bus?: boolean;
  metrobus?: boolean;
  focus?: readonly string[];
}

export interface UrlStateDefaults {
  routes: readonly string[];
  bus: boolean;
  metrobus: boolean;
  focus: readonly string[] | null;
}

export interface UrlStateInput {
  routes: readonly string[];
  bus: boolean;
  metrobus: boolean;
  focus: readonly string[] | null;
}

const ROUTES_KEY = 'routes';
const BUS_KEY = 'bus';
const METROBUS_KEY = 'metrobus';
const FOCUS_KEY = 'focus';

export function parseUrlState(searchString: string): UrlState {
  const params = new URLSearchParams(searchString || '');
  const out: UrlState = {};

  if (params.has(ROUTES_KEY)) {
    out.routes = parseIdList(params.get(ROUTES_KEY) ?? '');
  }
  const busRaw = params.get(BUS_KEY);
  if (busRaw === 'on') out.bus = true;
  else if (busRaw === 'off') out.bus = false;

  const metroRaw = params.get(METROBUS_KEY);
  if (metroRaw === 'on') out.metrobus = true;
  else if (metroRaw === 'off') out.metrobus = false;

  if (params.has(FOCUS_KEY)) {
    const list = parseIdList(params.get(FOCUS_KEY) ?? '');
    if (list.length > 0) out.focus = list;
  }

  return out;
}

export function serializeUrlState(
  state: UrlStateInput,
  defaults: UrlStateDefaults,
): string {
  const parts: string[] = [];

  if (!sameIdSet(state.routes, defaults.routes)) {
    parts.push(`${ROUTES_KEY}=${state.routes.join(',')}`);
  }
  if (state.bus !== defaults.bus) {
    parts.push(`${BUS_KEY}=${state.bus ? 'on' : 'off'}`);
  }
  if (state.metrobus !== defaults.metrobus) {
    parts.push(`${METROBUS_KEY}=${state.metrobus ? 'on' : 'off'}`);
  }
  if (!sameFocus(state.focus, defaults.focus)) {
    if (state.focus !== null && state.focus.length > 0) {
      parts.push(`${FOCUS_KEY}=${state.focus.join(',')}`);
    }
  }

  return parts.length === 0 ? '' : `?${parts.join('&')}`;
}

function parseIdList(raw: string): string[] {
  if (raw === '') return [];
  const seen = new Set<string>();
  const out: string[] = [];
  for (const id of raw.split(',')) {
    const trimmed = id.trim();
    if (trimmed === '' || seen.has(trimmed)) continue;
    seen.add(trimmed);
    out.push(trimmed);
  }
  return out;
}

function sameIdSet(a: readonly string[], b: readonly string[]): boolean {
  if (a.length !== b.length) return false;
  const set = new Set(b);
  for (const id of a) if (!set.has(id)) return false;
  return true;
}

function sameFocus(
  a: readonly string[] | null | undefined,
  b: readonly string[] | null | undefined,
): boolean {
  const aEmpty = a === undefined || a === null || a.length === 0;
  const bEmpty = b === undefined || b === null || b.length === 0;
  if (aEmpty && bEmpty) return true;
  if (aEmpty || bEmpty) return false;
  return sameIdSet(a as readonly string[], b as readonly string[]);
}
