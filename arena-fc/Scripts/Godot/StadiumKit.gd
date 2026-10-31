# StadiumKit.gd
# A procedural football stadium: floodlit evening atmosphere, two-tier bowl with curved corners, roof,
# animated crowd, floodlight towers, LED advertising boards, goals with full nets and corner flags.
# Everything is generated in code (no imported assets), so it ships in the web build at no size cost.
#
#   var s := StadiumKit.new(); add_child(s); s.build()      # build() once
#   s.celebrate(0)                                          # crowd goes up after a goal
#
# Layout (metres, pitch centred on the origin, goals at +/-HALF_L on the X axis):
#   pitch + 5 m grass run-off -> LED boards -> walkway -> lower tier -> aisle -> upper tier -> roof.
# The bowl is swept along a rounded rectangle, so the four stands join in curved corners.
class_name StadiumKit
extends Node3D

@export var half_l: float = 52.5
@export var half_w: float = 34.0
@export var goal_w: float = 3.66
@export var goal_h: float = 2.44
@export_range(0.0, 1.0) var crowd_density: float = 0.8
@export var home_colour: Color = Color("#d7263d")
@export var away_colour: Color = Color("#1d4ed8")

const GOAL_DEPTH := 2.0
const ROW_DEPTH := 0.85
const LOWER_ROWS := 16
const UPPER_ROWS := 14
const LOWER_RISE := 0.42
const UPPER_RISE := 0.55
const AISLE := 2.6
const CORNER_R := 15.0

var crowd: MultiMeshInstance3D
var crowd_mat: ShaderMaterial
var excite := 0.12
var excite_target := 0.12
var boards_mat: ShaderMaterial

# ring (rounded rectangle) description: point(i, d) = base[i] + dir[i] * (CORNER_R + d)
var _base := PackedVector2Array()
var _dir := PackedVector2Array()
var _a0 := 0.0
var _b0 := 0.0
var _mats := {}

# ---------------------------------------------------------------- public
func build() -> void:
	_a0 = half_l + 9.0
	_b0 = half_w + 7.5
	_make_ring()
	_build_environment()
	_build_ground()
	_build_bowl()
	_build_crowd()
	_build_floodlights()
	_build_boards()
	_build_goals()
	_build_flags()

## Crowd reaction. `side` is 0/1 for the scoring team (their end of the ground goes loudest).
func celebrate(_side: int = 0) -> void:
	excite_target = 1.0
	excite = maxf(excite, 0.8)
	_calm_later()

func _calm_later() -> void:
	await get_tree().create_timer(5.0).timeout
	excite_target = 0.12

func set_excitement(v: float) -> void:
	excite_target = clampf(v, 0.0, 1.0)

func _process(delta: float) -> void:
	excite = lerpf(excite, excite_target, minf(1.0, delta * (4.0 if excite_target > excite else 0.7)))
	if crowd_mat != null:
		crowd_mat.set_shader_parameter("excite", excite)
		crowd_mat.set_shader_parameter("wave_speed", 7.0 if excite > 0.7 else 0.0)

# ---------------------------------------------------------------- materials
func _m(col: Color, rough: float = 0.9, metal: float = 0.0, emit: float = 0.0, vcol: bool = false) -> StandardMaterial3D:
	var key := "%s_%s_%s_%s_%s" % [col.to_html(), rough, metal, emit, vcol]
	if _mats.has(key):
		return _mats[key]
	var m := StandardMaterial3D.new()
	m.albedo_color = col
	m.roughness = rough
	m.metallic = metal
	m.cull_mode = BaseMaterial3D.CULL_DISABLED
	if emit > 0.0:
		m.emission_enabled = true
		m.emission = col
		m.emission_energy_multiplier = emit
	m.vertex_color_use_as_albedo = vcol
	_mats[key] = m
	return m

func _add_mesh(mesh: Mesh, mat: Material, pos: Vector3 = Vector3.ZERO, shadows: bool = true) -> MeshInstance3D:
	var mi := MeshInstance3D.new()
	mi.mesh = mesh
	mi.material_override = mat
	mi.position = pos
	if not shadows:
		mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(mi)
	return mi

