"""A recording stand-in for Unreal Engine's `unreal` Python module - only what Sprite Forge's import script uses.

It is not Unreal: it checks that the script calls the documented UE5 Python API (class, function and property names,
argument counts) with sensible values, and records what an import would make. Install it with install(project_dir)
before importing sprite_forge_import; read the results from LOG.
"""
from __future__ import annotations
import os
import sys
import types

LOG = dict(assets={}, imports=[], props=[], markers=[], tracks=[], actors=[], levels=[], saved=[], logs=[])
PROJECT = [""]


class _Obj:
    _props = ()          # the editor properties this class has in UE5 (set_editor_property on anything else fails in UE)

    def __init__(self, name="", path=""):
        self._name, self._path, self._p = name, path, {}

    def set_editor_property(self, k, v):
        if self._props and k not in self._props:
            raise AttributeError("%s has no editor property %r" % (type(self).__name__, k))
        self._p[k] = v
        LOG["props"].append((type(self).__name__, self._name, k))

    def get_editor_property(self, k):
        if k not in self._p and k in ("render_component", "skeletal_mesh_component"):
            self._p[k] = _Component(self)
        return self._p.get(k)

    def get_name(self):
        return self._name

    def get_path_name(self):
        return self._path


class Texture2D(_Obj):
    _props = ("filter", "compression_settings", "mip_gen_settings", "lod_group")


class PaperSprite(_Obj):
    _props = ("source_texture", "source_uv", "source_dimension", "pivot_mode", "custom_pivot_point", "pixels_per_unreal_unit")


class PaperFlipbook(_Obj):
    _props = ("frames_per_second", "key_frames", "collision_source", "default_material")


class SkeletalMesh(_Obj):
    pass


class AnimSequence(_Obj):
    length = 1.0


class PaperSpriteFactory(_Obj):
    pass


class PaperFlipbookFactory(_Obj):
    pass


class FbxImportUI(_Obj):
    _props = ("import_mesh", "import_as_skeletal", "import_animations", "import_materials", "import_textures", "mesh_type_to_import")


class AssetImportTask(_Obj):
    _props = ("filename", "destination_path", "automated", "replace_existing", "save", "options", "imported_object_paths")


class Vector2D:
    def __init__(self, x=0.0, y=0.0):
        self.x, self.y = float(x), float(y)


class Vector:
    def __init__(self, x=0.0, y=0.0, z=0.0):
        self.x, self.y, self.z = x, y, z


class Rotator:
    def __init__(self, roll=0.0, pitch=0.0, yaw=0.0):
        self.r = (roll, pitch, yaw)


class PaperFlipbookKeyFrame:
    def __init__(self, sprite=None, frame_run=1):
        if not isinstance(sprite, PaperSprite):
            raise TypeError("key frame sprite must be a PaperSprite")
        self.sprite, self.frame_run = sprite, frame_run


class AssetRenameData:
    def __init__(self, asset, new_package_path, new_name):
        self.asset, self.path, self.name = asset, new_package_path, new_name


def _enum(name, *vals):
    return type(name, (), {v: v for v in vals})


TextureFilter = _enum("TextureFilter", "TF_NEAREST", "TF_DEFAULT")
TextureCompressionSettings = _enum("TextureCompressionSettings", "TC_EDITOR_ICON", "TC_DEFAULT")
TextureMipGenSettings = _enum("TextureMipGenSettings", "TMGS_NO_MIPMAPS")
TextureGroup = _enum("TextureGroup", "TEXTUREGROUP_PIXELS2D")
SpritePivotMode = _enum("SpritePivotMode", "CUSTOM", "BOTTOM_CENTER")
FBXImportType = _enum("FBXImportType", "FBXIT_SKELETAL_MESH", "FBXIT_STATIC_MESH")
AnimationMode = _enum("AnimationMode", "ANIMATION_SINGLE_NODE", "ANIMATION_BLUEPRINT")


