// Arena FC - goal net on the Sprite Forge goalnet mesh (v11.38).  UV = position on the net in mesh cells,
// UV2.x = how free the net is to move (0 on the frame / pegged ground line), UV2.y = panel.
// A goal bulges the net where the ball hits (impact, along the ball's direction) and a ripple runs out
// from there; the wind sways it a little.
shader_type spatial;
render_mode blend_mix, depth_draw_opaque, cull_disabled, diffuse_lambert, specular_disabled;

uniform vec4 net_color : source_color = vec4(0.95, 0.97, 1.0, 0.92);
uniform float thread = 0.075;          // line width in cells
uniform vec3 impact = vec3(1.6, 1.0, 0.0);
uniform vec3 impact_dir = vec3(1.0, 0.0, 0.0);
uniform float strength = 0.0;          // metres of bulge at the hit
uniform float since = 10.0;            // seconds since the hit
uniform float wind = 0.0;

void vertex() {
	float free = UV2.x;
	vec3 p = VERTEX;
	float d = length(p - impact);
	float t = since;
	float env = (1.0 - exp(-t * 28.0)) * exp(-t * 1.8);
	float bulge = strength * free * exp(-d * d / 0.36) * env * (0.75 + 0.25 * cos(t * 9.0));
	float ring = strength * 0.22 * free * env * sin(t * 13.0 - d * 8.0) * exp(-d * 0.9);
	VERTEX += impact_dir * bulge + NORMAL * ring;
	VERTEX += NORMAL * free * (0.006 + wind * 0.02) * sin(TIME * 1.6 + p.z * 1.1 + p.y * 0.7);
}

void fragment() {
	// diamond mesh: the cell grid turned 45 degrees
	vec2 r = vec2(UV.x + UV.y, UV.x - UV.y) * 0.70710678;
	vec2 d = abs(fract(r) - 0.5);
	float dist = 0.5 - max(d.x, d.y);
	vec2 fw = fwidth(r);
	float aa = max(fw.x, fw.y);
	float line = 1.0 - smoothstep(thread * 0.5, thread * 0.5 + aa, dist);
	// far away the threads merge into a fine veil instead of shimmering
	float veil = clamp((aa - 0.15) * 2.5, 0.0, 1.0);
	float a = mix(line, thread * 3.2, veil);
	if (!FRONT_FACING) NORMAL = -NORMAL;            // a thread is lit the same from either side
	ALBEDO = net_color.rgb;
	ALPHA = a * net_color.a;
	ROUGHNESS = 0.85;
}