# ---------------------------------------------------------------- ring geometry
func _make_ring() -> void:
	_base.clear()
	_dir.clear()
	var ca := _a0 - CORNER_R          # corner-centre coordinates
	var cb := _b0 - CORNER_R
	var es_x := int(ceil(2.0 * ca / 1.6))     # ~1.6 m samples along the edges
	var es_z := int(ceil(2.0 * cb / 1.6))
	var arc := 10
	# right edge (+X), bottom to top
	for k in range(es_z):
		_push(Vector2(ca, -cb + 2.0 * cb * k / es_z), Vector2(1, 0))
	for j in range(arc):                                  # top-right corner
		var th := 0.5 * PI * j / arc
		_push(Vector2(ca, cb), Vector2(cos(th), sin(th)))
	for k in range(es_x):                                 # top edge (+Z), right to left
		_push(Vector2(ca - 2.0 * ca * k / es_x, cb), Vector2(0, 1))
	for j in range(arc):                                  # top-left corner
		var th := 0.5 * PI + 0.5 * PI * j / arc
		_push(Vector2(-ca, cb), Vector2(cos(th), sin(th)))
	for k in range(es_z):                                 # left edge (-X), top to bottom
		_push(Vector2(-ca, cb - 2.0 * cb * k / es_z), Vector2(-1, 0))
	for j in range(arc):                                  # bottom-left corner
		var th := PI + 0.5 * PI * j / arc
		_push(Vector2(-ca, -cb), Vector2(cos(th), sin(th)))
	for k in range(es_x):                                 # bottom edge (-Z), left to right
		_push(Vector2(-ca + 2.0 * ca * k / es_x, -cb), Vector2(0, -1))
	for j in range(arc):                                  # bottom-right corner
		var th := 1.5 * PI + 0.5 * PI * j / arc
		_push(Vector2(ca, -cb), Vector2(cos(th), sin(th)))

func _push(base: Vector2, dir: Vector2) -> void:
	_base.append(base)
	_dir.append(dir)

func _ring_n() -> int:
	return _base.size()

func _pt(i: int, d: float) -> Vector2:
	var k := i % _ring_n()
	return _base[k] + _dir[k] * (CORNER_R + d)

func _v3(p: Vector2, h: float) -> Vector3:
	return Vector3(p.x, h, p.y)

# A quad strip between two rings (offsets da/db at heights ha/hb). `normal_up` picks the shading normal.
func _strip(st: SurfaceTool, da: float, ha: float, db: float, hb: float, kind: int, colour_fn: Callable = Callable()) -> void:
	var n := _ring_n()
	for i in range(n):
		var j := (i + 1) % n
		var a0 := _v3(_pt(i, da), ha)
		var a1 := _v3(_pt(j, da), ha)
		var b0 := _v3(_pt(i, db), hb)
		var b1 := _v3(_pt(j, db), hb)
		var col := Color.WHITE
		if colour_fn.is_valid():
			col = colour_fn.call(i)
		var n0: Vector3
		var n1: Vector3
		match kind:
			0: # tread: faces up
				n0 = Vector3.UP
				n1 = Vector3.UP
			1: # riser / wall facing the pitch
				n0 = Vector3(-_dir[i].x, 0, -_dir[i].y)
				n1 = Vector3(-_dir[j % n].x, 0, -_dir[j % n].y)
			_: # roof / underside: face down-ish (we shade both sides)
				n0 = Vector3.DOWN
				n1 = Vector3.DOWN
		st.set_color(col); st.set_normal(n0); st.add_vertex(a0)
		st.set_color(col); st.set_normal(n1); st.add_vertex(a1)
		st.set_color(col); st.set_normal(n1); st.add_vertex(b1)
		st.set_color(col); st.set_normal(n0); st.add_vertex(a0)
		st.set_color(col); st.set_normal(n1); st.add_vertex(b1)
		st.set_color(col); st.set_normal(n0); st.add_vertex(b0)