class _AssetTools:
    def import_asset_tasks(self, tasks):
        for t in tasks:
            f, dest = t._p["filename"], t._p["destination_path"]
            if not os.path.isfile(f):
                raise IOError("import of a missing file " + f)
            base = os.path.splitext(os.path.basename(f))[0]
            LOG["imports"].append((f, dest, type(t._p.get("options")).__name__ if t._p.get("options") else ""))
            made = []
            if f.lower().endswith(".png"):
                p = "%s/%s" % (dest, base)
                LOG["assets"][p] = Texture2D(base, p)
                made.append(p + "." + base)
            elif f.lower().endswith(".fbx"):
                p = "%s/%s" % (dest, base)
                LOG["assets"][p] = SkeletalMesh(base, p)
                made.append(p + "." + base)
                from sforge.importers import load_file           # the takes really in the FBX
                rig = load_file(f)[0]
                for take, clip in rig.clips.items():
                    q = "%s/%s_Anim_%s" % (dest, base, take)
                    a = AnimSequence("%s_Anim_%s" % (base, take), q)
                    a.length = float(clip.duration)
                    LOG["assets"][q] = a
                    made.append(q + "." + a._name)
            t._p["imported_object_paths"] = made

    def create_asset(self, name, path, cls, factory):
        if not issubclass(cls, _Obj):
            raise TypeError(cls)
        want = {PaperSprite: PaperSpriteFactory, PaperFlipbook: PaperFlipbookFactory}[cls]
        if not isinstance(factory, want):
            raise TypeError("%s needs a %s" % (cls.__name__, want.__name__))
        p = "%s/%s" % (path, name)
        LOG["assets"][p] = cls(name, p)
        return LOG["assets"][p]

    def rename_assets(self, items):
        for it in items:
            old = it.asset._path
            new = "%s/%s" % (it.path, it.name)
            LOG["assets"][new] = LOG["assets"].pop(old)
            it.asset._name, it.asset._path = it.name, new
        return True


class AssetToolsHelpers:
    @staticmethod
    def get_asset_tools():
        return _AssetTools()


class EditorAssetLibrary:
    @staticmethod
    def load_asset(path):
        if path not in LOG["assets"]:
            raise KeyError("no asset " + path)
        return LOG["assets"][path]

    @staticmethod
    def save_loaded_asset(a):
        LOG["saved"].append(a._path)
        return True

    @staticmethod
    def list_assets(path, recursive=True, include_folder=False):
        return [p + "." + p.rsplit("/", 1)[1] for p in LOG["assets"] if p.startswith(path + "/")]

    @staticmethod
    def save_directory(path):
        LOG["saved"].append(path)
        return True


class AnimationLibrary:
    @staticmethod
    def get_sequence_length(seq):
        return seq.length

    @staticmethod
    def add_animation_notify_track(seq, track, track_color=None):
        LOG["tracks"].append((seq._name, track))

    @staticmethod
    def add_animation_sync_marker(seq, marker, time, track):
        if (seq._name, track) not in LOG["tracks"]:
            raise RuntimeError("sync marker on a track that was not added")
        if not 0.0 <= time <= seq.length + 1e-6:
            raise ValueError("marker %s at %.3f outside 0..%.3f" % (marker, time, seq.length))
        LOG["markers"].append((seq._path, marker, time))


class _Component:
    def __init__(self, owner):
        self.owner = owner

    def set_flipbook(self, fb):
        if not isinstance(fb, PaperFlipbook):
            raise TypeError(fb)
        self.owner._fb = fb
        return True

    def set_skeletal_mesh_asset(self, m):
        if not isinstance(m, SkeletalMesh):
            raise TypeError(m)
        self.owner._mesh = m

    def set_animation_mode(self, mode):
        self.owner._mode = mode

    def override_animation_data(self, anim, looping, playing, position, rate):
        if not isinstance(anim, AnimSequence):
            raise TypeError(anim)
        self.owner._anim = anim


class PaperFlipbookActor(_Obj):
    pass


class SkeletalMeshActor(_Obj):
    pass


class _ActorSub:
    def spawn_actor_from_class(self, cls, loc, rot):
        a = cls(cls.__name__)
        a.set_actor_label = lambda s, a=a: setattr(a, "_label", s)
        LOG["actors"].append(a)
        return a


class _LevelSub:
    def new_level(self, path):
        LOG["levels"].append(path)
        return True

    def save_current_level(self):
        LOG["saved"].append("level")
        return True


class EditorActorSubsystem:
    pass


class LevelEditorSubsystem:
    pass


def get_editor_subsystem(cls):
    return {EditorActorSubsystem: _ActorSub, LevelEditorSubsystem: _LevelSub}[cls]()


class ScopedSlowTask:
    def __init__(self, work, desc=""):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def make_dialog(self, can_cancel=False):
        pass

    def enter_progress_frame(self, work=1, desc=""):
        pass


class Paths:
    @staticmethod
    def project_dir():
        return PROJECT[0] + "/"

    @staticmethod
    def convert_relative_path_to_full(p):
        return os.path.abspath(p)


def log(s):
    LOG["logs"].append(s)


def log_warning(s):
    LOG["logs"].append("WARNING " + s)


def install(project_dir):
    """make `import unreal` give this stand-in, pointed at project_dir. -> the module"""
    for k in LOG:
        LOG[k] = {} if k == "assets" else []
    PROJECT[0] = os.path.abspath(project_dir)
    mod = types.ModuleType("unreal")
    for k, v in globals().items():
        if not k.startswith("__") and k not in ("install", "types", "sys", "os"):
            setattr(mod, k, v)
    sys.modules["unreal"] = mod
    return mod
