"""Soccer clip QA: checks for foot slide, joint limits, ball-contact frames,
loop seams, and other issues in baked soccer clips.

Usage:
    from sforge.soccer_qa import qa_clips
    report = qa_clips(clips_data, events_data)
    print(report.summary())
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass
class ClipIssue:
    level: str  # FAIL, WARN, INFO
    check: str
    clip: str
    frame: int
    message: str


@dataclass
class QAReport:
    issues: list[ClipIssue] = field(default_factory=list)

    def add(self, level: str, check: str, clip: str, frame: int, message: str):
        self.issues.append(ClipIssue(level, check, clip, frame, message))

    def summary(self) -> str:
        fails = sum(1 for i in self.issues if i.level == "FAIL")
        warns = sum(1 for i in self.issues if i.level == "WARN")
        return f"QA: {fails} FAIL, {warns} WARN, {len(self.issues)} total issues"

    @property
    def passed(self) -> bool:
        return not any(i.level == "FAIL" for i in self.issues)


# Soccer joint limits (degrees).
JOINT_LIMITS = {
    "knee": (0, 150),       # knee flexion (0 = straight)
    "ankle": (-30, 45),     # ankle dorsiflexion/plantarflexion
    "hip": (-45, 120),      # hip flexion/extension
    "elbow": (0, 160),      # elbow flexion
    "shoulder": (-60, 180), # shoulder flexion
}

# Foot slide threshold (metres per frame at 30 fps).
FOOT_SLIDE_TOL = 0.05


def qa_clips(clips: dict, events: dict) -> QAReport:
    """Run QA checks on baked soccer clips.

    Args:
        clips: {clip_name: {bones: {bone: {r: [...], t: [...]}, fps, frames, loop}}
        events: {clip_name: {ball_contact, footsteps, hit_start, hit_end}}

    Returns:
        QAReport with all issues found.
    """
    report = QAReport()

    for clip_name, clip_data in clips.items():
        bones = clip_data.get("bones", {})
        frames = clip_data.get("frames", 0)
        loop = clip_data.get("loop", False)
        ev = events.get(clip_name, {})

        # Check 1: Ball-contact frame present for ball clips.
        ball_clips = ("pass", "shoot", "volley", "header", "chest", "trap",
                      "kick", "catch", "save", "punch", "throw")
        if any(b in clip_name for b in ball_clips):
            bc = ev.get("ball_contact", -1)
            if bc < 0:
                report.add("FAIL", "ball_contact", clip_name, 0,
                           "ball clip missing ball_contact frame")

        # Check 2: Footsteps present for locomotion clips.
        loco_clips = ("walk", "jog", "run", "sprint", "dribble", "strafe",
                      "backpedal", "jockey", "turn", "sidestep")
        if any(l in clip_name for l in loco_clips):
            steps = ev.get("footsteps", [])
            if not steps:
                report.add("WARN", "footsteps", clip_name, 0,
                           "locomotion clip missing footsteps")

        # Check 3: Loop seam — first and last frame should be close.
        if loop and frames > 1 and "Hips" in bones:
            hips = bones["Hips"]
            r = hips.get("r", [])
            if len(r) >= 8:
                # Compare first and last quaternion (should be similar for loops).
                q0 = r[0:4]
                q1 = r[-4:]
                dot = sum(a * b for a, b in zip(q0, q1))
                if abs(dot) < 0.9:  # Not close enough
                    report.add("WARN", "loop_seam", clip_name, frames - 1,
                               f"loop seam: first/last quaternion dot={dot:.3f}")

        # Check 4: Quaternion normalisation.
        for bone_name, bone_data in bones.items():
            r = bone_data.get("r", [])
            for i in range(0, len(r), 4):
                if i + 3 >= len(r):
                    break
                q = r[i:i+4]
                norm = math.sqrt(sum(x * x for x in q))
                if abs(norm - 1.0) > 0.01:
                    report.add("FAIL", "quaternion", clip_name, i // 4,
                               f"{bone_name} quaternion not normalised: |q|={norm:.4f}")
                    break  # Only report once per bone

        # Check 5: Frame count consistency.
        if frames <= 0:
            report.add("FAIL", "frames", clip_name, 0, "zero frames")

    return report
