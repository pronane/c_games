// Arena FC - corner flag cloth (Sprite Forge goalnet.corner_flag, v11.39): UV2.x = distance from the pole.
shader_type spatial;
render_mode cull_disabled;
uniform vec3 colour : source_color = vec3(0.98, 0.82, 0.1);
uniform vec3 colour2 : source_color = vec3(0.85, 0.1, 0.12);
uniform float wind = 0.3;
uniform float phase = 0.0;

void vertex() {
	float u = UV2.x;
	float t = TIME * (2.2 + wind * 3.0) + phase;
	float flap = sin(t - u * 6.0) * 0.07 + sin(t * 1.7 - u * 9.0 + UV2.y * 2.0) * 0.03;
	VERTEX.z += flap * u * (0.4 + wind);
	VERTEX.x -= u * u * 0.04 * (1.0 - wind);          // hangs a little when calm
	VERTEX.y -= u * u * 0.08 * (1.0 - wind);
}

void fragment() {
	// two-tone diagonal, the classic corner flag
	float k = step(UV.x, UV.y);
	ALBEDO = mix(colour, colour2, k);
	ROUGHNESS = 0.7;
}
