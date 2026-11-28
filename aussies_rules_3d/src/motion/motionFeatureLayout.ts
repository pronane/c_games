/**
 * Versioned feature contract shared by the offline baker
 * (tools/build_afl_motion_features.py) and the runtime search.
 * Must stay byte-identical to the AFL bake — validated by tests.
 */
export const SCHEMA_VERSION = 2;
export const NO_CONTACT = 1.5;
export const TIME_TO_CONTACT = 23;
export const NAMES = [
  'foot_l_pos_x', 'foot_l_pos_z', 'foot_r_pos_x', 'foot_r_pos_z',
  'foot_l_vel_x', 'foot_l_vel_z', 'foot_r_vel_x', 'foot_r_vel_z',
  'root_vel_x', 'root_vel_z', 'yaw_rate',
  'traj_pos_0_x', 'traj_pos_0_z', 'traj_pos_1_x', 'traj_pos_1_z',
  'traj_pos_2_x', 'traj_pos_2_z',
  'traj_dir_0_x', 'traj_dir_0_z', 'traj_dir_1_x', 'traj_dir_1_z',
  'traj_dir_2_x', 'traj_dir_2_z',
  'time_to_contact',
] as const;
export const DIMENSIONS = NAMES.length;
export const TRAJECTORY_TIMES = [0.2, 0.4, 0.6] as const;

export function matchesLayout(names: readonly string[]): boolean {
  return names.length === NAMES.length && NAMES.every((n, i) => names[i] === n);
}

export function groupWeights(): number[] {
  const w = new Array(NAMES.length).fill(1);
  for (let i = 4; i < 8; i++) w[i] = 1.3;   // foot velocity
  w[8] = w[9] = 0.8;                         // root velocity
  w[10] = 0.7;                               // yaw rate
  for (let i = 11; i < 17; i++) w[i] = 1.5;  // trajectory position
  for (let i = 17; i < 23; i++) w[i] = 1.2;  // trajectory facing
  w[TIME_TO_CONTACT] = 12.0;
  return w;
}

export function circularDifference(a: number, b: number): number {
  let d = (a - b) % 1;
  if (d > 0.5) d -= 1;
  if (d < -0.5) d += 1;
  return d;
}
export function circularDistance(a: number, b: number): number {
  const d = Math.abs(circularDifference(a, b));
  return d > 0.5 ? 1 - d : d;
}
export function wrap01(v: number): number {
  return v - Math.floor(v);
}
export function clamp01(v: number): number {
  return v < 0 ? 0 : v > 1 ? 1 : v;
}
