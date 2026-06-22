/** Format a number of seconds as ``m:ss`` (e.g. 75 → "1:15").
 *
 * Single source of truth — previously duplicated as formatTime/fmtTime/
 * formatDuration across the player, chord timeline, chord-sheet export, and
 * library.
 */
export function formatTime(seconds: number): string {
  const safe = Number.isFinite(seconds) && seconds > 0 ? seconds : 0;
  const m = Math.floor(safe / 60);
  const s = Math.floor(safe % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}
