shader_type spatial;
render_mode cull_back, diffuse_lambert;
uniform float sway = 0.045;
void vertex() {
	VERTEX.y += sin(TIME * 2.2 + float(INSTANCE_ID) * 0.83) * sway;
}
void fragment() {
	ALBEDO = COLOR.rgb;
	ROUGHNESS = 1.0;
}