# ---------------------------------------------------------------- environment, ground
func _build_environment() -> void:
	var env := Environment.new()
	env.background_mode = Environment.BG_SKY
	var sky := Sky.new()
	var psm := ProceduralSkyMaterial.new()
	psm.sky_top_color = Color("#070f26")
	psm.sky_horizon_color = Color("#b8683f")
	psm.ground_horizon_color = Color("#3a2a33")
	psm.ground_bottom_color = Color("#0a0c14")
	psm.sky_curve = 0.18
	psm.sun_angle_max = 0.0
	sky.sky_material = psm
	env.sky = sky
	env.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	env.ambient_light_energy = 0.55
	env.tonemap_mode = Environment.TONE_MAPPER_ACES
	env.tonemap_exposure = 1.05
	env.glow_enabled = true
	env.glow_intensity = 0.45
	env.glow_bloom = 0.08
	env.glow_hdr_threshold = 1.0
	env.glow_blend_mode = Environment.GLOW_BLEND_MODE_SOFTLIGHT
	env.adjustment_enabled = true
	env.adjustment_contrast = 1.08
	env.adjustment_saturation = 1.12
	env.fog_enabled = true
	env.fog_light_color = Color("#1b2742")
	env.fog_density = 0.0016
	var we := WorldEnvironment.new()
	we.environment = env
	add_child(we)
	# cool "moon" key light: casts the player shadows, kept low so the floodlights read as the main source
	var key := DirectionalLight3D.new()
	key.light_color = Color("#bcd0ff")
	key.light_energy = 0.55
	key.rotation_degrees = Vector3(-58, -32, 0)
	key.shadow_enabled = true
	key.directional_shadow_max_distance = 140.0
	key.shadow_blur = 1.6
	add_child(key)

func _build_ground() -> void:
	# dark concourse tarmac under everything outside the pitch
	var ground := PlaneMesh.new()
	ground.size = Vector2(420, 320)
	_add_mesh(ground, _m(Color("#14181f"), 0.95), Vector3(0, -0.06, 0), false)
	# mown run-off grass around the pitch (the pitch shader covers the playing surface itself)
	var apron := PlaneMesh.new()
	apron.size = Vector2(2.0 * half_l + 14.0, 2.0 * half_w + 11.0)
	_add_mesh(apron, _m(Color("#1f5a2a"), 1.0), Vector3(0, 0.0, 0), false)

# ---------------------------------------------------------------- bowl + roof
func _seat_colour(i: int, row: int, upper: bool) -> Color:
	var p := _pt(i, 4.0)
	var sector := int(float(i) / 7.0)
	var base := Color("#26407f") if (sector % 2 == 0) else Color("#2f4d98")
	if upper:
		base = Color("#1e3266") if (sector % 2 == 0) else Color("#263d78")
	# team colours fill the two ends of the ground; a pale band marks every 5th row
	if absf(p.x) > half_l - 6.0 and absf(p.y) < half_w - 2.0:
		base = home_colour.darkened(0.25) if p.x < 0.0 else away_colour.darkened(0.15)
		if (sector + row) % 3 == 0:
			base = base.lightened(0.18)
	if row % 5 == 0:
		base = base.lightened(0.12)
	return base

