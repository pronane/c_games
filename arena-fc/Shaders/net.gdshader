shader_type spatial;
render_mode blend_mix, depth_draw_always, cull_disabled, unshaded;
uniform vec4 net_color : source_color = vec4(0.88, 0.94, 1.0, 0.55);
void fragment() {
	vec2 f = fract(UV * vec2(46.0, 16.0));
	vec2 d = min(f, 1.0 - f);
	float line = 1.0 - smoothstep(0.0, 0.075, min(d.x, d.y));
	ALBEDO = net_color.rgb;
	ALPHA = line * net_color.a;
}
