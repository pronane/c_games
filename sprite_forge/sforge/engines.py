"""v11.23 one-click engine projects: a built character, or a whole roster, as a project each engine opens directly.

    forge.py engine ENGINE SOURCE --out DIR      ENGINE: godot unity unreal raylib web pygame | all
                                                 SOURCE: a build folder (game_character.json) or a roster (roster.json)
    forge.py engine list

Every project holds the characters (sprites, strips, atlas, game_character.json with the move events, portrait and the
rigged 3D model with every move as an animation) and a demo that plays them side by side; LEFT / RIGHT change move.

  godot   Godot 4 project: open project.godot and press Play. main.tscn plays the sprites (with the move events),
          demo3d.tscn loads each model.glb at run time and plays its animations. The Sprite Forge addon is enabled
          for importing SpriteFrames / scenes with hit- and hurtboxes (Project > Tools).
  unity   Unity project (2021.3 or newer): add the folder in Unity Hub and open it. On first open the Sprite Forge
          package imports every character (sliced sprites, clips, controller, prefab with hit/hurt boxes) and builds
          Assets/Scenes/SpriteForgeDemo.unity with the sprites and the 3D models (model.fbx, animator per character).
  unreal  Unreal Engine 5 project: open SpriteForgeDemo.uproject. On first open Content/Python/init_unreal.py imports
          every character - textures, Paper2D sprites and a flipbook per move at its fps, the skeletal mesh with every
          move as an animation, the move events as sync markers - and saves the level /Game/SpriteForge/Demo.
  raylib  C project: `make` (RAYLIB_PATH=... if raylib is not installed), then ./demo (sprites) and ./demo3d (models).
  web     index.html plays the sprites in a canvas, viewer3d.html shows the models with three.js. Serve the folder
          (python serve.py) - browsers do not load files from file:// .
  pygame  python play.py (pip install pygame). Python, like Sprite Forge.

Not run inside Unity or Unreal by these tests (neither runs here); the Godot project runs headless in the tests, the
raylib demo is compiled and run, the web page is opened in a browser, the pygame player runs, and the Unreal import
script runs against a recording stand-in of Unreal's Python API.
"""
from __future__ import annotations
import json
import os
import shutil

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINES = ["godot", "unity", "unreal", "raylib", "web", "pygame"]
SKIP = shutil.ignore_patterns("loaders", ".sfs_build.json", "__pycache__", "*.blend", "faces")


# ------------------------------------------------------------------ the characters
def characters(src):
    """a build folder or a roster folder -> (game, [dict(name, folder, has_model, portrait)])"""
    src = os.path.abspath(src)
    if os.path.isfile(os.path.join(src, "roster.json")):
        r = json.load(open(os.path.join(src, "roster.json")))
        out = []
        for p in r["players"]:
            d = os.path.join(src, p["folder"])
            out.append(_char(p["name"], d, p))
        return r.get("game", ""), out
    if os.path.isfile(os.path.join(src, "game_character.json")):
        m = json.load(open(os.path.join(src, "game_character.json")))
        return m.get("game_pack", ""), [_char(os.path.basename(src.rstrip("/")) or m.get("name", "character"), src, {})]
    raise ValueError("%s has neither game_character.json (a build) nor roster.json (a roster)" % src)


def _char(name, d, rec):
    if not os.path.isfile(os.path.join(d, "game_character.json")):
        raise ValueError("%s: no game_character.json in %s" % (name, d))
    return dict(name=name, folder=d, glb=os.path.isfile(os.path.join(d, "model.glb")),
                fbx=os.path.isfile(os.path.join(d, "model.fbx")), portrait=os.path.isfile(os.path.join(d, "portrait.png")),
                side=rec.get("side", ""), role=rec.get("role", ""), kit=rec.get("kit", ""), type=rec.get("type", ""))


def copy_characters(chars, dst):
    os.makedirs(dst, exist_ok=True)
    for c in chars:
        t = os.path.join(dst, c["name"])
        if os.path.isdir(t):
            shutil.rmtree(t)
        shutil.copytree(c["folder"], t, ignore=SKIP)
    idx = [dict(name=c["name"], dir=c["name"], model=c["glb"], fbx=c["fbx"], portrait=c["portrait"],
                side=c["side"], role=c["role"]) for c in chars]
    json.dump(idx, open(os.path.join(dst, "index.json"), "w"), indent=1)
    return idx


def _w(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="\n") as f:
        f.write(text)


def _readme(dst, title, body):
    _w(os.path.join(dst, "README.md"), "# %s\n\n%s\n\nMade by Sprite Forge (`forge.py engine`). The characters are in "
                                         "the folder named below; each has game_character.json (moves, fps, loop, events, "
                                         "hit/hurt boxes), strips/, atlas.png, portrait.png and model.glb / model.fbx.\n" % (title, body))


# ------------------------------------------------------------------ Godot 4
GODOT_DEMO = r'''extends Node2D
## Sprite Forge demo: every character side by side, playing the same move. LEFT / RIGHT change move.
## The move's events (hit window, ball contact, footsteps...) light up under each character.

const GC := preload("res://sprite_forge/game_character.gd")
var chars: Array = []
var moves: PackedStringArray = []
var move_i := 0
var label: Label

func _ready() -> void:
	var idx = JSON.parse_string(FileAccess.get_file_as_string("res://characters/index.json"))
	var n: int = idx.size()
	var view := get_viewport_rect().size
	for i in n:
		var c = idx[i]
		var node := Node2D.new()
		node.set_script(GC)
		node.scale_to = clamp(view.y * 0.55, 120.0, 420.0)
		node.position = Vector2(view.x * (i + 0.5) / n, view.y * 0.78)
		add_child(node)
		node.load_dir("res://characters/" + str(c["dir"]))
		var tag := Label.new()
		tag.text = str(c["name"])
		tag.position = node.position + Vector2(-40, 12)
		add_child(tag)
		chars.append({"node": node, "tag": tag, "name": str(c["name"])})
		for m in node.moves():
			if not moves.has(m):
				moves.append(m)
		print("SF_DEMO ", c["name"], " ", node.moves().size())
	label = Label.new()
	label.position = Vector2(16, 12)
	add_child(label)
	_play()

func _play() -> void:
	if moves.is_empty():
		return
	var m := moves[move_i]
	for c in chars:
		c["node"].play(m)
	label.text = "%s   (LEFT / RIGHT: change move)" % m

func _unhandled_input(e: InputEvent) -> void:
	if e.is_action_pressed("ui_right"):
		move_i = (move_i + 1) % moves.size(); _play()
	elif e.is_action_pressed("ui_left"):
		move_i = (move_i + moves.size() - 1) % moves.size(); _play()

func _process(_d: float) -> void:
	for c in chars:
		var on := []
		for k in ["hit", "ball_contact", "throw_release", "shoot", "reload", "footstep"]:
			if c["node"].event_now(k):
				on.append(k)
		c["tag"].text = c["name"] + ("  [" + ", ".join(on) + "]" if on.size() > 0 else "")
'''