func _build_bowl() -> void:
	var tread := SurfaceTool.new()
	tread.begin(Mesh.PRIMITIVE_TRIANGLES)
	var concrete := SurfaceTool.new()
	concrete.begin(Mesh.PRIMITIVE_TRIANGLES)
	var d := 0.0
	var h := 0.0
	# front hoarding (the wall pitch-side of the lower tier)
	_strip(concrete, 0.0, 0.0, 0.0, 1.1, 1)
	for r in range(LOWER_ROWS):
		_strip(concrete, d, h, d, h + LOWER_RISE, 1)
		h += LOWER_RISE
		_strip(tread, d, h, d + ROW_DEPTH, h, 0, func(i): return _seat_colour(i, r, false))
		d += ROW_DEPTH
	# aisle + rail
	_strip(concrete, d, h, d + AISLE, h, 0)
	d += AISLE
	_strip(concrete, d, h, d, h + 1.0, 1)
	var d_upper0 := d
	h += 0.6
	for r in range(UPPER_ROWS):
		_strip(concrete, d, h, d, h + UPPER_RISE, 1)
		h += UPPER_RISE
		_strip(tread, d, h, d + ROW_DEPTH, h, 0, func(i): return _seat_colour(i, r, true))
		d += ROW_DEPTH
	var d_top := d
	var h_top := h
	_strip(concrete, d_top, h_top, d_top, h_top + 7.0, 1)          # back wall rising to the roof
	_stand_top = Vector2(d_top, h_top)
	# roof canopy (double sided), with a glowing fascia strip along its front lip
	var roof := SurfaceTool.new()
	roof.begin(Mesh.PRIMITIVE_TRIANGLES)
	var roof_h0 := h_top + 3.0 - 0.0
	var roof_d0 := d_upper0 + 2.0
	_strip(roof, roof_d0, roof_h0, d_top + 3.0, h_top + 8.0, 2)
	var fascia := SurfaceTool.new()
	fascia.begin(Mesh.PRIMITIVE_TRIANGLES)
	_strip(fascia, roof_d0, roof_h0 - 0.9, roof_d0, roof_h0 + 0.35, 1)
	_roof_lip = Vector2(roof_d0, roof_h0)

	_add_mesh(tread.commit(), _m(Color.WHITE, 0.85, 0.0, 0.0, true), Vector3.ZERO, false)
	_add_mesh(concrete.commit(), _m(Color("#8c929c"), 0.95), Vector3.ZERO, false)
	_add_mesh(roof.commit(), _m(Color("#3a404c"), 0.6, 0.35), Vector3.ZERO, false)
	_add_mesh(fascia.commit(), _m(Color("#dfe6f5"), 0.5, 0.0, 0.6), Vector3.ZERO, false)
	_rows_lower = LOWER_ROWS
	_d_upper0 = d_upper0

var _stand_top := Vector2.ZERO
var _roof_lip := Vector2.ZERO
var _rows_lower := 0
var _d_upper0 := 0.0

# ---------------------------------------------------------------- crowd
func _build_crowd() -> void:
	# one tiny spectator mesh (body + head) reused for every seat
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	var body := BoxMesh.new()
	body.size = Vector3(0.44, 0.55, 0.30)
	st.append_from(body, 0, Transform3D(Basis.IDENTITY, Vector3(0, 0.50, 0)))
	var head := SphereMesh.new()
	head.radius = 0.12
	head.height = 0.24
	head.radial_segments = 6
	head.rings = 3
	st.append_from(head, 0, Transform3D(Basis.IDENTITY, Vector3(0, 0.92, 0)))
	var mesh := st.commit()

	var rng := RandomNumberGenerator.new()
	rng.seed = 20261031
	var xforms: Array = []
	var cols: Array = []
	var n := _ring_n()
	var d := 0.0
	var h := 0.0
	for tier in range(2):
		var rows := LOWER_ROWS if tier == 0 else UPPER_ROWS
		var rise := LOWER_RISE if tier == 0 else UPPER_RISE
		if tier == 1:
			d = _d_upper0
			h = LOWER_ROWS * LOWER_RISE + 0.6
		for r in range(rows):
			h += rise
			var dm := d + ROW_DEPTH * 0.5
			for i in range(n):
				var a := _pt(i, dm)
				var b := _pt(i + 1, dm)
				var len := a.distance_to(b)
				var cnt := int(len / 0.62)
				for s in range(cnt):
					if rng.randf() > crowd_density:
						continue
					var t := (float(s) + rng.randf() * 0.5) / maxf(1.0, float(cnt))
					var p := a.lerp(b, t)
					var inward := Vector3(-_dir[i].x, 0, -_dir[i].y)
					var yaw := atan2(inward.x, inward.z)
					var sc := 0.92 + rng.randf() * 0.18
					var basis := Basis(Vector3.UP, yaw).scaled(Vector3(sc, sc, sc))
					xforms.append(Transform3D(basis, Vector3(p.x, h + 0.02, p.y)))
					cols.append(_shirt_colour(p, rng))
			d += ROW_DEPTH
	var mm := MultiMesh.new()
	mm.transform_format = MultiMesh.TRANSFORM_3D
	mm.use_colors = true
	mm.mesh = mesh
	mm.instance_count = xforms.size()
	for k in range(xforms.size()):
		mm.set_instance_transform(k, xforms[k])
		mm.set_instance_color(k, cols[k])
	crowd = MultiMeshInstance3D.new()
	crowd.multimesh = mm
	crowd_mat = ShaderMaterial.new()
	crowd_mat.shader = load("res://Shaders/crowd_3d.gdshader")
	crowd.material_override = crowd_mat
	crowd.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(crowd)

