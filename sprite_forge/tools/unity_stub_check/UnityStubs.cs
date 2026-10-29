// Minimal API-shape stubs of UnityEngine / UnityEditor - ONLY for a compile check of the Sprite Forge package outside Unity.
using System;
using System.Collections.Generic;
namespace UnityEngine {
  public class Object { public string name; public static void DestroyImmediate(Object o) {} public static implicit operator bool(Object o) { return o != null; } }
  public struct Vector2 { public float x, y; public Vector2(float x, float y) { this.x = x; this.y = y; } public static implicit operator Vector3(Vector2 v) { return new Vector3(v.x, v.y, 0); } }
  public struct Vector3 { public float x, y, z; public Vector3(float x, float y, float z) { this.x = x; this.y = y; this.z = z; } }
  public struct Color { public Color(float r, float g, float b, float a) {} }
  public struct Rect { public Rect(float x, float y, float w, float h) { this.x = x; this.y = y; width = w; height = h; } public float x, y, width, height; public Vector2 center { get { return new Vector2(x + width / 2, y + height / 2); } } public Vector2 size { get { return new Vector2(width, height); } } }
  public enum SpriteAlignment { Center, TopLeft, TopCenter, TopRight, LeftCenter, RightCenter, BottomLeft, BottomCenter, BottomRight, Custom }
  public class Sprite : Object {}
  public class Texture : Object {} public class Texture2D : Texture {}
  public class Component : Object { public GameObject gameObject; public Transform transform; public T GetComponent<T>() { return default(T); } }
  public class Behaviour : Component { public bool enabled; }
  public class MonoBehaviour : Behaviour {}
  public class ScriptableObject : Object { public static T CreateInstance<T>() where T : ScriptableObject, new() { return new T(); } }
  public class Transform : Component { public Transform Find(string n) { return null; } public void SetParent(Transform p, bool w) {} public Vector3 TransformPoint(Vector3 v) { return v; } public Vector3 TransformVector(Vector3 v) { return v; } }
  public class GameObject : Object { public GameObject(string n) {} public Transform transform; public T AddComponent<T>() where T : Component, new() { return new T(); } public T GetComponent<T>() { return default(T); } }
  public class SpriteRenderer : Component { public Sprite sprite; public bool flipX; }
  public class RuntimeAnimatorController : Object {}
  public class Animator : Behaviour { public RuntimeAnimatorController runtimeAnimatorController; }
  public class Collider2D : Behaviour { public bool isTrigger; public Vector2 offset; }
  public class BoxCollider2D : Collider2D { public Vector2 size; }
  public class Motion : Object {}
  public class AnimationClip : Motion { public float frameRate; }
  public static class Gizmos { public static Color color; public static void DrawWireCube(Vector3 c, Vector3 s) {} }
  public static class Mathf { public static int FloorToInt(float f) { return (int)Math.Floor(f); } public static float Max(float a, float b) { return Math.Max(a, b); } }
  public static class Time { public static float deltaTime; }
  public static class Debug { public static void Log(object o) {} public static void LogWarning(object o) {} public static void LogError(object o) {} }
  public static class Application { public static string dataPath = ""; }
  public class RequireComponent : Attribute { public RequireComponent(Type t) {} }
  public class CreateAssetMenuAttribute : Attribute { public string menuName; }
}
namespace UnityEditor {
  using UnityEngine;
  public class MenuItem : Attribute { public MenuItem(string p) {} }
  public enum ImportAssetOptions { Default, ForceSynchronousImport }
  public enum TextureImporterType { Default, Sprite }
  public enum SpriteImportMode { None, Single, Multiple }
  public enum TextureImporterCompression { Uncompressed, Compressed }
  public struct SpriteMetaData { public string name; public Rect rect; public int alignment; public Vector2 pivot; }
  public struct SecondarySpriteTexture { public string name; public Texture2D texture; }
  public class AssetImporter : Object { public static AssetImporter GetAtPath(string p) { return null; } public void SaveAndReimport() {} }
  public class TextureImporter : AssetImporter { public TextureImporterType textureType; public SpriteImportMode spriteImportMode; public float spritePixelsPerUnit; public bool alphaIsTransparency, mipmapEnabled, sRGBTexture; public TextureImporterCompression textureCompression; public int maxTextureSize; [Obsolete] public SpriteMetaData[] spritesheet; public SecondarySpriteTexture[] secondarySpriteTextures; public void GetSourceTextureWidthAndHeight(out int w, out int h) { w = h = 0; } }
  public static class AssetDatabase { public static void ImportAsset(string p, ImportAssetOptions o) {} public static T LoadAssetAtPath<T>(string p) where T : Object { return null; } public static Object[] LoadAllAssetsAtPath(string p) { return new Object[0]; } public static void CreateAsset(Object o, string p) {} public static void SaveAssets() {} }
  public static class EditorUtility { public static string OpenFolderPanel(string t, string f, string d) { return ""; } public static bool DisplayDialog(string a, string b, string c) { return true; } }
  public struct EditorCurveBinding { public static EditorCurveBinding PPtrCurve(string p, Type t, string n) { return new EditorCurveBinding(); } }
  public struct ObjectReferenceKeyframe { public float time; public Object value; }
  public class AnimationClipSettings { public bool loopTime; }
  public static class AnimationUtility { public static void SetObjectReferenceCurve(AnimationClip c, EditorCurveBinding b, ObjectReferenceKeyframe[] k) {} public static AnimationClipSettings GetAnimationClipSettings(AnimationClip c) { return new AnimationClipSettings(); } public static void SetAnimationClipSettings(AnimationClip c, AnimationClipSettings s) {} }
  public static class PrefabUtility { public static GameObject SaveAsPrefabAsset(GameObject g, string p) { return g; } }
}
namespace UnityEditor.Animations {
  using UnityEngine;
  public class AnimatorState { public Motion motion; }
  public class AnimatorStateMachine { public AnimatorState defaultState; public AnimatorState AddState(string n) { return new AnimatorState(); } }
  public class AnimatorControllerLayer { public AnimatorStateMachine stateMachine; }
  public class AnimatorController : RuntimeAnimatorController { public AnimatorControllerLayer[] layers; public static AnimatorController CreateAnimatorControllerAtPath(string p) { return null; } }
}
