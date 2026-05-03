// KM5-d (Spec §5.8) — sonraki durak listesi compute helper.
//
// Pure: PreparedTrip.stopProjections + nowSec → planlı saatten itibaren
// gelmemiş k+1...k+limit durağı çeker. ETA = arrivalSec - nowSec (planlı
// saat referansı; real-time ETA v0.9+).
//
// Vehicle pozisyonu ya da bearing'e bakılmaz — projection arrivalSec
// monotone artıyor (prepareTrip sort), filter ile "şu andan sonra"
// kalan duraklar zaten yön-doğru sıradadır.

import type { PreparedTrip } from './scheduled_trip';

export interface NextStop {
  stopName: string;
  scheduled: string;       // "HH:MM" (24h, IST wall-clock; arrivalSec >= 86400 ise mod 24)
  etaSeconds: number;      // arrivalSec - nowSec; negatif olamaz (filter sonrası)
  sequence: number;
}

export function computeNextStops(
  prepared: PreparedTrip,
  nowSec: number,
  limit: number = 5,
): NextStop[] {
  const out: NextStop[] = [];
  const sps = prepared.stopProjections;
  for (let i = 0; i < sps.length && out.length < limit; i++) {
    const sp = sps[i];
    if (sp.arrivalSec <= nowSec) continue;
    out.push({
      stopName: sp.stopName,
      scheduled: formatTime(sp.arrivalSec),
      etaSeconds: sp.arrivalSec - nowSec,
      sequence: sp.sequence,
    });
  }
  return out;
}

// arrivalSec midnight'tan itibaren saniye; gece servisi 25:30 → "01:30".
export function formatTime(arrivalSec: number): string {
  const h = Math.floor(arrivalSec / 3600) % 24;
  const m = Math.floor((arrivalSec % 3600) / 60);
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
}

// "30sn", "2 dk", "1 sa 5 dk". Negatif input olmamalı (caller filter ediyor).
export function formatEta(seconds: number): string {
  if (seconds < 60) return `${seconds}sn`;
  const totalMin = Math.round(seconds / 60);
  if (totalMin < 60) return `${totalMin} dk`;
  const h = Math.floor(totalMin / 60);
  const m = totalMin % 60;
  return m === 0 ? `${h} sa` : `${h} sa ${m} dk`;
}