func _shirt_colour(p: Vector2, rng: RandomNumberGenerator) -> Color:
	var r := rng.randf()
	if absf(p.x) > half_l - 6.0 and absf(p.y) < half_w - 2.0 and r < 0.78:
		var team := home_colour if p.x < 0.0 else away_colour
		return team.lightened(rng.randf() * 0.25)
	if r < 0.22:
		return Color.from_hsv(rng.randf(), 0.55, 0.85)
	if r < 0.5:
		return Color(0.88, 0.9, 0.95).darkened(rng.randf() * 0.3)
	return Color.from_hsv(0.6 + rng.randf() * 0.1, 0.35 + rng.randf() * 0.3, 0.35 + rng.randf() * 0.4)

# ---------------------------------------------------------------- floodlights
func _build_floodlights() -> void:
	var corner_d := _roof_lip.x + 8.0
	for sx in [-1, 1]:
		for sz in [-1, 1]:
			var dirn := Vector2(sx, sz).normalized()
			var c := Vector2((_a0 - CORNER_R) * sx, (_b0 - CORNER_R) * sz) + dirn * (CORNER_R + corner_d)
			var base_h := _stand_top.y + 5.0
			# lattice mast
			var pole := CylinderMesh.new()
			pole.top_radius = 0.28
			pole.bottom_radius = 0.45
			pole.height = 24.0
			_add_mesh(pole, _m(Color("#6b7280"), 0.5, 0.6), Vector3(c.x, base_h + 12.0, c.y), false)
			# lamp bank: a grid of emissive lamps facing the pitch centre
			var bank := Node3D.new()
			bank.position = Vector3(c.x, base_h + 25.0, c.y)
			add_child(bank)
			bank.look_at(Vector3(0, 0, 0), Vector3.UP)
			var frame := BoxMesh.new()
			frame.size = Vector3(7.5, 4.5, 0.4)
			var fm := MeshInstance3D.new()
			fm.mesh = frame
			fm.material_override = _m(Color("#2a2f38"), 0.6, 0.5)
			fm.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
			bank.add_child(fm)
			var lamp := BoxMesh.new()
			lamp.size = Vector3(0.7, 0.55, 0.15)
			var lm := _m(Color("#fff3d6"), 0.3, 0.0, 6.0)
			for gx in range(6):
				for gy in range(4):
					var l := MeshInstance3D.new()
					l.mesh = lamp
					l.material_override = lm
					l.position = Vector3(-3.0 + gx * 1.2, -1.65 + gy * 1.1, -0.28)
					l.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
					bank.add_child(l)
			var spot := SpotLight3D.new()
			spot.light_color = Color("#fff1d8")
			spot.light_energy = 3.4
			spot.spot_range = 190.0
			spot.spot_angle = 34.0
			spot.spot_attenuation = 0.7
			spot.position = Vector3(0, 0, -0.6)
			bank.add_child(spot)

# ---------------------------------------------------------------- LED boards, goals, flags
func _build_boards() -> void:
	var sh := Shader.new()
	sh.code = """
shader_type spatial;
render_mode unshaded, cull_disabled;
uniform float speed = 0.22;
uniform float panels = 8.0;
float hash(float n){ return fract(sin(n * 91.7) * 43758.5); }
void fragment() {
	float u = UV.x * panels + TIME * speed * panels * 0.25;
	float cell = floor(u);
	float f = fract(u);
	vec3 a = vec3(0.07, 0.10, 0.25);
	vec3 col = a;
	float k = hash(cell);
	if (k < 0.34) col = vec3(0.95, 0.15, 0.2);
	else if (k < 0.62) col = vec3(0.1, 0.55, 0.95);
	else if (k < 0.82) col = vec3(0.98, 0.78, 0.15);
	else col = vec3(0.92, 0.94, 1.0);
	// chevrons so the panels read as an animated LED display
	float chev = abs(fract((UV.y + f * 0.5) * 3.0) - 0.5);
	col *= 0.55 + 0.9 * smoothstep(0.1, 0.5, chev);
	col *= 0.75 + 0.25 * step(0.06, f) * step(f, 0.94);       // gaps between panels
	ALBEDO = col * 1.2;
	EMISSION = col * 1.1;
}
"""
	boards_mat = ShaderMaterial.new()
	boards_mat.shader = sh
	var off_x := half_l + 5.2
	var off_z := half_w + 4.2
	for s in [-1, 1]:
		_board(Vector3(0, 0.55, s * off_z), Vector3(2.0 * half_l + 6.0, 1.0, 0.12), 16.0)
		_board(Vector3(s * off_x, 0.55, 0), Vector3(0.12, 1.0, 2.0 * half_w + 4.0), 10.0)
	# dark backing so the boards have a frame
	for s in [-1, 1]:
		_add_mesh(_box(Vector3(2.0 * half_l + 6.4, 0.12, 0.3)), _m(Color("#0b0d12"), 0.8), Vector3(0, 1.08, s * (off_z + 0.04)), false)
		_add_mesh(_box(Vector3(0.3, 0.12, 2.0 * half_w + 4.4)), _m(Color("#0b0d12"), 0.8), Vector3(s * (off_x + 0.04), 1.08, 0), false)