GODOT_DEMO3D = r'''extends Node3D
## Sprite Forge 3D demo: each character's model.glb loaded at run time (GLTFDocument), every move an animation.
## LEFT / RIGHT change move.

var players: Array = []
var anims: PackedStringArray = []
var move_i := 0

func _ready() -> void:
	var idx = JSON.parse_string(FileAccess.get_file_as_string("res://characters/index.json"))
	var x := 0.0
	var n := 0
	for c in idx:
		if not c.get("model", false):
			continue
		var doc := GLTFDocument.new()
		var state := GLTFState.new()
		if doc.append_from_file(ProjectSettings.globalize_path("res://characters/%s/model.glb" % c["dir"]), state) != OK:
			push_warning("could not load the model of " + str(c["name"]))
			continue
		var scene := doc.generate_scene(state)
		scene.position = Vector3(x, 0, 0)
		add_child(scene)
		x += 1.2
		n += 1
		var ap: AnimationPlayer = scene.find_child("AnimationPlayer", true, false)
		if ap:
			players.append(ap)
			for a in ap.get_animation_list():
				if not anims.has(a):
					anims.append(a)
		print("SF_DEMO3D ", c["name"], " ", ap.get_animation_list().size() if ap else 0)
	var cam := Camera3D.new()
	cam.position = Vector3(max(0.0, x - 1.2) / 2.0, 1.1, 1.6 + 0.45 * n)
	add_child(cam)
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-45, 30, 0)
	add_child(sun)
	var env := WorldEnvironment.new()
	env.environment = Environment.new()
	env.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.environment.ambient_light_color = Color(0.6, 0.6, 0.65)
	add_child(env)
	_play()

func _play() -> void:
	if anims.is_empty():
		return
	var want := anims[move_i]
	for ap in players:
		for a in ap.get_animation_list():
			if a == want or a.ends_with(want):
				ap.play(a)

func _unhandled_input(e: InputEvent) -> void:
	if anims.is_empty():
		return
	if e.is_action_pressed("ui_right"):
		move_i = (move_i + 1) % anims.size(); _play()
	elif e.is_action_pressed("ui_left"):
		move_i = (move_i + anims.size() - 1) % anims.size(); _play()
'''


def godot(chars, dst, game=""):
    copy_characters(chars, os.path.join(dst, "characters"))
    shutil.copytree(os.path.join(HERE, "plugins", "godot", "addons"), os.path.join(dst, "addons"), dirs_exist_ok=True)
    os.makedirs(os.path.join(dst, "sprite_forge"), exist_ok=True)
    shutil.copy(os.path.join(HERE, "loaders", "godot", "game_character.gd"), os.path.join(dst, "sprite_forge", "game_character.gd"))
    _w(os.path.join(dst, "project.godot"), '''; Sprite Forge characters (forge.py engine godot)
config_version=5

[application]
config/name="Sprite Forge %s"
run/main_scene="res://main.tscn"
config/features=PackedStringArray("4.2")

[display]
window/size/viewport_width=1280
window/size/viewport_height=720

[editor_plugins]
enabled=PackedStringArray("res://addons/sprite_forge/plugin.cfg")

[rendering]
textures/canvas_textures/default_texture_filter=0
''' % (game or "characters"))
    _w(os.path.join(dst, "demo.gd"), GODOT_DEMO)
    _w(os.path.join(dst, "demo3d.gd"), GODOT_DEMO3D)
    _w(os.path.join(dst, "main.tscn"), '[gd_scene load_steps=2 format=3]\n\n[ext_resource type="Script" path="res://demo.gd" id="1"]\n\n'
                                       '[node name="Demo" type="Node2D"]\nscript = ExtResource("1")\n')
    _w(os.path.join(dst, "demo3d.tscn"), '[gd_scene load_steps=2 format=3]\n\n[ext_resource type="Script" path="res://demo3d.gd" id="1"]\n\n'
                                         '[node name="Demo3D" type="Node3D"]\nscript = ExtResource("1")\n')
    _w(os.path.join(dst, ".gitignore"), ".godot/\n")
    _readme(dst, "Sprite Forge characters for Godot 4", "Open `project.godot` in Godot 4.2 or newer and press Play: "
            "`main.tscn` plays the sprites (LEFT / RIGHT change move; the move events show under each character). Open "
            "`demo3d.tscn` and press F6 for the 3D models with their animations.\n\nIn your game: put "
            "`sprite_forge/game_character.gd` on a Node2D and call `load_dir(\"res://characters/NAME\")`, `play(\"kick\")`, "
            "`event_now(\"ball_contact\")`. Or Project > Tools > *Sprite Forge: import build folder...* for a SpriteFrames "
            "resource and a scene with hit and hurt boxes. Drag `characters/NAME/model.glb` into a 3D scene for the model.\n\n"
            "Characters: `characters/`")
    return dst


# ------------------------------------------------------------------ Unity
UNITY_SETUP = r'''// Sprite Forge one-click setup (forge.py engine unity). Runs once when the project opens, or from
// Tools > Sprite Forge > Set Up Demo Scene. Imports every folder under Assets/Characters with the Sprite Forge
// importer, gives each 3D model an Animator that plays idle, and saves Assets/Scenes/SpriteForgeDemo.unity.
// Batch: Unity -batchmode -quit -projectPath P -executeMethod SpriteForge.Setup.SpriteForgeProjectSetup.Run
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.Animations;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace SpriteForge.Setup
{
    [InitializeOnLoad]
    public static class SpriteForgeProjectSetup
    {
        const string ScenePath = "Assets/Scenes/SpriteForgeDemo.unity";

        static SpriteForgeProjectSetup()
        {
            EditorApplication.delayCall += () =>
            {
                if (!File.Exists(ScenePath) && Directory.Exists("Assets/Characters")) Run();
            };
        }

        [MenuItem("Tools/Sprite Forge/Set Up Demo Scene")]
        public static void Run()
        {
            AssetDatabase.Refresh();
            var sprites = new List<GameObject>();
            var models = new List<GameObject>();
            foreach (var dir in Directory.GetDirectories("Assets/Characters").OrderBy(d => d))
            {
                var folder = dir.Replace('\\', '/');
                foreach (var p in SpriteForge.Editor.SpriteForgeImporter.ImportFolder(folder))
                    if (p.EndsWith(".prefab"))
                    {
                        var go = AssetDatabase.LoadAssetAtPath<GameObject>(p);
                        if (go != null) sprites.Add(go);
                    }
                var fbx = folder + "/model.fbx";
                if (File.Exists(fbx))
                {
                    var model = AssetDatabase.LoadAssetAtPath<GameObject>(fbx);
                    var clips = AssetDatabase.LoadAllAssetsAtPath(fbx).OfType<AnimationClip>()
                        .Where(c => !c.name.StartsWith("__preview__")).ToList();
                    if (model != null)
                    {
                        if (clips.Count > 0)
                        {
                            var idle = clips.FirstOrDefault(c => c.name.EndsWith("idle")) ?? clips[0];
                            var ctrl = AnimatorController.CreateAnimatorControllerAtPathWithClip(folder + "/model.controller", idle);
                            foreach (var c in clips)
                                if (c != idle) ctrl.layers[0].stateMachine.AddState(c.name).motion = c;
                        }
                        models.Add(model);
                    }
                }
            }
            var scene = EditorSceneManager.NewScene(NewSceneSetup.DefaultGameObjects, NewSceneMode.Single);
            var cam = Camera.main;
            float span = 2.2f;
            for (int i = 0; i < sprites.Count; i++)
            {
                var g = (GameObject)PrefabUtility.InstantiatePrefab(sprites[i]);
                g.transform.position = new Vector3((i - (sprites.Count - 1) / 2f) * span, -1f, 0f);
            }
            for (int i = 0; i < models.Count; i++)
            {
                var g = (GameObject)PrefabUtility.InstantiatePrefab(models[i]);
                g.transform.position = new Vector3((i - (models.Count - 1) / 2f) * span, -1f, 3f);
                g.transform.rotation = Quaternion.Euler(0f, 180f, 0f);
                var ctrlPath = Path.GetDirectoryName(AssetDatabase.GetAssetPath(models[i])).Replace('\\', '/') + "/model.controller";
                var ctrl = AssetDatabase.LoadAssetAtPath<RuntimeAnimatorController>(ctrlPath);
                if (ctrl != null)
                {
                    var an = g.GetComponent<Animator>() ?? g.AddComponent<Animator>();
                    an.runtimeAnimatorController = ctrl;
                }
            }
            if (cam != null)
            {
                cam.transform.position = new Vector3(0f, 0.6f, -10f);
                cam.orthographic = models.Count == 0;
                cam.orthographicSize = 3f;
            }
            new GameObject("Sprite Forge Demo").AddComponent<SpriteForge.SpriteForgeDemo>();
            Directory.CreateDirectory("Assets/Scenes");
            EditorSceneManager.SaveScene(scene, ScenePath);
            Debug.Log("Sprite Forge: " + sprites.Count + " sprite characters, " + models.Count + " models -> " + ScenePath);
        }
    }
}
'''

