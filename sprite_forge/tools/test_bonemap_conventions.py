#!/usr/bin/env python3
"""v11.35: bone-naming conventions - classic BVH mocap names map right, and the others still win
their own skeletons.

    python tools/test_bonemap_conventions.py
"""
from __future__ import annotations
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sforge import bonemap as BM  # noqa: E402

passed = failed = 0


def check(name, ok, detail=""):
    global passed, failed
    if ok: passed += 1; print("  PASS  " + name)
    else: failed += 1; print("  FAIL  " + name + ("  " + detail if detail else ""))


# 100STYLE's skeleton (joint named after where the bone starts)
CLASSIC = ("Hips Chest Chest2 Chest3 Chest4 Neck Head RightCollar RightShoulder RightElbow RightWrist LeftCollar "
           "LeftShoulder LeftElbow LeftWrist RightHip RightKnee RightAnkle RightToe LeftHip LeftKnee LeftAnkle LeftToe").split()
conv, m, _ = BM.detect_convention(CLASSIC)
check("classic BVH names detected as bvh_classic", conv == "bvh_classic", conv)
check("{S}Hip is the thigh, {S}Shoulder the upper arm, {S}Collar the clavicle",
      m.get("thigh_L") == "LeftHip" and m.get("upperarm_R") == "RightShoulder" and m.get("shoulder_R") == "RightCollar"
      and m.get("forearm_L") == "LeftElbow" and m.get("hand_L") == "LeftWrist", str(m))
check("every required bone found", all(k in m for k in BM.REQUIRED), str([k for k in BM.REQUIRED if k not in m]))

MIXAMO = ["mixamorig:" + b for b in ("Hips Spine Spine1 Spine2 Neck Head LeftShoulder LeftArm LeftForeArm LeftHand RightShoulder "
                                     "RightArm RightForeArm RightHand LeftUpLeg LeftLeg LeftFoot LeftToeBase RightUpLeg RightLeg "
                                     "RightFoot RightToeBase").split()]
check("Mixamo still Mixamo (its LeftShoulder stays the clavicle)", BM.detect_convention(MIXAMO)[0] == "mixamo"
      and BM.detect_convention(MIXAMO)[1].get("shoulder_L") == "mixamorig:LeftShoulder")
UNITY = ("Hips Spine Chest UpperChest Neck Head LeftShoulder LeftUpperArm LeftLowerArm LeftHand RightShoulder RightUpperArm "
         "RightLowerArm RightHand LeftUpperLeg LeftLowerLeg LeftFoot LeftToes RightUpperLeg RightLowerLeg RightFoot RightToes").split()
check("Unity humanoid still Unity", BM.detect_convention(UNITY)[0] == "unity")
UNREAL = ("pelvis spine_01 spine_02 spine_03 neck_01 head clavicle_l upperarm_l lowerarm_l hand_l clavicle_r upperarm_r "
          "lowerarm_r hand_r thigh_l calf_l foot_l ball_l thigh_r calf_r foot_r ball_r").split()
check("UE still Unreal", BM.detect_convention(UNREAL)[0] == "unreal")
print("RESULT: %d passed, %d failed" % (passed, failed))
sys.exit(1 if failed else 0)
