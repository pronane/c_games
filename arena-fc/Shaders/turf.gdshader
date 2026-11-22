// Arena FC - turf from Sprite Forge sforge.pitch (v11.33): R line markings, G mowing band, B wear.
// The mowing bands are shaded by viewing direction like real cut grass (a band is light seen one way,
// dark the other); wear browns the goalmouths and the assistants' channels; rain darkens and glosses it.
shader_type spatial;
render_mode cull_back, diffuse_burley, specular_schlick_ggx;

uniform sampler2D turf : filter_linear_mipmap_anisotropic, repeat_disable;
uniform vec2 extent = vec2(56.5, 38.0);          // half size the texture covers (m)
uniform vec3 grass : source_color = vec3(0.06, 0.205, 0.08);
uniform vec3 worn : source_color = vec3(0.20, 0.21, 0.11);
uniform vec3 paint : source_color = vec3(0.93, 0.95, 0.93);
uniform float mow_contrast = 0.13;
uniform float wear_amount : hint_range(0.0, 1.0) = 0.35;
uniform float wetness : hint_range(0.0, 1.0) = 0.0;

varying vec3 world_pos;
float hash(vec2 p) { return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453); }

void vertex() { world_pos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz; }

void fragment() {
	vec2 uv = (world_pos.xz + extent) / (2.0 * extent);
	vec3 t = texture(turf, uv).rgb;
	// a 12 cm line is under a pixel far away: widen the lookup by the pixel's footprint so distant lines
	// stay solid instead of breaking into dashes
	vec2 fw = fwidth(uv) * 0.6;
	float lines = max(t.r, max(max(texture(turf, uv + vec2(fw.x, 0.0)).r, texture(turf, uv - vec2(fw.x, 0.0)).r),
	                          max(texture(turf, uv + vec2(0.0, fw.y)).r, texture(turf, uv - vec2(0.0, fw.y)).r)));
	// cut grass: the blade lean flips the band's brightness with the view direction along the pitch
	vec3 view_w = (INV_VIEW_MATRIX * vec4(VIEW, 0.0)).xyz;
	float facing = sign(view_w.x + 1e-4);
	float band = (t.g * 2.0 - 1.0) * facing;
	vec3 g = grass * (1.0 + mow_contrast * band);
	// blades: fine multi-scale variation and a micro-normal
	float n1 = hash(floor(world_pos.xz * 7.0)), n2 = hash(floor(world_pos.xz * 23.0) + 3.1), n3 = hash(floor(world_pos.xz * 61.0) + 7.7);
	g *= 0.93 + 0.05 * n1 + 0.04 * n2 + 0.03 * n3;
	vec2 micro = world_pos.xz * 28.0;
	float h1 = hash(floor(micro)), h2 = hash(floor(micro + vec2(1.0, 0.0))), h3 = hash(floor(micro + vec2(0.0, 1.0)));
	NORMAL_MAP = vec3(0.5 + (h2 - h1) * 0.3, 0.5 + (h3 - h1) * 0.3, 1.0);
	float w = clamp(t.b * wear_amount * 1.6, 0.0, 1.0);
	g = mix(g, worn * (0.9 + 0.2 * n2), w * 0.75);
	g *= 1.0 - wetness * 0.18;
	vec3 c = mix(g, paint * (0.94 + 0.06 * n3), smoothstep(0.2, 0.7, lines));
	ALBEDO = c;
	ROUGHNESS = mix(0.92, 0.38, wetness) + w * 0.05;
	SPECULAR = mix(0.18, 0.55, wetness);
}