UNITY_DEMO = r'''// Sprite Forge demo: every SpriteForgeCharacter in the scene plays the same move. LEFT / RIGHT change move
// (old Input Manager); with the new Input System only, the moves change by themselves every 2.5 seconds.
using System.Collections.Generic;
using UnityEngine;

namespace SpriteForge
{
    public class SpriteForgeDemo : MonoBehaviour
    {
        public float autoAdvance = 2.5f;
        readonly List<string> _moves = new List<string>();
        SpriteForgeCharacter[] _chars;
        Animator[] _models;
        int _i;
        float _t;

        void Start()
        {
            _chars = FindObjectsOfType<SpriteForgeCharacter>();
            _models = FindObjectsOfType<Animator>();
            foreach (var c in _chars)
                if (c.data != null)
                    foreach (var m in c.data.moves)
                        if (!_moves.Contains(m.name)) _moves.Add(m.name);
            Play();
        }

        void Play()
        {
            if (_moves.Count == 0) return;
            var m = _moves[_i];
            foreach (var c in _chars) c.Play(m);
            foreach (var a in _models)
                if (a.runtimeAnimatorController != null && a.GetComponent<SpriteForgeCharacter>() == null)
                    a.Play(m, 0, 0f);
            _t = 0f;
        }

        void Step(int d)
        {
            if (_moves.Count == 0) return;
            _i = (_i + d + _moves.Count) % _moves.Count;
            Play();
        }

        void Update()
        {
#if ENABLE_LEGACY_INPUT_MANAGER
            if (Input.GetKeyDown(KeyCode.RightArrow)) { Step(1); return; }
            if (Input.GetKeyDown(KeyCode.LeftArrow)) { Step(-1); return; }
#endif
            _t += Time.deltaTime;
            if (autoAdvance > 0f && _t > autoAdvance) Step(1);
        }

        void OnGUI()
        {
            if (_moves.Count > 0) GUI.Label(new Rect(12, 8, 600, 24), _moves[_i] + "   (LEFT / RIGHT: change move)");
        }
    }
}
'''


def unity(chars, dst, game=""):
    copy_characters(chars, os.path.join(dst, "Assets", "Characters"))
    os.remove(os.path.join(dst, "Assets", "Characters", "index.json"))
    shutil.copytree(os.path.join(HERE, "plugins", "unity", "com.spriteforge.importer"),
                    os.path.join(dst, "Packages", "com.spriteforge.importer"), dirs_exist_ok=True)
    mods = ["ai", "animation", "audio", "imageconversion", "imgui", "jsonserialize", "particlesystem", "physics",
            "physics2d", "ui", "uielements", "unitywebrequest", "unitywebrequesttexture"]
    deps = {"com.unity.2d.sprite": "1.0.0", "com.unity.ugui": "1.0.0"}
    deps.update({"com.unity.modules." + m: "1.0.0" for m in mods})
    _w(os.path.join(dst, "Packages", "manifest.json"), json.dumps({"dependencies": deps}, indent=2) + "\n")
    _w(os.path.join(dst, "Assets", "SpriteForge", "Editor", "SpriteForgeProjectSetup.cs"), UNITY_SETUP)
    _w(os.path.join(dst, "Assets", "SpriteForge", "Editor", "SpriteForge.Setup.asmdef"), json.dumps(
        {"name": "SpriteForge.Setup", "references": ["SpriteForge.Runtime", "SpriteForge.Editor"], "includePlatforms": ["Editor"]}, indent=1))
    _w(os.path.join(dst, "Assets", "SpriteForge", "SpriteForgeDemo.cs"), UNITY_DEMO)
    _w(os.path.join(dst, "Assets", "SpriteForge", "SpriteForge.Demo.asmdef"), json.dumps(
        {"name": "SpriteForge.Demo", "references": ["SpriteForge.Runtime"]}, indent=1))
    _w(os.path.join(dst, ".gitignore"), "Library/\nTemp/\nLogs/\nobj/\nUserSettings/\n")
    _readme(dst, "Sprite Forge characters for Unity", "Unity Hub > Add > this folder, open it (Unity 2021.3 LTS or newer). "
            "On first open the project imports every character (Tools > Sprite Forge > Set Up Demo Scene does it again) "
            "and saves `Assets/Scenes/SpriteForgeDemo.unity`: the sprite characters in a row, the 3D models behind them. "
            "Press Play; LEFT / RIGHT change move.\n\nIn your game: drag `Assets/Characters/NAME/NAME.prefab` into a scene "
            "(`SpriteForgeCharacter.Play(\"kick\")`, `HitActive` event, hit and hurt BoxCollider2D triggers) or "
            "`model.fbx` for the rigged model with every move as an animation clip.\n\nThis project was written by Sprite "
            "Forge and has not been opened in Unity by its tests. Characters: `Assets/Characters/`")
    return dst


