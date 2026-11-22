// Arena FC - stand seating from Sprite Forge sforge.stadium (v11.32): vertex colours carry the sections,
// row bands and aisles; alpha marks the ends (.25 home, .5 away), baked as a grey level tinted here with the
// two clubs' colours so every fixture's ground wears its teams.
shader_type spatial;
render_mode cull_disabled, diffuse_burley, specular_disabled;
uniform vec3 home : source_color = vec3(0.84, 0.15, 0.24);
uniform vec3 away : source_color = vec3(0.11, 0.30, 0.85);
uniform float seat_grain = 0.08;
// Godot's glTF import stores vertex colours sRGB-encoded: back to linear for lighting
vec3 to_linear(vec3 c) { return mix(c / 12.92, pow((c + 0.055) / 1.055, vec3(2.4)), step(0.04045, c)); }
void fragment() {
	vec3 c = to_linear(COLOR.rgb);
	float a = COLOR.a;
	if (a < 0.4) c = home * (0.45 + 0.65 * c.r);
	else if (a < 0.75) c = away * (0.45 + 0.65 * c.r);
	// individual seats along the row read at broadcast distance as a fine grain
	vec3 w = (INV_VIEW_MATRIX * vec4(VERTEX, 1.0)).xyz;
	float seat = step(0.5, fract((w.x + w.z) * 1.82));
	c *= 1.0 - seat_grain * seat;
	ALBEDO = c;
	ROUGHNESS = 0.8;
}
