@tool
extends EditorPlugin
## Sprite Forge Studio v9 - Godot 4 editor plugin.
## Project > Tools > "Sprite Forge: import build folder..." : pick a Sprite Forge output folder that you copied
## into the project (it holds atlas.json or pack.json). Writes <name>_frames.tres and <name>.tscn next to it.

var _dialog: EditorFileDialog

func _enter_tree() -> void:
	add_tool_menu_item("Sprite Forge: import build folder...", _open_dialog)

func _exit_tree() -> void:
	remove_tool_menu_item("Sprite Forge: import build folder...")
	if _dialog:
		_dialog.queue_free()

func _open_dialog() -> void:
	if _dialog == null:
		_dialog = EditorFileDialog.new()
		_dialog.file_mode = EditorFileDialog.FILE_MODE_OPEN_DIR
		_dialog.access = EditorFileDialog.ACCESS_RESOURCES
		_dialog.title = "Sprite Forge build folder (contains atlas.json or pack.json)"
		_dialog.dir_selected.connect(_on_dir)
		get_editor_interface().get_base_control().add_child(_dialog)
	_dialog.popup_centered_ratio(0.6)

func _on_dir(dir: String) -> void:
	var made := SpriteForgeImport.import_folder(dir)
	get_editor_interface().get_resource_filesystem().scan()
	print("Sprite Forge: imported ", made)