# ------------------------------------------------------------------ Unreal Engine 5
UNREAL_IMPORT = r'''"""Sprite Forge -> Unreal Engine 5 (Paper2D + skeletal meshes). Written by `forge.py engine unreal`.

Runs by itself the first time the project opens (Content/Python/init_unreal.py); run it again with
Tools > Execute Python Script... > SpriteForge/sprite_forge_import.py. Needs the Paper2D, Python Editor Script and
Editor Scripting Utilities plugins (the .uproject turns them on).

For each character in SpriteForge/characters/<name>/ it makes, under /Game/SpriteForge/<name>/:
  Strips/T_<move>       the move's sprite strip as a texture (nearest filter, no mipmaps, UI compression)
  Sprites/S_<move>_NN   one Paper2D sprite per frame, pivot on the feet
  Flipbooks/FB_<move>   one flipbook per move at the move's fps
  Model/                model.fbx: skeletal mesh + one animation per move; each move's events (hit_start,
                        ball_contact, footstep...) are sync markers on a "SpriteForge" notify track
and saves the level /Game/SpriteForge/Demo with every character's idle flipbook and model side by side.
The events and hit / hurt boxes are also in SpriteForge/characters/<name>/game_character.json.
"""
import json
import os

import unreal

ROOT = "/Game/SpriteForge"


def _src_dir():
    return os.path.join(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir()), "SpriteForge", "characters")


def _import(files, dest, options=None):
    tasks = []
    for f in files:
        t = unreal.AssetImportTask()
        t.set_editor_property("filename", f)
        t.set_editor_property("destination_path", dest)
        t.set_editor_property("automated", True)
        t.set_editor_property("replace_existing", True)
        t.set_editor_property("save", True)
        if options is not None:
            t.set_editor_property("options", options)
        tasks.append(t)
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks(tasks)
    out = []
    for t in tasks:
        out += list(t.get_editor_property("imported_object_paths") or [])
    return out


def _texture(path):
    tex = unreal.EditorAssetLibrary.load_asset(path)
    tex.set_editor_property("filter", unreal.TextureFilter.TF_NEAREST)
    tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_EDITOR_ICON)
    tex.set_editor_property("mip_gen_settings", unreal.TextureMipGenSettings.TMGS_NO_MIPMAPS)
    tex.set_editor_property("lod_group", unreal.TextureGroup.TEXTUREGROUP_PIXELS2D)
    unreal.EditorAssetLibrary.save_loaded_asset(tex)
    return tex


def _event_times(anim, n, fps, loop, length):
    """sprite frame -> seconds on the 3D take (the sprite frames sample the take evenly)"""
    marks = []
    ev = anim.get("events") or {}
    for key, v in ev.items():
        frames = v if isinstance(v, list) else [v]
        for f in frames:
            if isinstance(f, (int, float)) and f >= 0:
                k = (f / float(n)) if loop else (f / float(max(1, n - 1)))
                marks.append((("footstep" if key == "footsteps" else key), round(min(1.0, k) * length, 4)))
    return marks


def import_character(name, folder):
    data = json.load(open(os.path.join(folder, "game_character.json")))
    base = "%s/%s" % (ROOT, name)
    tools = unreal.AssetToolsHelpers.get_asset_tools()
    flipbooks = {}
    height = float(data.get("height_px") or 100)
    for a in data.get("animations", []):
        move, n, fps = a["name"], int(a["frames"]), float(a.get("fps", 12))
        w, h = int(a.get("w", 128)), int(a.get("h", 160))
        piv = a.get("pivot") or {"x": w // 2, "y": h}
        strip = os.path.join(folder, a["strip"])
        paths = _import([strip], base + "/Strips")
        if not paths:
            unreal.log_warning("Sprite Forge: could not import " + strip)
            continue
        tex_path = paths[0].split(".")[0]
        tex = _texture(tex_path)
        new_tex = tools.rename_assets([unreal.AssetRenameData(tex, base + "/Strips", "T_" + move)])
        frames = []
        for i in range(n):
            sp = tools.create_asset("S_%s_%02d" % (move, i), base + "/Sprites", unreal.PaperSprite, unreal.PaperSpriteFactory())
            sp.set_editor_property("source_texture", tex)
            sp.set_editor_property("source_uv", unreal.Vector2D(i * w, 0))
            sp.set_editor_property("source_dimension", unreal.Vector2D(w, h))
            sp.set_editor_property("pivot_mode", unreal.SpritePivotMode.CUSTOM)
            sp.set_editor_property("custom_pivot_point", unreal.Vector2D(i * w + float(piv["x"]), float(piv["y"])))
            sp.set_editor_property("pixels_per_unreal_unit", height / 180.0)
            unreal.EditorAssetLibrary.save_loaded_asset(sp)
            frames.append(sp)
        fb = tools.create_asset("FB_" + move, base + "/Flipbooks", unreal.PaperFlipbook, unreal.PaperFlipbookFactory())
        fb.set_editor_property("frames_per_second", fps)
        fb.set_editor_property("key_frames", [unreal.PaperFlipbookKeyFrame(sprite=s, frame_run=1) for s in frames])
        unreal.EditorAssetLibrary.save_loaded_asset(fb)
        flipbooks[move] = fb
    mesh, anims = None, {}
    fbx = os.path.join(folder, "model.fbx")
    if os.path.isfile(fbx):
        ui = unreal.FbxImportUI()
        ui.set_editor_property("import_mesh", True)
        ui.set_editor_property("import_as_skeletal", True)
        ui.set_editor_property("import_animations", True)
        ui.set_editor_property("import_materials", True)
        ui.set_editor_property("import_textures", True)
        ui.set_editor_property("mesh_type_to_import", unreal.FBXImportType.FBXIT_SKELETAL_MESH)
        for p in _import([fbx], base + "/Model", ui):
            obj = unreal.EditorAssetLibrary.load_asset(p.split(".")[0])
            if isinstance(obj, unreal.SkeletalMesh):
                mesh = obj
        for p in unreal.EditorAssetLibrary.list_assets(base + "/Model", recursive=True, include_folder=False):
            obj = unreal.EditorAssetLibrary.load_asset(p.split(".")[0])
            if isinstance(obj, unreal.AnimSequence):
                anims[obj.get_name()] = obj
        by_move = {}
        for a in data.get("animations", []):
            mv = a["name"]
            seq = anims.get(mv) or next((s for k, s in anims.items() if k.endswith("_Anim_" + mv)), None) or \
                next((s for k, s in anims.items() if k.endswith("_" + mv)), None)
            if seq is None:
                continue
            by_move[a["name"]] = seq
            length = unreal.AnimationLibrary.get_sequence_length(seq)
            marks = _event_times(a, int(a["frames"]), float(a.get("fps", 12)), bool(a.get("loop")), length)
            if marks:
                unreal.AnimationLibrary.add_animation_notify_track(seq, "SpriteForge")
                for ev, t in marks:
                    unreal.AnimationLibrary.add_animation_sync_marker(seq, ev, t, "SpriteForge")
                unreal.EditorAssetLibrary.save_loaded_asset(seq)
        anims = by_move
    unreal.log("Sprite Forge: %s - %d flipbooks, %d animations" % (name, len(flipbooks), len(anims)))
    return flipbooks, mesh, anims


def build_level(made):
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    les.new_level(ROOT + "/Demo")
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    span = 220.0
    n = len(made)
    for i, (name, (fbs, mesh, anims)) in enumerate(sorted(made.items())):
        x = (i - (n - 1) / 2.0) * span
        fb = fbs.get("idle") or (next(iter(fbs.values())) if fbs else None)
        if fb is not None:
            a = actors.spawn_actor_from_class(unreal.PaperFlipbookActor, unreal.Vector(x, 0, 0), unreal.Rotator(0, 0, 0))
            a.set_actor_label("SF_" + name)
            a.get_editor_property("render_component").set_flipbook(fb)
        if mesh is not None:
            m = actors.spawn_actor_from_class(unreal.SkeletalMeshActor, unreal.Vector(x, 300, 0), unreal.Rotator(0, 0, 0))
            m.set_actor_label("SF_" + name + "_3D")
            comp = m.get_editor_property("skeletal_mesh_component")
            comp.set_skeletal_mesh_asset(mesh) if hasattr(comp, "set_skeletal_mesh_asset") else comp.set_skeletal_mesh(mesh)
            idle = anims.get("idle")
            if idle is not None:
                comp.set_animation_mode(unreal.AnimationMode.ANIMATION_SINGLE_NODE)
                comp.override_animation_data(idle, True, True, 0.0, 1.0)
    les.save_current_level()


def run():
    src = _src_dir()
    idx = json.load(open(os.path.join(src, "index.json")))
    made = {}
    with unreal.ScopedSlowTask(len(idx), "Sprite Forge: importing characters") as task:
        task.make_dialog(True)
        for c in idx:
            task.enter_progress_frame(1, "Sprite Forge: " + c["name"])
            made[c["name"]] = import_character(c["name"], os.path.join(src, c["dir"]))
    build_level(made)
    unreal.EditorAssetLibrary.save_directory(ROOT)
    unreal.log("Sprite Forge: imported %d characters -> %s/Demo" % (len(made), ROOT))
    return made


if __name__ == "__main__":
    run()
'''

UNREAL_INIT = r'''# Sprite Forge: import the characters the first time the project opens (forge.py engine unreal).
import os
import sys

import unreal

_here = os.path.join(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir()), "SpriteForge")
_done = os.path.join(_here, ".imported")
_handle = None


def _once(_dt):
    global _handle
    unreal.unregister_slate_post_tick_callback(_handle)
    if _here not in sys.path:
        sys.path.append(_here)
    import sprite_forge_import
    sprite_forge_import.run()
    open(_done, "w").write("imported\n")


if not os.path.isfile(_done):
    _handle = unreal.register_slate_post_tick_callback(_once)
'''


