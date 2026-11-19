shader_type spatial;
render_mode cull_back, unshaded;

uniform vec3 color_a : source_color = vec3(0.1, 0.6, 1.0);
uniform vec3 color_b : source_color = vec3(0.0, 0.2, 0.5);
uniform float scroll_speed = 0.3;

void fragment() {
	// Scrolling LED pattern: diagonal stripes moving horizontally.
	float scroll = UV.x * 8.0 - TIME * scroll_speed * 4.0;
	float stripe = sin(scroll * 3.14159) * 0.5 + 0.5;
	vec3 col = mix(color_a, color_b, stripe);
	// Add scanline effect (LED dots).
	float scan = sin(UV.y * 60.0) * 0.15 + 0.85;
	ALBEDO = col * scan;
}
