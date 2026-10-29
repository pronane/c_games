extends SceneTree
## headless import:  godot --headless --path <project> --script res://addons/sprite_forge/sf_cli.gd -- res://chars/hero [res://chars/pack ...]
func _init() -> void:
	var args := OS.get_cmdline_user_args()
	var code := 0
	for d in args:
		var made := SpriteForgeImport.import_folder(d)
		print("Sprite Forge import ", d, " -> ", made)
		if made.is_empty():
			code = 1
	quit(code)