def unreal(chars, dst, game=""):
    copy_characters(chars, os.path.join(dst, "SpriteForge", "characters"))
    proj = {"FileVersion": 3, "EngineAssociation": "", "Category": "", "Description": "Sprite Forge characters (%s)" % (game or "game"),
            "Plugins": [{"Name": "Paper2D", "Enabled": True}, {"Name": "PythonScriptPlugin", "Enabled": True},
                        {"Name": "EditorScriptingUtilities", "Enabled": True}]}
    _w(os.path.join(dst, "SpriteForgeDemo.uproject"), json.dumps(proj, indent=1) + "\n")
    _w(os.path.join(dst, "SpriteForge", "sprite_forge_import.py"), UNREAL_IMPORT)
    _w(os.path.join(dst, "Content", "Python", "init_unreal.py"), UNREAL_INIT)
    _w(os.path.join(dst, "Config", "DefaultEngine.ini"), "[/Script/EngineSettings.GameMapsSettings]\n"
       "EditorStartupMap=/Game/SpriteForge/Demo.Demo\nGameDefaultMap=/Game/SpriteForge/Demo.Demo\n")
    _w(os.path.join(dst, "Config", "DefaultGame.ini"), "[/Script/EngineSettings.GeneralProjectSettings]\nProjectName=Sprite Forge Demo\n\n"
       "[/Script/UnrealEd.ProjectPackagingSettings]\n+DirectoriesToAlwaysStageAsNonUFS=(Path=\"../SpriteForge/characters\")\n")
    _w(os.path.join(dst, ".gitignore"), "Binaries/\nDerivedDataCache/\nIntermediate/\nSaved/\nSpriteForge/.imported\n")
    _readme(dst, "Sprite Forge characters for Unreal Engine 5", "Open `SpriteForgeDemo.uproject` with Unreal Engine 5 (pick "
            "your installed version when asked). On first open `Content/Python/init_unreal.py` imports every character "
            "(a progress bar shows) - textures, a Paper2D sprite per frame with the pivot on the feet, a flipbook per "
            "move at its fps, the skeletal mesh with every move as an animation and the move events (hit_start, "
            "ball_contact, footstep...) as sync markers on a *SpriteForge* track - and saves `/Game/SpriteForge/Demo` "
            "with each character's idle flipbook and 3D model. To import again: delete `SpriteForge/.imported` or run "
            "Tools > Execute Python Script > `SpriteForge/sprite_forge_import.py`.\n\nIn your game: a PaperFlipbookComponent "
            "with `/Game/SpriteForge/NAME/Flipbooks/FB_kick`, or a SkeletalMeshComponent with the model and its "
            "animations; read the sync markers (or `SpriteForge/characters/NAME/game_character.json`) for the events.\n\n"
            "This project was written by Sprite Forge. Its import script is tested against a stand-in of Unreal's Python "
            "API, not inside Unreal. Characters: `SpriteForge/characters/`")
    return dst


# ------------------------------------------------------------------ raylib
RAYLIB_MAIN = r'''/* Sprite Forge demo for raylib: every character in characters/index.txt side by side.
 *   ./demo [--shot out.png]     LEFT / RIGHT change move, ESC quits */
#define GAME_CHARACTER_IMPLEMENTATION
#include "game_character.h"
#include <stdio.h>
#include <string.h>

#define MAXC 16
int main(int argc, char **argv) {
    const char *shot = (argc > 2 && !strcmp(argv[1], "--shot")) ? argv[2] : NULL;
    char names[MAXC][64]; int n = 0;
    FILE *f = fopen("characters/index.txt", "r");
    if (!f) { fprintf(stderr, "characters/index.txt not found - run from the project folder\n"); return 1; }
    while (n < MAXC && fscanf(f, "%63s", names[n]) == 1) n++;
    fclose(f);
    const int W = 1280, H = 720;
    SetConfigFlags(FLAG_MSAA_4X_HINT);
    InitWindow(W, H, "Sprite Forge characters");
    SetTargetFPS(60);
    static GC_Character ch[MAXC]; int ok = 0;
    for (int i = 0; i < n; i++) {
        char dir[128]; snprintf(dir, sizeof dir, "characters/%s", names[i]);
        if (GC_Load(&ch[ok], dir)) { strncpy(names[ok], names[i], 63); ok++; }
        else fprintf(stderr, "could not load %s\n", dir);
    }
    if (!ok) { CloseWindow(); return 1; }
    int move = GC_Find(&ch[0], "idle"); if (move < 0) move = 0;
    for (int i = 0; i < ok; i++) { int m = GC_Find(&ch[i], ch[0].anims[move].name); GC_Play(&ch[i], m < 0 ? 0 : m); }
    float ground = H - 90.0f;
    int frames = 0;
    while (!WindowShouldClose()) {
        if (IsKeyPressed(KEY_RIGHT) || IsKeyPressed(KEY_LEFT)) {
            move = (move + (IsKeyPressed(KEY_RIGHT) ? 1 : ch[0].anim_count - 1)) % ch[0].anim_count;
            for (int i = 0; i < ok; i++) { int m = GC_Find(&ch[i], ch[0].anims[move].name); if (m >= 0) GC_Play(&ch[i], m); }
        }
        for (int i = 0; i < ok; i++) GC_Update(&ch[i], shot ? 1.0f / 60.0f : GetFrameTime());
        BeginDrawing();
        ClearBackground((Color){24, 26, 34, 255});
        DrawRectangle(0, (int)ground, W, H - (int)ground, (Color){48, 54, 66, 255});
        for (int i = 0; i < ok; i++) {
            float x = W * (i + 0.5f) / ok;
            float sc = ch[i].anims[ch[i].playing].h > 0 ? (H * 0.62f) / ch[i].anims[ch[i].playing].h : 2.0f;
            if (sc * ch[i].anims[ch[i].playing].w > W / (float)ok * 1.4f) sc = W / (float)ok * 1.4f / ch[i].anims[ch[i].playing].w;
            GC_Draw(&ch[i], x, ground, false, sc);
            DrawText(names[i], (int)x - MeasureText(names[i], 18) / 2, (int)ground + 12, 18, RAYWHITE);
            if (GC_HitActive(&ch[i])) DrawText("HIT", (int)x - 14, (int)ground + 36, 18, RED);
        }
        DrawText(TextFormat("%s   (LEFT / RIGHT: change move)", ch[0].anims[move].name), 16, 14, 22, RAYWHITE);
        EndDrawing();
        if (shot && ++frames >= 20) { { Image im_ = LoadImageFromScreen(); ExportImage(im_, shot); UnloadImage(im_); } printf("SF_DEMO %d characters, move %s\n", ok, ch[0].anims[move].name); break; }
    }
    for (int i = 0; i < ok; i++) GC_Unload(&ch[i]);
    CloseWindow();
    return 0;
}
'''

