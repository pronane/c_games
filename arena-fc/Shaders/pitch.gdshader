shader_type spatial;
render_mode cull_back, diffuse_burley, specular_schlick_ggx;

uniform vec3 grass_a : source_color = vec3(0.075, 0.255, 0.105);
uniform vec3 grass_b : source_color = vec3(0.085, 0.28, 0.115);
uniform float line_width = 0.11;
uniform float wear_amount : hint_range(0.0, 1.0) = 0.25;
uniform float wetness : hint_range(0.0, 1.0) = 0.0;

varying vec3 world_pos;

void vertex() {
	world_pos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
}

float line_at(float value, float target, float w) {
	return 1.0 - smoothstep(0.0, w, abs(value - target));
}

float hash(vec2 p) {
	return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453);
}

void fragment() {
	float x = world_pos.x;
	float z = world_pos.z;
	float w = line_width;
	float stripe = mod(floor((x + 52.5) / 6.56), 2.0);
	vec3 grass = mix(grass_a, grass_b, stripe);
	// Multi-scale noise for natural grass variation (breaks up flat stripes).
	float n1 = fract(sin(dot(floor(world_pos.xz * 7.0), vec2(12.9898, 78.233))) * 43758.5453);
	float n2 = fract(sin(dot(floor(world_pos.xz * 23.0), vec2(39.346, 11.135))) * 24634.6345);
	float n3 = fract(sin(dot(floor(world_pos.xz * 61.0), vec2(73.156, 32.819))) * 31543.1234);
	grass *= 0.88 + 0.10 * n1 + 0.08 * n2 + 0.06 * n3;

	// Phase 3.2: normal-mapped grass detail (procedural micro-normal).
	vec2 micro = world_pos.xz * 28.0;
	float h1 = hash(floor(micro));
	float h2 = hash(floor(micro + vec2(1.0, 0.0)));
	float h3 = hash(floor(micro + vec2(0.0, 1.0)));
	NORMAL_MAP = vec3((h2 - h1) * 0.35, (h3 - h1) * 0.35, 1.0);

	// Phase 3.2: wear — centre of pitch and penalty areas are worn.
	float centre_wear = 1.0 - smoothstep(0.0, 18.0, length(vec2(x, z)));
	float pen_wear = (1.0 - smoothstep(0.0, 12.0, abs(abs(x) - 41.5))) * (1.0 - smoothstep(0.0, 14.0, abs(z)));
	float wear = max(centre_wear, pen_wear) * wear_amount;
	grass = mix(grass, vec3(0.18, 0.22, 0.12), wear * 0.45);

	// Phase 3.2: wet reflections — lower roughness when wet.
	float rough = mix(0.95, 0.35, wetness);

	float line = 0.0;
	float ax = abs(x), az = abs(z);
	line = max(line, line_at(az, 34.0, w) * step(ax, 52.6));          // touch lines
	line = max(line, line_at(ax, 52.5, w) * step(az, 34.1));           // goal lines
	line = max(line, line_at(x, 0.0, w) * step(az, 34.0));             // halfway
	line = max(line, line_at(length(vec2(x, z)), 9.15, w));            // centre circle
	line = max(line, 1.0 - smoothstep(0.10, 0.19, length(vec2(x, z))));// centre spot

	float pen = step(36.0, ax);
	line = max(line, line_at(ax, 36.0, w) * step(az, 20.16));          // penalty box front
	line = max(line, line_at(az, 20.16, w) * pen);                      // penalty box sides
	float six = step(47.0, ax);
	line = max(line, line_at(ax, 47.0, w) * step(az, 9.16));
	line = max(line, line_at(az, 9.16, w) * six);
	line = max(line, 1.0 - smoothstep(0.10, 0.19, length(vec2(ax - 41.5, z)))); // penalty spots
	// penalty arcs (outside the box)
	float darc = length(vec2(ax - 41.5, z));
	line = max(line, line_at(darc, 9.15, w) * step(36.0, darc) * step(ax, 36.0));
	// corner arcs
	vec2 corner = vec2(52.5 - ax, 34.0 - az);
	line = max(line, line_at(length(corner), 1.0, w));

	line *= step(ax, 52.62) * step(az, 34.12);
	ALBEDO = mix(grass, vec3(0.93, 0.95, 0.93), clamp(line, 0.0, 1.0));
	ROUGHNESS = rough;
	SPECULAR = mix(0.15, 0.6, wetness);
}
