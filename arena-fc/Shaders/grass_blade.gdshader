shader_type spatial;
render_mode cull_back, diffuse_lambert;

uniform float wind_strength = 0.15;
uniform float wind_speed = 1.8;

void vertex() {
	// Wind sway: bend blade tip based on height (UV.y) and world position.
	float bend = UV.y * UV.y; // Quadratic: base stays, tip bends
	float sway = sin(TIME * wind_speed + float(INSTANCE_ID) * 0.7) * wind_strength;
	float gust = sin(TIME * 0.5 + VERTEX.x * 0.1) * 0.05;
	VERTEX.x += (sway + gust) * bend;
	VERTEX.z += cos(TIME * wind_speed * 0.8 + float(INSTANCE_ID) * 0.5) * wind_strength * 0.5 * bend;
}

void fragment() {
	// Gradient: dark base to light tip (fake AO + sunlight).
	vec3 base_col = vec3(0.06, 0.22, 0.09);
	vec3 tip_col = vec3(0.18, 0.45, 0.18);
	ALBEDO = mix(base_col, tip_col, UV.y);
	ROUGHNESS = 0.9;
}
