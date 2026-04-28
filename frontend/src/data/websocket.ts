const WS_PATH = '/ws/vehicles/';
const PING_INTERVAL_MS = 30_000;
const BACKOFF_INITIAL_MS = 1_000;
const BACKOFF_MAX_MS = 30_000;

export interface VehicleSnapshot {
  type: 'vehicles_all_update';
  timestamp: string;
  vehicle_count: number;
  mapped_count: number;
  vehicles: unknown[];
}

type IncomingMessage = VehicleSnapshot | { type: string; [k: string]: unknown };

export interface VehicleClientHandlers {
  onSnapshot?: (snapshot: VehicleSnapshot) => void;
  onConnected?: () => void;
  onDisconnected?: () => void;
}

export interface WsController {
  isOpen(): boolean;
}

export function connectWebSocket(handlers: VehicleClientHandlers = {}): WsController {
  let socket: WebSocket | null = null;
  let backoffMs = BACKOFF_INITIAL_MS;
  let pingTimer: ReturnType<typeof setInterval> | null = null;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  const url = buildWsUrl();

  function open(): void {
    console.log('[ws] connecting →', url);
    socket = new WebSocket(url);

    socket.addEventListener('open', () => {
      console.log('[ws] connected');
      backoffMs = BACKOFF_INITIAL_MS;
      pingTimer = setInterval(sendPing, PING_INTERVAL_MS);
      handlers.onConnected?.();
    });

    socket.addEventListener('message', (ev) => {
      let msg: IncomingMessage;
      try {
        msg = JSON.parse(ev.data) as IncomingMessage;
      } catch (err) {
        console.warn('[ws] non-JSON frame', err);
        return;
      }

      if (msg.type === 'vehicles_all_update') {
        const snap = msg as VehicleSnapshot;
        console.log(
          `[ws] snapshot: ${snap.vehicle_count} vehicles, ` +
            `${snap.mapped_count} mapped, ${snap.vehicles.length} in payload`,
        );
        handlers.onSnapshot?.(snap);
      } else if (msg.type === 'pong') {
        // expected response to {action: 'ping'}
      } else {
        console.log('[ws] message', msg.type);
      }
    });

    socket.addEventListener('close', (ev) => {
      console.warn(`[ws] closed (code=${ev.code}); reconnecting in ${backoffMs}ms`);
      cleanupSocket();
      handlers.onDisconnected?.();
      scheduleReconnect();
    });

    socket.addEventListener('error', () => {
      // 'close' will fire next; let it handle reconnect.
    });
  }

  function sendPing(): void {
    if (socket?.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ action: 'ping' }));
    }
  }

  function cleanupSocket(): void {
    if (pingTimer !== null) {
      clearInterval(pingTimer);
      pingTimer = null;
    }
    socket = null;
  }

  function scheduleReconnect(): void {
    if (reconnectTimer !== null) return;
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null;
      open();
    }, backoffMs);
    backoffMs = Math.min(backoffMs * 2, BACKOFF_MAX_MS);
  }

  open();

  return {
    isOpen: () => socket?.readyState === WebSocket.OPEN,
  };
}

function buildWsUrl(): string {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${proto}//${window.location.host}${WS_PATH}`;
}