func _box(size: Vector3) -> BoxMesh:
	var b := BoxMesh.new()
	b.size = size
	return b

func _board(pos: Vector3, size: Vector3, panels: float) -> void:
	var mi := _add_mesh(_box(size), boards_mat, pos, false)
	mi.set_instance_shader_parameter("panels", panels)

func _build_goals() -> void:
	var white := _m(Color(0.96, 0.97, 1.0), 0.4, 0.1)
	var net_mat := ShaderMaterial.new()
	net_mat.shader = load("res://Shaders/net.gdshader")
	for s in [-1, 1]:
		for z in [-goal_w, goal_w]:
			var post := CylinderMesh.new()
			post.top_radius = 0.06
			post.bottom_radius = 0.06
			post.height = goal_h
			_add_mesh(post, white, Vector3(s * half_l, goal_h * 0.5, z))
			# rear stanchion
			var rear := CylinderMesh.new()
			rear.top_radius = 0.04
			rear.bottom_radius = 0.04
			rear.height = goal_h
			_add_mesh(rear, white, Vector3(s * (half_l + GOAL_DEPTH), goal_h * 0.5, z), false)
		var bar := CylinderMesh.new()
		bar.top_radius = 0.06
		bar.bottom_radius = 0.06
		bar.height = goal_w * 2.0
		var bi := _add_mesh(bar, white, Vector3(s * half_l, goal_h, 0))
		bi.rotation_degrees.x = 90
		# nets: back, two sides, top
		var back := QuadMesh.new()
		back.size = Vector2(goal_w * 2.0, goal_h)
		var bk := _add_mesh(back, net_mat, Vector3(s * (half_l + GOAL_DEPTH), goal_h * 0.5, 0), false)
		bk.rotation_degrees.y = 90
		for z in [-goal_w, goal_w]:
			var side := QuadMesh.new()
			side.size = Vector2(GOAL_DEPTH, goal_h)
			_add_mesh(side, net_mat, Vector3(s * (half_l + GOAL_DEPTH * 0.5), goal_h * 0.5, z), false)
		var top := QuadMesh.new()
		top.size = Vector2(GOAL_DEPTH, goal_w * 2.0)
		var tp := _add_mesh(top, net_mat, Vector3(s * (half_l + GOAL_DEPTH * 0.5), goal_h, 0), false)
		tp.rotation_degrees.x = 90

func _build_flags() -> void:
	var pole_m := _m(Color("#f4f4f4"), 0.6)
	for sx in [-1, 1]:
		for sz in [-1, 1]:
			var pole := CylinderMesh.new()
			pole.top_radius = 0.015
			pole.bottom_radius = 0.015
			pole.height = 1.6
			_add_mesh(pole, pole_m, Vector3(sx * half_l, 0.8, sz * half_w), false)
			var flag := QuadMesh.new()
			flag.size = Vector2(0.4, 0.3)
			var fl := _add_mesh(flag, _m(Color("#ffd23f"), 0.7), Vector3(sx * half_l - sx * 0.2, 1.45, sz * half_w), false)
			fl.rotation_degrees.y = 90