RAYLIB_3D = r'''/* Sprite Forge 3D demo for raylib: each character's model.glb with its animations (every move).
 *   ./demo3d [--shot out.png]     LEFT / RIGHT change move, ESC quits */
#include "raylib.h"
#include <stdio.h>
#include <string.h>

#define MAXC 16
int main(int argc, char **argv) {
    const char *shot = (argc > 2 && !strcmp(argv[1], "--shot")) ? argv[2] : NULL;
    char names[MAXC][64]; int n = 0;
    FILE *f = fopen("characters/index3d.txt", "r");
    if (!f) { fprintf(stderr, "characters/index3d.txt not found - run from the project folder\n"); return 1; }
    while (n < MAXC && fscanf(f, "%63s", names[n]) == 1) n++;
    fclose(f);
    InitWindow(1280, 720, "Sprite Forge models");
    SetTargetFPS(60);
    Model model[MAXC]; ModelAnimation *anims[MAXC]; int count[MAXC]; int ok = 0;
    for (int i = 0; i < n; i++) {
        const char *p = TextFormat("characters/%s/model.glb", names[i]);
        model[ok] = LoadModel(p);
        if (model[ok].meshCount == 0) { fprintf(stderr, "could not load %s\n", p); continue; }
        count[ok] = 0;
        anims[ok] = LoadModelAnimations(p, &count[ok]);
        ok++;
    }
    Camera3D cam = { 0 };
    cam.position = (Vector3){ 0.0f, 1.3f, 2.4f + ok * 0.6f };
    cam.target = (Vector3){ 0.0f, 0.9f, 0.0f };
    cam.up = (Vector3){ 0.0f, 1.0f, 0.0f };
    cam.fovy = 45.0f; cam.projection = CAMERA_PERSPECTIVE;
    int move = 0, frame = 0, drawn = 0;
    while (!WindowShouldClose()) {
        if (IsKeyPressed(KEY_RIGHT)) { move++; frame = 0; }
        if (IsKeyPressed(KEY_LEFT)) { move = move > 0 ? move - 1 : 0; frame = 0; }
        frame++;
        for (int i = 0; i < ok; i++)
            if (count[i] > 0) {
                ModelAnimation a = anims[i][move % count[i]];
                UpdateModelAnimation(model[i], a, frame % (a.frameCount > 0 ? a.frameCount : 1));
            }
        BeginDrawing();
        ClearBackground((Color){24, 26, 34, 255});
        BeginMode3D(cam);
        DrawGrid(10, 0.5f);
        for (int i = 0; i < ok; i++) DrawModel(model[i], (Vector3){ (i - (ok - 1) / 2.0f) * 1.1f, 0, 0 }, 1.0f, WHITE);
        EndMode3D();
        if (ok && count[0] > 0) DrawText(TextFormat("%s   (LEFT / RIGHT: change move)", anims[0][move % count[0]].name), 16, 14, 22, RAYWHITE);
        EndDrawing();
        if (shot && ++drawn >= 20) { { Image im_ = LoadImageFromScreen(); ExportImage(im_, shot); UnloadImage(im_); } printf("SF_DEMO3D %d models, %d animations\n", ok, ok ? count[0] : 0); break; }
    }
    for (int i = 0; i < ok; i++) { UnloadModelAnimations(anims[i], count[i]); UnloadModel(model[i]); }
    CloseWindow();
    return 0;
}
'''

RAYLIB_MAKE = r'''# Sprite Forge raylib demo.  make               (raylib installed system-wide)
#                           make RAYLIB_PATH=~/raylib/src
RAYLIB_PATH ?=
CFLAGS += -O2 -std=c99 $(if $(RAYLIB_PATH),-I$(RAYLIB_PATH),)
LDFLAGS += $(if $(RAYLIB_PATH),-L$(RAYLIB_PATH),)
ifeq ($(OS),Windows_NT)
  LIBS = -lraylib -lopengl32 -lgdi32 -lwinmm
else ifeq ($(shell uname),Darwin)
  LIBS = -lraylib -framework OpenGL -framework Cocoa -framework IOKit -framework CoreVideo
else
  LIBS = -lraylib -lGL -lm -lpthread -ldl -lrt -lX11
endif
all: demo demo3d
demo: main.c game_character.h
	$(CC) $(CFLAGS) main.c -o demo $(LDFLAGS) $(LIBS)
demo3d: main3d.c
	$(CC) $(CFLAGS) main3d.c -o demo3d $(LDFLAGS) $(LIBS)
clean:
	rm -f demo demo3d demo.exe demo3d.exe
'''


def joints_u8(path):
    """rewrite a GLB in place with 8-bit joint indices (JOINTS_0 as unsigned byte) when every index fits: raylib
    5.0 reads only that. Still valid glTF for every other loader. -> number of accessors changed"""
    import struct
    import numpy as np
    raw = open(path, "rb").read()
    if raw[:4] != b"glTF":
        return 0
    jlen = struct.unpack_from("<I", raw, 12)[0]
    gl = json.loads(raw[20:20 + jlen])
    off = 20 + jlen
    blen = struct.unpack_from("<I", raw, off)[0]
    binb = bytearray(raw[off + 8:off + 8 + blen])
    done = 0
    for mesh in gl.get("meshes", []):
        for prim in mesh.get("primitives", []):
            for key in [k for k in prim.get("attributes", {}) if k.startswith("JOINTS_")]:
                acc = gl["accessors"][prim["attributes"][key]]
                if acc.get("componentType") != 5123 or acc.get("sparse"):
                    continue
                bv = gl["bufferViews"][acc["bufferView"]]
                start = bv.get("byteOffset", 0) + acc.get("byteOffset", 0)
                stride = bv.get("byteStride", 8)
                n = acc["count"]
                a = np.frombuffer(bytes(binb[start:start + stride * (n - 1) + 8]), np.uint8)
                rows = np.stack([np.frombuffer(bytes(binb[start + i * stride:start + i * stride + 8]), "<u2") for i in range(n)]) \
                    if stride != 8 else a.view("<u2").reshape(n, 4)
                if rows.max() > 255:
                    continue
                while len(binb) % 4:
                    binb.append(0)
                gl["bufferViews"].append(dict(buffer=0, byteOffset=len(binb), byteLength=n * 4))
                binb += rows.astype(np.uint8).tobytes()
                acc.update(bufferView=len(gl["bufferViews"]) - 1, byteOffset=0, componentType=5121)
                done += 1
    if not done:
        return 0
    while len(binb) % 4:
        binb.append(0)
    gl["buffers"][0]["byteLength"] = len(binb)
    js = json.dumps(gl, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)
    total = 12 + 8 + len(js) + 8 + len(binb)
    with open(path, "wb") as f:
        f.write(struct.pack("<4sII", b"glTF", 2, total))
        f.write(struct.pack("<I4s", len(js), b"JSON")); f.write(js)
        f.write(struct.pack("<I4s", len(binb), b"BIN\0")); f.write(bytes(binb))
    return done


def raylib(chars, dst, game=""):
    idx = copy_characters(chars, os.path.join(dst, "characters"))
    for c in idx:
        if c["model"]:
            joints_u8(os.path.join(dst, "characters", c["dir"], "model.glb"))
    _w(os.path.join(dst, "characters", "index.txt"), "\n".join(c["name"] for c in idx) + "\n")
    _w(os.path.join(dst, "characters", "index3d.txt"), "\n".join(c["name"] for c in idx if c["model"]) + "\n")
    shutil.copy(os.path.join(HERE, "loaders", "raylib", "game_character.h"), os.path.join(dst, "game_character.h"))
    _w(os.path.join(dst, "main.c"), RAYLIB_MAIN)
    _w(os.path.join(dst, "main3d.c"), RAYLIB_3D)
    _w(os.path.join(dst, "Makefile"), RAYLIB_MAKE)
    _readme(dst, "Sprite Forge characters for raylib", "`make` (or `make RAYLIB_PATH=path/to/raylib/src`), then `./demo` "
            "for the sprites (with the hit window shown) and `./demo3d` for the 3D models with their animations. LEFT / "
            "RIGHT change move. raylib 5.5 or newer (5.0 draws the 3D models wrongly).\n\nIn your game: `#define GAME_CHARACTER_IMPLEMENTATION` once, "
            "`#include \"game_character.h\"`, then `GC_Load`, `GC_Play`, `GC_Update`, `GC_Draw`, `GC_HitActive`. "
            "Characters: `characters/`")
    return dst


