// Instanced spectators: per-instance colour (MultiMesh colours), idle sway, and a bounce that scales
// with `excite` (0 = sitting calmly, 1 = on their feet after a goal). `wave` sweeps a Mexican wave.
shader_type spatial;
render_mode cull_back, diffuse_lambert, specular_disabled;

uniform float excite : hint_range(0.0, 1.0) = 0.12;
uniform float wave_speed = 0.0;       // 0 = off
uniform vec3 skin : source_color = vec3(0.80, 0.60, 0.46);

varying float v_head;
varying float v_lit;

float hash(float n) { return fract(sin(n * 12.9898) * 43758.5453); }

void vertex() {
	float id = float(INSTANCE_ID);
	float ph = hash(id);
	v_head = step(0.78, VERTEX.y);
	float t = TIME * (2.6 + ph * 1.8) + ph * 40.0;
	float bounce = max(0.0, sin(t)) * (0.012 + 0.20 * excite);
	float w = 0.0;
	if (wave_speed > 0.0) {
		vec3 wp = (MODEL_MATRIX * vec4(0.0, 0.0, 0.0, 1.0)).xyz;
		w = pow(max(0.0, sin((wp.x + wp.z) * 0.09 - TIME * wave_speed)), 6.0) * 0.28;
	}
	// everything above the seat lifts; the lower body stays put
	float lift = smoothstep(0.1, 0.5, VERTEX.y);
	VERTEX.y += (bounce + w) * lift;
	VERTEX.x += sin(t * 0.5) * 0.02 * lift * (0.4 + excite);
	v_lit = 1.0;
}

void fragment() {
	vec3 shirt = COLOR.rgb;
	ALBEDO = mix(shirt, skin * (0.8 + 0.3 * fract(shirt.r * 7.0)), v_head);
	ROUGHNESS = 1.0;
}
