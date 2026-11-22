// Arena FC - instanced spectators from Sprite Forge sforge.crowd (v11.32).
// UV2 (TEXCOORD_1): x part (0 skin, .25 hair, .5 shirt, .75 trousers, 1 cloth), y arm weight; side = sign(x),
// height = y.  (COLOR_0 mirrors them but is sRGB-converted on import, so it is not read here.)
// INSTANCE_CUSTOM: rgb shirt colour, a = end + seed (floor: 0 home end, 1 side, 2 away end; fract: seed).
// (Godot multiplies a MultiMesh's instance colour into COLOR, which carries the part channels, so the
// shirt rides in the custom data instead.)
// `excite` lifts the crowd to its feet and raises arms (a goal), `chant` claps arms above heads at the ends.
shader_type spatial;
render_mode cull_back, diffuse_lambert, specular_disabled;

uniform float excite : hint_range(0.0, 1.0) = 0.12;
uniform float chant : hint_range(0.0, 1.0) = 0.0;
uniform float wave_speed = 0.0;
uniform vec3 home : source_color = vec3(0.84, 0.15, 0.24);
uniform vec3 away : source_color = vec3(0.11, 0.30, 0.85);
const vec2 SHOULDER = vec2(0.21, 0.80);

varying float v_part;
varying vec3 v_shirt;
varying vec3 v_skin;
varying vec3 v_hair;

vec3 rot_x(vec3 p, float a) { float c = cos(a), s = sin(a); return vec3(p.x, p.y * c - p.z * s, p.y * s + p.z * c); }

void vertex() {
	float seed = fract(INSTANCE_CUSTOM.a);
	float endv = floor(INSTANCE_CUSTOM.a) - 1.0;
	float part = UV2.x, armw = UV2.y, side = step(0.0, VERTEX.x), hgt = clamp(VERTEX.y, 0.0, 1.0);
	float t = TIME * (2.2 + seed * 1.6) + seed * 37.0;
	// how worked-up this fan is: the ends sing all match, everyone goes up for a goal
	float fervour = clamp(excite + chant * abs(endv) * 0.6, 0.0, 1.0) * (0.55 + 0.45 * fract(seed * 7.13));
	float stand = smoothstep(0.35, 0.8, fervour);
	float bounce = max(0.0, sin(t * 1.6)) * 0.14 * fervour;
	float wave = 0.0;
	if (wave_speed > 0.0) {
		vec3 wp = (MODEL_MATRIX * vec4(0.0, 0.0, 0.0, 1.0)).xyz;
		wave = pow(max(0.0, sin((wp.x + wp.z) * 0.08 - TIME * wave_speed)), 6.0);
	}
	vec3 v = VERTEX;
	// arms: rotate about the shoulder; up with the fervour, a clap/punch rhythm on top
	if (armw > 0.1) {
		float sgn = side > 0.5 ? 1.0 : -1.0;
		vec3 piv = vec3(sgn * SHOULDER.x, SHOULDER.y, 0.0);
		float raise = (fervour * 2.7 + wave * 2.6) * (0.7 + 0.3 * sin(t * 2.0 + sgn));
		v = piv + rot_x(v - piv, -raise);
	}
	// rise out of the seat: the body above the hips lifts and the thighs drop
	v.y += (stand * 0.42 + bounce + wave * 0.35) * smoothstep(0.0, 0.25, hgt + 0.1);
	v.x += sin(t * 0.5) * 0.02 * (0.3 + fervour) * hgt;
	VERTEX = v;
	v_part = part;
	v_shirt = part > 0.9 ? (endv < -0.5 ? home : endv > 0.5 ? away : INSTANCE_CUSTOM.rgb) : INSTANCE_CUSTOM.rgb;
	float st = fract(seed * 13.7);
	v_skin = mix(vec3(0.95, 0.78, 0.64), vec3(0.32, 0.20, 0.13), st * st);
	v_hair = mix(vec3(0.05, 0.04, 0.03), vec3(0.55, 0.38, 0.2), fract(seed * 29.3) * fract(seed * 5.1));
}

void fragment() {
	vec3 c = v_shirt;
	if (v_part < 0.12) c = v_skin;
	else if (v_part < 0.37) c = v_hair;
	else if (v_part < 0.62) c = v_shirt;
	else if (v_part < 0.87) c = vec3(0.10, 0.12, 0.16);
	ALBEDO = c;
	ROUGHNESS = 1.0;
}
