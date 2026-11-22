// Arena FC - pitch-side LED ring (Sprite Forge sforge.stadium ad_ring + sforge.adboards atlas, v11.32).
// UV.x runs once round the ground, UV.y top->bottom.  The ring is cut into boards; each shows one sponsor
// row of the atlas, scrolling, and the whole ring cuts to the next set every `cycle` seconds (a goal
// flashes the home / away colours via `flash`).
shader_type spatial;
render_mode unshaded, cull_disabled;
uniform sampler2D atlas : source_color, filter_linear_mipmap, repeat_enable;
uniform float rows = 8.0;
uniform float boards = 36.0;
uniform float cycle = 9.0;
uniform float scroll = 0.08;
uniform float brightness = 1.15;
uniform float flash = 0.0;
uniform vec3 flash_a : source_color = vec3(0.84, 0.15, 0.24);
uniform vec3 flash_b : source_color = vec3(1.0);
float hash(float n) { return fract(sin(n * 91.7) * 43758.5); }
void fragment() {
	float b = floor(UV.x * boards);
	float set_i = floor(TIME / cycle);
	float row = floor(hash(b * 0.37 + set_i * 1.31) * rows);
	float lx = fract(UV.x * boards + TIME * scroll);
	vec3 col = texture(atlas, vec2(lx, (row + clamp(UV.y, 0.02, 0.98)) / rows)).rgb;
	// LED pixel grid and a soft edge between boards
	vec2 px = fract(vec2(UV.x * boards * 160.0, UV.y * 24.0));
	col *= 0.82 + 0.18 * step(0.18, px.x) * step(0.18, px.y);
	float edge = smoothstep(0.0, 0.004, fract(UV.x * boards)) * smoothstep(0.0, 0.004, 1.0 - fract(UV.x * boards));
	col *= 0.4 + 0.6 * edge;
	if (flash > 0.0) col = mix(col, mod(floor(TIME * 4.0 + b), 2.0) < 1.0 ? flash_a : flash_b, flash);
	ALBEDO = col * brightness;
}