# ------------------------------------------------------------------ web (canvas 2D + three.js 3D)
WEB_INDEX = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sprite Forge characters</title>
<style>
:root{--bg:#181a22;--fg:#eef0f4;--mute:#9aa3b2;--acc:#f0c43c}
body{margin:0;background:var(--bg);color:var(--fg);font:15px system-ui,sans-serif}
header{display:flex;gap:12px;align-items:center;padding:12px 16px;flex-wrap:wrap}
button{background:#2a2f3c;color:var(--fg);border:1px solid #3a4152;border-radius:6px;padding:6px 12px;cursor:pointer}
#move{font-weight:600;color:var(--acc);min-width:120px}
canvas{display:block;width:100%;image-rendering:pixelated}
a{color:var(--acc)}
</style></head><body>
<header><button id="prev">&larr;</button><span id="move">-</span><button id="next">&rarr;</button>
<span style="color:var(--mute)">LEFT / RIGHT change move &middot; <a href="viewer3d.html">3D models</a></span></header>
<canvas id="c" width="1280" height="640"></canvas>
<script>
// Sprite Forge web player: reads characters/index.json and each game_character.json, draws the strips at their fps.
const cv = document.getElementById('c'), g = cv.getContext('2d');
g.imageSmoothingEnabled = false;
let chars = [], moves = [], mi = 0, t0 = performance.now();
const img = src => new Promise((ok, no) => { const i = new Image(); i.onload = () => ok(i); i.onerror = no; i.src = src; });
async function load() {
  const idx = await (await fetch('characters/index.json')).json();
  for (const c of idx) {
    const m = await (await fetch(`characters/${c.dir}/game_character.json`)).json();
    const strips = {};
    for (const a of m.animations) { strips[a.name] = await img(`characters/${c.dir}/${a.strip}`); if (!moves.includes(a.name)) moves.push(a.name); }
    chars.push({name: c.name, m, strips});
  }
  mi = Math.max(0, moves.indexOf('idle'));
  show(); requestAnimationFrame(draw);
  window.sfReady = {characters: chars.length, moves: moves.length};
}
function show() { document.getElementById('move').textContent = moves[mi] || '-'; t0 = performance.now(); }
function step(d) { mi = (mi + d + moves.length) % moves.length; show(); }
document.getElementById('prev').onclick = () => step(-1);
document.getElementById('next').onclick = () => step(1);
addEventListener('keydown', e => { if (e.key === 'ArrowRight') step(1); if (e.key === 'ArrowLeft') step(-1); });
function eventsNow(a, f) {
  const e = a.events || {}, on = [];
  if (e.hit_start >= 0 && f >= e.hit_start && f <= (e.hit_end >= 0 ? e.hit_end : e.hit_start)) on.push('hit');
  for (const k of ['ball_contact', 'throw_release', 'shoot', 'reload']) if (e[k] === f) on.push(k.replace('_', ' '));
  if ((e.footsteps || []).includes(f)) on.push('step');
  return on;
}
function draw(now) {
  const W = cv.width, H = cv.height, ground = H - 70, n = chars.length || 1;
  g.fillStyle = '#181a22'; g.fillRect(0, 0, W, H);
  g.fillStyle = '#2c3240'; g.fillRect(0, ground, W, H - ground);
  const t = (now - t0) / 1000;
  chars.forEach((c, i) => {
    const a = c.m.animations.find(x => x.name === moves[mi]) || c.m.animations[0];
    let f = Math.floor(t * a.fps); f = a.loop ? f % a.frames : Math.min(f, a.frames - 1);
    const sc = Math.min((H * 0.62) / a.h, (W / n * 1.3) / a.w), x = W * (i + 0.5) / n;
    const px = a.pivot ? a.pivot.x : a.w / 2, py = a.pivot ? a.pivot.y : a.ground_y;
    g.drawImage(c.strips[a.name], f * a.w, 0, a.w, a.h, x - px * sc, ground - py * sc, a.w * sc, a.h * sc);
    g.fillStyle = '#eef0f4'; g.font = '16px system-ui'; g.textAlign = 'center'; g.fillText(c.name, x, ground + 24);
    const on = eventsNow(a, f);
    if (on.length) { g.fillStyle = '#f0c43c'; g.fillText(on.join(', '), x, ground + 46); }
  });
  requestAnimationFrame(draw);
}
load().catch(e => { document.body.insertAdjacentHTML('beforeend', `<p style="padding:16px">Could not load the characters (${e}). Serve this folder: python serve.py</p>`); });
</script></body></html>
'''

WEB_3D = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sprite Forge models</title>
<style>body{margin:0;background:#181a22;color:#eef0f4;font:15px system-ui,sans-serif}
header{padding:10px 16px}a{color:#f0c43c}#move{color:#f0c43c;font-weight:600}</style>
<script type="importmap">{"imports":{"three":"https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js",
"three/addons/":"https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/"}}</script></head><body>
<header><span id="move">-</span> &middot; LEFT / RIGHT change move &middot; <a href="index.html">sprites</a></header>
<script type="module">
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
const r = new THREE.WebGLRenderer({antialias: true}); r.setSize(innerWidth, innerHeight - 40); document.body.appendChild(r.domElement);
const scene = new THREE.Scene(); scene.background = new THREE.Color(0x181a22);
const cam = new THREE.PerspectiveCamera(40, innerWidth / (innerHeight - 40), 0.1, 100);
scene.add(new THREE.HemisphereLight(0xffffff, 0x334455, 2.2));
const sun = new THREE.DirectionalLight(0xffffff, 1.6); sun.position.set(2, 4, 3); scene.add(sun);
scene.add(new THREE.GridHelper(10, 20, 0x445066, 0x2c3240));
const ctl = new OrbitControls(cam, r.domElement); ctl.target.set(0, 0.9, 0);
const mixers = [], sets = []; let names = [], mi = 0;
const idx = await (await fetch('characters/index.json')).json();
const withModel = idx.filter(c => c.model);
const loader = new GLTFLoader();
for (const [i, c] of withModel.entries()) {
  const g = await loader.loadAsync(`characters/${c.dir}/model.glb`);
  g.scene.position.x = (i - (withModel.length - 1) / 2) * 1.1; scene.add(g.scene);
  const mx = new THREE.AnimationMixer(g.scene); mixers.push(mx); sets.push(g.animations);
  for (const a of g.animations) if (!names.includes(a.name)) names.push(a.name);
}
cam.position.set(0, 1.4, 2.6 + withModel.length * 0.6); ctl.update();
function play() {
  document.getElementById('move').textContent = names[mi] || '-';
  mixers.forEach((mx, i) => { mx.stopAllAction(); const c = sets[i].find(a => a.name === names[mi]); if (c) mx.clipAction(c).play(); });
}
mi = Math.max(0, names.indexOf('idle')); play();
addEventListener('keydown', e => { if (!names.length) return; if (e.key === 'ArrowRight') mi = (mi + 1) % names.length; else if (e.key === 'ArrowLeft') mi = (mi + names.length - 1) % names.length; else return; play(); });
const clock = new THREE.Clock();
r.setAnimationLoop(() => { const d = clock.getDelta(); mixers.forEach(m => m.update(d)); r.render(scene, cam); });
window.sfReady3d = {models: withModel.length, animations: names.length};
</script></body></html>
'''

WEB_SERVE = '''"""python serve.py [port] - serve this folder (browsers will not fetch files from file://) and open it."""
import http.server, functools, os, sys, webbrowser
port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=os.path.dirname(os.path.abspath(__file__)))
print("Sprite Forge: http://localhost:%d/" % port)
webbrowser.open("http://localhost:%d/" % port)
http.server.ThreadingHTTPServer(("", port), h).serve_forever()
'''


def web(chars, dst, game=""):
    copy_characters(chars, os.path.join(dst, "characters"))
    _w(os.path.join(dst, "index.html"), WEB_INDEX)
    _w(os.path.join(dst, "viewer3d.html"), WEB_3D)
    _w(os.path.join(dst, "serve.py"), WEB_SERVE)
    _readme(dst, "Sprite Forge characters for the web", "`python serve.py` and the browser opens `index.html`: every "
            "character's sprites at their fps with the move events. `viewer3d.html` shows the 3D models with every move "
            "(three.js from the jsDelivr CDN). For Phaser 3 atlases see `tools/export_engines.py --phaser`. Characters: `characters/`")
    return dst


# ------------------------------------------------------------------ pygame
PYGAME_PLAY = r'''"""Sprite Forge characters in pygame:  python play.py [--shot out.png]   (pip install pygame)
LEFT / RIGHT change move, ESC quits. In your game, Character(folder).play("kick"), .update(dt), .draw(surface, x, ground),
.event_now("ball_contact")."""
import json
import os
import sys

import pygame

HERE = os.path.dirname(os.path.abspath(__file__))


class Character:
    def __init__(self, folder):
        self.m = json.load(open(os.path.join(folder, "game_character.json")))
        self.anims = {a["name"]: a for a in self.m["animations"]}
        self.strips = {a["name"]: pygame.image.load(os.path.join(folder, a["strip"])) for a in self.m["animations"]}
        self.name, self.move, self.t = self.m.get("name", os.path.basename(folder)), None, 0.0
        self.play("idle" if "idle" in self.anims else self.m["animations"][0]["name"])

    def play(self, move):
        if move in self.anims:
            self.move, self.t = move, 0.0

    def update(self, dt):
        self.t += dt

    def frame(self):
        a = self.anims[self.move]
        f = int(self.t * a["fps"])
        return f % a["frames"] if a.get("loop") else min(f, a["frames"] - 1)

    def event_now(self, key):
        e, f = self.anims[self.move].get("events") or {}, self.frame()
        if key == "hit":
            s = e.get("hit_start", -1)
            return s >= 0 and s <= f <= (e.get("hit_end", -1) if e.get("hit_end", -1) >= 0 else s)
        if key == "footstep":
            return f in (e.get("footsteps") or [])
        return e.get(key, -1) == f

    def draw(self, surf, x, ground, height):
        a = self.anims[self.move]
        sc = height / float(a["h"])
        cell = self.strips[self.move].subsurface((self.frame() * a["w"], 0, a["w"], a["h"]))
        img = pygame.transform.scale(cell, (int(a["w"] * sc), int(a["h"] * sc)))
        piv = a.get("pivot") or {"x": a["w"] / 2, "y": a.get("ground_y", a["h"])}
        surf.blit(img, (x - piv["x"] * sc, ground - piv["y"] * sc))


def main():
    shot = sys.argv[sys.argv.index("--shot") + 1] if "--shot" in sys.argv else None
    if shot:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    pygame.init()
    W, H = 1280, 720
    screen = pygame.display.set_mode((W, H))
    pygame.display.set_caption("Sprite Forge characters")
    idx = json.load(open(os.path.join(HERE, "characters", "index.json")))
    chars = [Character(os.path.join(HERE, "characters", c["dir"])) for c in idx]
    moves = []
    for c in chars:
        moves += [m for m in c.anims if m not in moves]
    mi = moves.index("idle") if "idle" in moves else 0
    for c in chars:
        c.play(moves[mi])
    font, clock, n = pygame.font.SysFont(None, 26), pygame.time.Clock(), 0
    while True:
        for e in pygame.event.get():
            if e.type == pygame.QUIT or (e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE):
                pygame.quit(); return 0
            if e.type == pygame.KEYDOWN and e.key in (pygame.K_RIGHT, pygame.K_LEFT):
                mi = (mi + (1 if e.key == pygame.K_RIGHT else -1)) % len(moves)
                for c in chars:
                    c.play(moves[mi])
        dt = 1 / 60.0 if shot else clock.tick(60) / 1000.0
        screen.fill((24, 26, 34))
        ground = H - 90
        pygame.draw.rect(screen, (48, 54, 66), (0, ground, W, H - ground))
        for i, c in enumerate(chars):
            c.update(dt)
            x = W * (i + 0.5) / len(chars)
            c.draw(screen, x, ground, H * 0.62)
            on = [k for k in ("hit", "ball_contact", "throw_release", "shoot", "footstep") if c.event_now(k)]
            t = font.render(c.name + ("  [" + ", ".join(on) + "]" if on else ""), True, (238, 240, 244))
            screen.blit(t, (x - t.get_width() / 2, ground + 12))
        screen.blit(font.render(moves[mi] + "   (LEFT / RIGHT: change move)", True, (240, 196, 60)), (16, 12))
        pygame.display.flip()
        n += 1
        if shot and n >= 20:
            pygame.image.save(screen, shot)
            print("SF_DEMO %d characters, %d moves" % (len(chars), len(moves)))
            pygame.quit(); return 0


if __name__ == "__main__":
    sys.exit(main())
'''


def pygame_(chars, dst, game=""):
    copy_characters(chars, os.path.join(dst, "characters"))
    _w(os.path.join(dst, "play.py"), PYGAME_PLAY)
    _w(os.path.join(dst, "requirements.txt"), "pygame>=2.1\n")
    _readme(dst, "Sprite Forge characters for pygame", "`pip install pygame`, then `python play.py`. LEFT / RIGHT change "
            "move; the events show under each character. `Character` in play.py is the loader to copy into your game. "
            "Characters: `characters/`")
    return dst


MAKERS = dict(godot=godot, unity=unity, unreal=unreal, raylib=raylib, web=web, pygame=pygame_)
LABELS = dict(godot="Godot 4", unity="Unity", unreal="Unreal Engine 5", raylib="raylib (C)", web="Web (canvas + three.js)",
              pygame="pygame (Python)")


def export(engine, src, out):
    """-> {engine: project folder}"""
    game, chars = characters(src)
    if not chars:
        raise ValueError("no characters in %s" % src)
    names = ENGINES if engine == "all" else [engine]
    done = {}
    for e in names:
        if e not in MAKERS:
            raise ValueError("unknown engine %r (%s)" % (e, ", ".join(ENGINES)))
        dst = os.path.join(out, e) if engine == "all" or os.path.basename(out.rstrip("/")) != e else out
        if os.path.isdir(dst):
            shutil.rmtree(dst)
        os.makedirs(dst)
        done[e] = MAKERS[e](chars, dst, game)
    return done


def main(argv):
    import argparse
    ap = argparse.ArgumentParser(prog="forge.py engine", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("engine", help="|".join(ENGINES + ["all", "list"]))
    ap.add_argument("source", nargs="?", help="a build folder or a roster folder")
    ap.add_argument("--out", default="engine_projects")
    a = ap.parse_args(argv)
    if a.engine == "list":
        for e in ENGINES:
            print("  %-8s %s" % (e, LABELS[e]))
        return 0
    if not a.source:
        ap.error("give the build or roster folder")
    try:
        done = export(a.engine, a.source, a.out)
    except ValueError as e:
        print(e); return 2
    for e, d in done.items():
        print("%-8s -> %s" % (e, d))
    return 0
