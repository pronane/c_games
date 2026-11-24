export interface AbSample {
  fps: number;
  p50_ms: number;
  p95_ms: number;
  tris: number;
  calls: number;
  textures: number;
  geometries: number;
  lod: string;
}
export function parseAbStats(text: string): AbSample[];
export function summariseLeg(label: string, samples: AbSample[]): string;
export function main(argv: string[]): void;
