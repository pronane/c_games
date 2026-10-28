shader_type sky;
uniform vec3 top : source_color = vec3(0.055, 0.13, 0.28);
uniform vec3 horizon : source_color = vec3(0.32, 0.42, 0.55);
void sky() {
	COLOR = mix(horizon, top, smoothstep(-0.08, 0.6, EYEDIR.y));
	COLOR += vec3(0.9, 0.75, 0.45) * pow(max(dot(EYEDIR, LIGHT0), 0.0), 220.0) * 1.4;
}
