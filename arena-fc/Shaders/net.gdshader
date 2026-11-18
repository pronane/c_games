shader_type spatial;
render_mode blend_mix, depth_draw_always, cull_disabled, unshaded;
uniform vec4 net_color : source_color = vec4(0.88, 0.94, 1.0, 0.55);
uniform float ripple : hint_range(0.0, 1.0) = 0.0;

varying vec2 uv_pos;

void vertex() {
	uv_pos = UV;
	// Phase 3.3: net ripple — displace vertices when the ball hits the net.
	if (ripple > 0.01) {
		float wave = sin(uv_pos.x * 20.0 + TIME * 18.0) * ripple * 0.08;
		VERTEX.z += wave;
	}
}

void fragment() {
	vec2 f = fract(UV * vec2(46.0, 16.0));
	vec2 d = min(f, 1.0 - f);
	float line = 1.0 - smoothstep(0.0, 0.075, min(d.x, d.y));
	ALBEDO = net_color.rgb;
	ALPHA = line * net_color.a;
}
