// Arena FC - football kit on the Sprite Forge tailor atlas (sforge.tailor / sforge.kitdesign v11.30).
// One shader for shirt, shorts, socks and boots: the masks come from Sprite Forge, the colours,
// pattern, name and number from the player's CharacterSpec.  Layout: Data/textures/kit/kit_layout.json.
shader_type spatial;
render_mode cull_disabled, diffuse_burley, specular_schlick_ggx;

uniform sampler2D pattern_tex : hint_default_black, filter_linear_mipmap;   // L: secondary colour
uniform sampler2D detail_tex : hint_default_white, filter_linear_mipmap;    // R trim, G boot detail, B fabric
uniform sampler2D glyph_tex : hint_default_black, filter_linear_mipmap;     // R fill, G outline

uniform vec3 primary : source_color = vec3(0.84, 0.15, 0.24);
uniform vec3 secondary : source_color = vec3(1.0);
uniform vec3 trim : source_color = vec3(0.08, 0.13, 0.24);
uniform vec3 shorts : source_color = vec3(0.08, 0.13, 0.24);
uniform vec3 socks : source_color = vec3(1.0);
uniform vec3 boots : source_color = vec3(0.07);
uniform vec3 boot_detail : source_color = vec3(0.92);
uniform vec3 print_fill : source_color = vec3(1.0);
uniform vec3 print_edge : source_color = vec3(0.05);
uniform float roughness_cloth = 0.78;
uniform float roughness_boot = 0.32;
uniform float wet = 0.0;          // rain darkens and glosses the cloth
uniform float dirt = 0.0;         // grass and mud stains build up on shorts and socks

// cloth flutter (Sprite Forge tailor v11.36): UV2.x = amplitude along the normal (m, negative on the
// turned-in hems), UV2.y = phase round the hem.  Zero on the collar, waistband, socks and boots.
uniform float flutter_speed = 0.0;   // 0 standing .. 1 sprinting (set per player each frame)
uniform float wind = 0.0;            // 0 calm .. 1 gale
uniform float flutter_seed = 0.0;    // de-syncs the players

uniform int number = 10;
uniform int name_len = 0;
uniform int name_chars[14];

// glyph grid (kit_layout.json)
const vec2 GRID = vec2(8.0, 5.0);
const float CELL_ASPECT = 96.0 / 144.0;
// print rectangles (u0, v0, u1, v1)
const vec4 BACK_NAME = vec4(0.60, 0.075, 0.90, 0.135);
const vec4 BACK_NUMBER = vec4(0.62, 0.15, 0.88, 0.36);
const vec4 FRONT_NUMBER = vec4(0.21, 0.17, 0.29, 0.25);
const vec4 SHORTS_NUMBER = vec4(0.53, 0.53, 0.58, 0.58);
const vec4 CREST = vec4(0.31, 0.065, 0.37, 0.125);

float hash12(vec2 p) { return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453); }

// sample one glyph cell at local coords q (0..1)
vec2 glyph(int idx, vec2 q) {
	vec2 cell = vec2(float(idx % 8), float(idx / 8));
	vec2 uv = (cell + clamp(q, vec2(0.0), vec2(1.0))) / GRID;
	return texture(glyph_tex, uv).rg;
}

// text in a rect: returns (fill, outline)
vec2 print_text(vec2 uv, vec4 r, int count, int which) {
	if (uv.x < r.x || uv.x >= r.z || uv.y < r.y || uv.y >= r.w || count <= 0) return vec2(0.0);
	float w = r.z - r.x, h = r.w - r.y;
	float cw = min(w / float(count), h * CELL_ASPECT);
	float x0 = r.x + (w - cw * float(count)) * 0.5;
	float k = floor((uv.x - x0) / cw);
	if (k < 0.0 || k >= float(count)) return vec2(0.0);
	vec2 q = vec2((uv.x - x0 - k * cw) / cw, (uv.y - r.y) / h);
	int ki = int(k);
	int idx = 39;
	if (which == 0) {
		idx = name_chars[min(ki, 13)];
	} else {
		int tens = number / 10;
		idx = count == 2 ? (ki == 0 ? tens : number - tens * 10) : number;
	}
	return glyph(idx, q);
}

