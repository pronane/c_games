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
export interface AbCamSample {
  frames: number;
  ball_in: number;
  player_in: number | null;
  ball_max_ndc: number;
  player_max_ndc: number | null;
}
export function parseAbStats(text: string): AbSample[];
export function summariseLeg(label: string, samples: AbSample[]): string;
export function parseAbCamStats(text: string): AbCamSample[];
export function summariseCamLeg(label: string, samples: AbCamSample[]): string;
export function main(argv: string[]): void;
