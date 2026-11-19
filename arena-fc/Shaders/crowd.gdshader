shader_type spatial;
render_mode cull_back, diffuse_lambert;
uniform float sway = 0.045;
uniform float celebrate = 0.0; // 0 = normal, 1 = goal celebration (jump + arms)
uniform float wave_speed = 1.5; // Mexican wave speed

void vertex() {
	float id = float(INSTANCE_ID);
	// Base sway (idle)
	float sway_offset = sin(TIME * 2.2 + id * 0.83) * sway;
	
	// Mexican wave: sine wave traveling across the crowd by world position.
	// Uses instance position (from MultiMesh transform) for wave phase.
	vec3 instance_pos = (MODEL_MATRIX * vec4(0.0, 0.0, 0.0, 1.0)).xyz;
	float wave_phase = instance_pos.x * 0.15 + instance_pos.z * 0.1;
	float wave = sin(TIME * wave_speed - wave_phase) * 0.5 + 0.5;
	wave = pow(wave, 3.0) * 0.12; // Sharp peak, smooth trough
	
	// Celebration: jump higher + faster sway.
	float celeb_jump = celebrate * (0.15 + 0.1 * sin(TIME * 8.0 + id * 1.7));
	float celeb_sway = celebrate * 0.08 * sin(TIME * 6.0 + id * 2.3);
	
	VERTEX.y += sway_offset + wave + celeb_jump;
	VERTEX.x += celeb_sway;
}

void fragment() {
	ALBEDO = COLOR.rgb;
	ROUGHNESS = 1.0;
}
