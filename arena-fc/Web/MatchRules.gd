# MatchRules.gd — pure, side-effect-free football logic for the browser edition, so it can be unit tested
# headless. BrowserBoot.gd calls these; nothing here touches the scene tree.
# Coordinates: pitch centred on origin, X is the long axis. Team 0 attacks +X, team 1 attacks -X.
extends RefCounted

const POST_R := 0.06

# ---- goalkeeper -------------------------------------------------------------------------------
## Where the keeper should be. If the ball is travelling at the goal, go to where it will cross the goal
## line (clamped just outside the posts); otherwise hold the angle bisector between ball and goal centre.
static func keeper_target(own_goal_x: float, sign: float, ball_pos: Vector3, ball_vel: Vector3, goal_w: float) -> Vector3:
	var toward := -sign * ball_vel.x > 0.0          # own goal is at x = own_goal_x; sign = +1 means it is on -X
	var line_x := own_goal_x + sign * 1.2
	var dx := absf(ball_pos.x - own_goal_x)
	if toward and absf(ball_vel.x) > 6.0 and dx < 30.0:
		var t := (line_x - ball_pos.x) / ball_vel.x
		if t > 0.0:
			var z := ball_pos.z + ball_vel.z * t
			return Vector3(line_x, 0, clampf(z, -goal_w - 0.6, goal_w + 0.6))
	var z2 := clampf(ball_pos.z * (0.35 + 0.35 * clampf(1.0 - dx / 40.0, 0.0, 1.0)), -goal_w * 0.85, goal_w * 0.85)
	var out := clampf(2.0 + (30.0 - minf(dx, 30.0)) * 0.05, 1.2, 3.2)       # steps out as the ball comes closer
	return Vector3(own_goal_x + sign * out, 0, z2)

## Probability that a keeper at `miss` metres from the ball's path keeps out a shot of `speed` m/s.
static func save_chance(miss: float, speed: float, reach: float) -> float:
	if miss > reach:
		return 0.0
	var closeness := 1.0 - miss / reach
	var pace := clampf((speed - 8.0) / 24.0, 0.0, 1.0)
	return clampf(0.35 + 0.6 * closeness - 0.35 * pace, 0.05, 0.95)

# ---- shooting / passing ------------------------------------------------------------------------
## Angular error (radians, 1 sigma-ish) of a shot. Further out, harder hit and more pressure = wilder.
static func shot_error(dist: float, pressure: float, power: float) -> float:
	return clampf(0.015 + dist * 0.0022 + pressure * 0.05 + maxf(0.0, power - 0.75) * 0.08, 0.015, 0.22)

## Number in 0..1: how closely an opponent is marking the ball carrier (1 = right on top of him).
static func pressure(carrier: Vector3, opponents: Array) -> float:
	var best := 1e9
	for o in opponents:
		best = minf(best, carrier.distance_to(o))
	return clampf(1.0 - (best - 1.0) / 5.0, 0.0, 1.0)

## Shortest distance from `p` to the segment a-b on the ground plane.
static func dist_to_segment(p: Vector3, a: Vector3, b: Vector3) -> float:
	var ab := Vector3(b.x - a.x, 0, b.z - a.z)
	var l2 := ab.length_squared()
	if l2 < 0.0001:
		return Vector2(p.x - a.x, p.z - a.z).length()
	var t := clampf(((p.x - a.x) * ab.x + (p.z - a.z) * ab.z) / l2, 0.0, 1.0)
	var c := Vector3(a.x + ab.x * t, 0, a.z + ab.z * t)
	return Vector2(p.x - c.x, p.z - c.z).length()

## Where to aim a pass so it meets a moving team-mate: lead by flight time.
static func lead_point(from: Vector3, cand_pos: Vector3, cand_vel: Vector3, ball_speed: float, extra: float) -> Vector3:
	var d := from.distance_to(cand_pos)
	var t := d / maxf(ball_speed, 1.0)
	return cand_pos + cand_vel * (t + extra)

## Pass speed that gets the ball there firmly but not through the receiver.
static func pass_speed(dist: float, through: bool) -> float:
	return clampf(8.0 + dist * 0.6 + (3.0 if through else 0.0), 10.0, 26.0)

