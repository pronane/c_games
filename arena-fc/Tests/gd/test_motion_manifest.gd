extends SceneTree
# Cross-target contract tests for the shared side-aware plant alignment metadata.
const ClipManifest = preload("res://Web/ClipManifest.gd")
var fails := 0

func ok(condition: bool, message: String) -> void:
	print(("PASS " if condition else "FAIL ") + message)
	if not condition:
		fails += 1

func _init() -> void:
	_run.call_deferred()

func _run() -> void:
	var loaded := ClipManifest.load_manifest()
	var by_id: Dictionary = loaded.get("by_id", {})
	ok(by_id.size() == 333 and by_id.has("soccer_run"), "shared manifest loads all clips")
	if by_id.has("soccer_run"):
		var run: Dictionary = by_id["soccer_run"]
		ok(run.get("footPlantFrames", []).size() == 2
			and run.get("footPlantSides", []) == ["Left", "Right"], "manifest carries explicit left/right plant sides")

	var fixture := {"by_id": {
		"source": {"footPlantFrames": [0.10, 0.60], "footPlantSides": ["Left", "Right"]},
		"uneven": {"footPlantFrames": [0.08, 0.30, 0.55], "footPlantSides": ["Left", "Left", "Right"]},
		"left_only": {"footPlantFrames": [0.08], "footPlantSides": ["Left"]},
		"seam_source": {"footPlantFrames": [0.95], "footPlantSides": ["Left"]},
		"seam_target": {"footPlantFrames": [0.05], "footPlantSides": ["Left"]},
	}}
	ok(absf(ClipManifest.align_phase("source", "uneven", 0.58, fixture) - 0.53) < 0.001,
		"uneven plant counts align right-to-right")
	ok(absf(ClipManifest.align_phase("source", "uneven", 0.12, fixture) - 0.10) < 0.001,
		"uneven plant counts align left-to-left")
	ok(absf(ClipManifest.align_phase("source", "left_only", 0.58, fixture) - 0.58) < 0.001,
		"missing same-side event inherits phase")
	ok(absf(ClipManifest.align_phase("seam_source", "seam_target", 0.98, fixture) - 0.08) < 0.001,
		"circular offset remains continuous across cycle wrap")

	print("RESULT motion manifest: %d passed, %d failed" % [5 + (1 if by_id.has("soccer_run") else 0), fails])
	quit(1 if fails > 0 else 0)
