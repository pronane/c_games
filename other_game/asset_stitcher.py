import os
import json
import glob
from PIL import Image

def build_master_pipeline(asset_name, frame_width=128, frame_height=128):
    """
    Scans the current folder for matching frame slices, stitches them into a
    master grid, and generates a structured JSON manifest for the game engine.
    """
    # 1. Gather all PNG slices named like: walk_0.png, walk_1.png, run_0.png, etc.
    all_files = glob.glob("*.png")
    
    # Categorize actions based on prefixes
    action_map = {}
    for f in all_files:
        if "_" in f and f != "master_sheet.png":
            parts = f.rsplit("_", 1)
            action = parts[0]
            try:
                frame_idx = int(parts[1].split(".")[0])
                if action not in action_map:
                    action_map[action] = []
                action_map[action].append((frame_idx, f))
            except ValueError:
                continue

    if not action_map:
        print("❌ No valid frame files found! Name your files like 'walk_0.png', 'walk_1.png'.")
        return

    # Sort frames sequentially inside each action group
    actions = sorted(list(action_map.keys()))
    max_frames = 0
    for action in actions:
        action_map[action].sort()
        if len(action_map[action]) > max_frames:
            max_frames = len(action_map[action])

    # 2. Calculate canvas boundaries
    total_cols = max_frames
    total_rows = len(actions)
    canvas_width = frame_width * total_cols
    canvas_height = frame_height * total_rows

    # Instantiate transparent canvas
    master_canvas = Image.new("RGBA", (canvas_width, canvas_height), (0, 0, 0, 0))
    
    # Engine JSON Metadata Manifest Blueprint
    manifest = {
        "meta": {
            "asset_name": asset_name,
            "frame_width": frame_width,
            "frame_height": frame_height,
            "total_width": canvas_width,
            "total_height": canvas_height,
            "actions_list": actions
        },
        "frames": {}
    }

    # 3. Stitch images into coordinates
    for row_idx, action in enumerate(actions):
        manifest["frames"][action] = []
        for col_idx, (frame_num, file_path) in enumerate(action_map[action]):
            try:
                img_frame = Image.open(file_path).convert("RGBA")
                # Enforce safety resizing constraint
                img_frame = img_frame.resize((frame_width, frame_height), Image.Resampling.NEAREST)
                
                pos_x = col_idx * frame_width
                pos_y = row_idx * frame_height
                
                # Composite frame slice safely onto master sheet canvas
                master_canvas.paste(img_frame, (pos_x, pos_y), img_frame)
                
                # Append slice records to metadata
                manifest["frames"][action].append({
                    "frame_index": frame_num,
                    "x": pos_x,
                    "y": pos_y,
                    "w": frame_width,
                    "h": frame_height
                })
            except Exception as e:
                print(f"⚠️ Error compiling file {file_path}: {e}")

    # Save finalized workspace deployment maps
    master_canvas.save("master_sheet.png", "PNG")
    with open("master_manifest.json", "w") as f:
        json.dump(manifest, f, indent=4)

    print("✔ [Success] Generated compiled asset matrix map: master_sheet.png")
    print("✔ [Success] Generated engine atlas rules map: master_manifest.json")

if __name__ == "__main__":
    # Test execution assuming standard cell dimensions
    build_master_pipeline(asset_name="game_hero", frame_width=128, frame_height=128)
