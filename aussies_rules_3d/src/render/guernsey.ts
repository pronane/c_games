/**
 * AFL guernsey texture — painted procedurally on a canvas at load time.
 *
 * The kit garments in the squad GLB ship with no UVs; jersey UVs are
 * synthesised at load (`jerseyUvs.ts`, chest/back projection). This module
 * paints the other half: an Aussie Rules guernsey in the club's colours with
 * the club's pattern (vertical stripes / hoops / sash), the signature lace-up
 * collar, and a big squad number that reads from the stands.
 *
 * Pattern geometry lives in `patternGeometry` (pure, unit-tested); the
 * canvas code is a thin draw over it.
 */
import * as THREE from 'three';

export type GuernseyPattern = 'solid' | 'vstripes' | 'hstripes' | 'sash';

export type PatternGeometry =
  | { kind: 'solid' }
  | { kind: 'vstripes'; bars: Array<{ x: number; w: number }> }
  | { kind: 'hstripes'; hoops: Array<{ y: number; h: number }> }
  | { kind: 'sash'; angle: number; width: number };

/** Layout of the secondary-colour shapes for a pattern on a W×H canvas. */
export function patternGeometry(pattern: GuernseyPattern, W: number, H: number): PatternGeometry {
  switch (pattern) {
    case 'vstripes': {
      // six vertical flanks, alternating — Collingwood / Richmond / Carlton style
      const bars: Array<{ x: number; w: number }> = [];
      const flank = W / 12;
      for (let i = 0; i < 12; i += 2) bars.push({ x: Math.round(i * flank), w: Math.ceil(flank) });
      return { kind: 'vstripes', bars };
    }
    case 'hstripes':
      // two hoops across the torso — Melbourne / Geelong / West Coast style
      return { kind: 'hstripes', hoops: [
        { y: Math.round(H * 0.28), h: Math.round(H * 0.13) },
        { y: Math.round(H * 0.56), h: Math.round(H * 0.13) },
      ] };
    case 'sash':
      // one band, left shoulder to right hip — Sydney / Adelaide style
      return { kind: 'sash', angle: Math.PI / 5.4, width: H / 5.2 };
    default:
      return { kind: 'solid' };
  }
}

/** Readable ink over a fill colour (simple WCAG-ish luminance gate). */
export function contrastInk(hex: string): string {
  const n = parseInt(hex.replace('#', ''), 16);
  if (Number.isNaN(n)) return '#f5f5f5';
  const r = (n >> 16) & 0xff, g = (n >> 8) & 0xff, b = n & 0xff;
  return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255 > 0.62 ? '#101010' : '#f5f5f5';
}

export interface GuernseySpec {
  primary: string;
  secondary: string;
  pattern: GuernseyPattern;
  number: number | null;
}

const GUERNSEY_SIZE = 512;

/** Paint a full-colour AFL guernsey (front and back are the same projection). */
export function guernseyTexture(spec: GuernseySpec): THREE.CanvasTexture {
  const W = GUERNSEY_SIZE, H = GUERNSEY_SIZE;
  const c = document.createElement('canvas');
  c.width = W; c.height = H;
  const g = c.getContext('2d')!;

  // base
  g.fillStyle = spec.primary;
  g.fillRect(0, 0, W, H);

  // pattern in the secondary colour
  const geo = patternGeometry(spec.pattern, W, H);
  g.fillStyle = spec.secondary;
  if (geo.kind === 'vstripes') {
    for (const b of geo.bars) g.fillRect(b.x, 0, b.w, H);
  } else if (geo.kind === 'hstripes') {
    for (const hp of geo.hoops) g.fillRect(0, hp.y, W, hp.h);
  } else if (geo.kind === 'sash') {
    g.save();
    g.translate(W / 2, H / 2);
    g.rotate(geo.angle);
    g.fillRect(-W, -geo.width / 2, W * 2, geo.width);
    g.restore();
  }

  // collar: crew band + lace-up (the AFL signature) — dark trim
  const trim = contrastInk(spec.primary) === '#101010' ? '#101010' : '#f5f5f5';
  g.strokeStyle = spec.secondary;
  g.lineWidth = H * 0.045;
  g.beginPath();
  g.moveTo(W * 0.335, 0);
  g.quadraticCurveTo(W * 0.5, H * 0.075, W * 0.665, 0);
  g.stroke();
  // laces
  g.strokeStyle = trim;
  g.lineWidth = H * 0.012;
  for (const dx of [-0.028, 0.028]) {
    g.beginPath();
    g.moveTo(W * (0.5 + dx), H * 0.004);
    g.lineTo(W * (0.5 + dx * 1.6), H * 0.062);
    g.stroke();
  }

  // squad number — big, with a thin secondary outline so it reads on any pattern
  if (spec.number !== null) {
    const ink = contrastInk(spec.primary);
    const n = String(spec.number);
    let fontPx = 210;
    g.textAlign = 'center';
    g.textBaseline = 'middle';
    for (;;) {
      g.font = `900 ${fontPx}px system-ui, 'Arial Black', sans-serif`;
      if (g.measureText(n).width <= W * 0.72 || fontPx <= 60) break;
      fontPx -= 10;
    }
    g.lineJoin = 'round';
    g.strokeStyle = spec.secondary;
    g.lineWidth = fontPx * 0.09;
    g.strokeText(n, W / 2, H * 0.52);
    g.fillStyle = ink;
    g.fillText(n, W / 2, H * 0.52);
  }

  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 4;
  return tex;
}
