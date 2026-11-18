shader_type spatial;
render_mode cull_back;
uniform vec3 base_color : source_color = vec3(0.96, 0.97, 0.95);
uniform vec3 patch_color : source_color = vec3(0.08, 0.09, 0.11);
uniform float spin_blur : hint_range(0.0, 1.0) = 0.0;

varying vec3 local_pos;

void vertex() {
	local_pos = VERTEX;
}

void fragment() {
	// Use 3D direction for seamless football pattern (no UV distortion).
	vec3 dir = normalize(local_pos);
	
	// Icosahedral-ish pattern: project onto cube faces for even distribution.
	vec3 abs_dir = abs(dir);
	float max_axis = max(abs_dir.x, max(abs_dir.y, abs_dir.z));
	vec2 uv;
	if (max_axis == abs_dir.x) {
		uv = dir.zy / dir.x;
	} else if (max_axis == abs_dir.y) {
		uv = dir.xz / dir.y;
	} else {
		uv = dir.xy / dir.z;
	}
	
	// Hexagonal tiling for football panels.
	vec2 p = uv * 2.2;
	vec2 cell = floor(p);
	vec2 f = fract(p) - 0.5;
	// Offset alternate rows for hex layout.
	f.x += mod(cell.y, 2.0) * 0.5;
	f.x = fract(f.x + 0.5) - 0.5;
	float d = length(f * vec2(1.0, 1.15));
	
	// Black pentagons at cell centers, white hexagons between.
	float patch = 1.0 - smoothstep(0.22, 0.28, d);
	float seam = 1.0 - smoothstep(0.0, 0.03, abs(d - 0.25));
	
	ALBEDO = mix(base_color, patch_color, patch);
	ALBEDO *= 1.0 - seam * 0.3;

	// Panel bump at seams.
	float bump = seam * 0.12;
	NORMAL_MAP = vec3(0.0, 0.0, 1.0 - bump);

	// Spin blur — reduce contrast when spinning fast.
	if (spin_blur > 0.01) {
		float blur_mix = spin_blur * 0.35;
		ALBEDO = mix(ALBEDO, vec3(dot(ALBEDO, vec3(0.333))), blur_mix);
	}

	ROUGHNESS = 0.38;
	SPECULAR = 0.55;
}