void vertex() {
	float a = UV2.x;
	if (a != 0.0) {
		float ph = UV2.y * 6.2831853;
		float drive = clamp(flutter_speed + wind * 0.6, 0.0, 1.4);
		float t = TIME * (4.0 + 10.0 * flutter_speed) + flutter_seed * 17.0;
		// a ripple running round the hem plus a slower billow; barely there standing still
		float w = sin(t + ph * 3.0) * 0.6 + sin(t * 1.63 - ph * 5.0 + 1.3) * 0.4;
		VERTEX += NORMAL * a * (0.12 + 0.88 * drive) * w;
	}
}

void fragment() {
	vec2 uv = UV;
	vec3 det = texture(detail_tex, uv).rgb;
	bool shirt = uv.y < 0.5 || (uv.y < 0.75 && uv.x < 0.5);
	bool is_shorts = uv.y >= 0.5 && uv.y < 0.75 && uv.x >= 0.5;
	bool is_socks = uv.y >= 0.75 && uv.x < 0.5;
	bool is_boot = uv.y >= 0.75 && uv.x >= 0.5;
	vec3 col;
	float rough = roughness_cloth;
	if (shirt) {
		float m = texture(pattern_tex, uv).r;
		col = mix(primary, secondary, m);
	} else if (is_shorts) {
		col = shorts;
	} else if (is_socks) {
		col = socks;
	} else {
		col = boots;
		rough = roughness_boot;
	}
	if (!is_boot) col = mix(col, trim, det.r);
	else col = mix(col, boot_detail, step(0.2, det.g));
	// printing: number on the back, front and shorts, name across the shoulders
	int ndig = number >= 10 ? 2 : (number > 0 ? 1 : 0);   // 0 = no number (officials)
	vec2 p = print_text(uv, BACK_NUMBER, ndig, 1);
	p = max(p, print_text(uv, FRONT_NUMBER, ndig, 1));
	p = max(p, print_text(uv, SHORTS_NUMBER, ndig, 1));
	p = max(p, print_text(uv, BACK_NAME, name_len, 0));
	col = mix(col, print_edge, p.g * (1.0 - p.r));
	col = mix(col, print_fill, p.r);
	// crest: an original shield in the trim colour with the secondary inside
	if (uv.x >= CREST.x && uv.x < CREST.z && uv.y >= CREST.y && uv.y < CREST.w) {
		vec2 q = (uv - CREST.xy) / (CREST.zw - CREST.xy) * 2.0 - 1.0;
		float shield = step(abs(q.x), 0.8 - max(q.y, 0.0) * 0.7) * step(-0.85, q.y);
		float inner = step(abs(q.x), 0.58 - max(q.y, 0.0) * 0.6) * step(-0.62, q.y);
		col = mix(col, trim, shield);
		col = mix(col, secondary, inner * 0.9);
		rough = mix(rough, 0.45, shield);
	}
	// cloth weave + seams; grass stains on the shorts and socks as the match goes on
	col *= det.b;
	if (dirt > 0.0 && (is_shorts || is_socks)) {
		float n = hash12(floor(uv * 160.0)) * 0.6 + hash12(floor(uv * 23.0)) * 0.4;
		float s = smoothstep(1.0 - dirt * 0.6, 1.0, n);
		col = mix(col, vec3(0.24, 0.30, 0.13), s * 0.55);
	}
	col *= 1.0 - wet * 0.22;
	ALBEDO = col;
	ROUGHNESS = mix(rough, rough * 0.55, wet);
	SPECULAR = is_boot ? 0.6 : 0.35;
	// a sheen at grazing angles reads as knitted polyester under floodlights
	float fres = pow(1.0 - clamp(dot(NORMAL, VIEW), 0.0, 1.0), 3.0);
	RIM = is_boot ? 0.1 : 0.35 * fres + 0.1;
	RIM_TINT = 0.5;
}
