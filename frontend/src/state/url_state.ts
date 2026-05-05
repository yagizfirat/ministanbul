// v0.8.2 KM-b — URL state persistence (Spec Ek A.19 #5).
//
// Sağ paneldeki görünürlük state'lerini URL query string'e yansıtır,
// böylece "şu hatları açtım, sana göstereyim" linki paylaşılabilir.
//
// Tasarım:
//   - parse: pure, raw partial state döner. Eksik field undefined.
//     Caller defaults ile merge eder.
//   - serialize: full state + defaults alır, default'a eşit field'ları
//     URL'den atar (default-elision — kısa URL).
//   - routes/focus için comma-separated; on/off bus/metrobus için
//     literal "on"/"off".
//   - URL'i okurken `URLSearchParams` (decode tolerant); yazarken
//     manual concat (encode'suz okunabilir route_id'ler — `public:m2`
//     query value'sunda RFC 3986 reserved değil, modern browser kabul).

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
