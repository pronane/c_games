shader_type spatial;
render_mode cull_back;
uniform vec3 base_color : source_color = vec3(0.95, 0.96, 0.94);
uniform vec3 patch_color : source_color = vec3(0.055, 0.065, 0.08);
void fragment() {
	vec2 p = UV * vec2(11.0, 7.0);
	vec2 cell = floor(p);
	vec2 f = fract(p) - 0.5;
	// stagger odd rows to fake a truncated-icosahedron layout
	f.x += mod(cell.y, 2.0) * 0.5;
	f.x = fract(f.x + 0.5) - 0.5;
	float d = length(f * vec2(1.0, 1.25));
	float patch = 1.0 - smoothstep(0.27, 0.31, d);
	float seam = 1.0 - smoothstep(0.0, 0.035, abs(d - 0.30));
	ALBEDO = mix(base_color, patch_color, patch);
	ALBEDO *= 1.0 - seam * 0.35;
	ROUGHNESS = 0.42;
	SPECULAR = 0.5;
}