## Rank a pass option. Higher is better. `input_dir` (ground vector, may be zero) is the user's stick.
static func pass_score(from: Vector3, cand: Vector3, attack_sign: float, opponents: Array, input_dir: Vector3) -> float:
	var d := from.distance_to(cand)
	if d < 2.0:
		return -1e9
	var forward := (cand.x - from.x) * attack_sign
	var lane := 9.0
	for o in opponents:
		lane = minf(lane, dist_to_segment(o, from, cand))
	var s := forward * 0.22 - d * 0.07 + minf(lane, 5.0) * 1.1
	if lane < 1.3:
		s -= 6.0                                        # the lane is blocked
	if d > 38.0:
		s -= (d - 38.0) * 0.5
	if input_dir.length() > 0.2:
		var to := Vector3(cand.x - from.x, 0, cand.z - from.z).normalized()
		s += to.dot(input_dir.normalized()) * 6.0
	return s

# ---- woodwork ----------------------------------------------------------------------------------
## Ball (radius r) vs the two posts and crossbar of the goal at x = side * half_l.
## Returns {"hit": bool, "vel": Vector3, "pos": Vector3}.
static func woodwork(pos: Vector3, vel: Vector3, side: float, half_l: float, goal_w: float, goal_h: float, r: float) -> Dictionary:
	var gx := side * half_l
	for zs in [-1.0, 1.0]:
		var pz: float = zs * goal_w
		var dx := pos.x - gx
		var dz := pos.z - pz
		var dist := Vector2(dx, dz).length()
		if pos.y < goal_h and dist < r + POST_R:
			var n := Vector3(dx, 0, dz).normalized() if dist > 0.0001 else Vector3(-side, 0, 0)
			var vn := vel.dot(n)
			if vn < 0.0:
				var v := vel - n * (1.0 + 0.55) * vn
				var np := Vector3(gx, pos.y, pz) + n * (r + POST_R + 0.01)
				np.y = pos.y
				return {"hit": true, "vel": v, "pos": np, "kind": "post"}
	if absf(pos.z) < goal_w:
		var dx2 := pos.x - gx
		var dy := pos.y - goal_h
		var dist2 := Vector2(dx2, dy).length()
		if dist2 < r + POST_R:
			var n2 := Vector3(dx2, dy, 0).normalized() if dist2 > 0.0001 else Vector3(0, 1, 0)
			var vn2 := vel.dot(n2)
			if vn2 < 0.0:
				var v2 := vel - n2 * (1.0 + 0.5) * vn2
				return {"hit": true, "vel": v2, "pos": Vector3(gx, goal_h, pos.z) + n2 * (r + POST_R + 0.01), "kind": "bar"}
	return {"hit": false, "vel": vel, "pos": pos}

# ---- restarts ----------------------------------------------------------------------------------
## Decide the restart when the ball has gone out of play at `pos`, last touched by `last_team`.
## Returns {"kind": "throw"/"goal_kick"/"corner", "team": awarded team, "spot": Vector3}.
static func restart_for(pos: Vector3, last_team: int, half_l: float, half_w: float) -> Dictionary:
	if absf(pos.x) <= half_l:
		var z := half_w * signf(pos.z)
		return {"kind": "throw", "team": 1 - last_team, "spot": Vector3(clampf(pos.x, -half_l + 1.0, half_l - 1.0), 0.11, z)}
	var end := signf(pos.x)                             # +1: team 0 attacks this end (team 1 defends it)
	var defender := 1 if end > 0.0 else 0
	if last_team == defender:                           # defender put it out: corner to the attackers
		var cz := half_w * (1.0 if pos.z >= 0.0 else -1.0)
		return {"kind": "corner", "team": 1 - defender, "spot": Vector3(end * (half_l - 0.4), 0.11, cz * 0.97)}
	return {"kind": "goal_kick", "team": defender, "spot": Vector3(end * (half_l - 5.5), 0.11, 0)}

# ---- fouls -------------------------------------------------------------------------------------
## Tackle from behind (tackler's motion roughly along the victim's facing) is far likelier to be a foul.
static func foul_chance(tackler_vel: Vector3, victim_facing: Vector3, sliding: bool) -> float:
	var v := Vector3(tackler_vel.x, 0, tackler_vel.z)
	var f := Vector3(victim_facing.x, 0, victim_facing.z)
	if v.length() < 0.5 or f.length() < 0.1:
		return 0.08
	var behind := v.normalized().dot(f.normalized())    # +1 = chasing him from behind
	return clampf(0.10 + maxf(0.0, behind) * 0.4 + (0.15 if sliding else 0.0), 0.05, 0.7)
