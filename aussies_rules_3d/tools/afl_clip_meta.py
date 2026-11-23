"""AFL clip metadata — the authored contract shared by the feature baker, the
runtime manifest writer and the motion engine. Values are estimates derived from
the clip names and typical technique; they steer selection, they do not schedule
the simulation. ball_contact fractions are fractions OF THE CLIP where the boot
meets the Sherrin (or, for bounces/pickups, the ball is touched)."""

# id: (category, ballState, contactFraction, preferredSpeed m/s, preferredTurnRate rad/s, loop)
CLIP_META = {
    "idle":             ("Idle",       "None",        -1,    0.0, 0.0, True),
    "jog":              ("Locomotion", "None",         -1,    1.6, 0.0, True),
    "run":              ("Locomotion", "None",         -1,    4.9, 0.0, True),
    "solo":             ("Locomotion", "Possessed",    0.42,  3.4, 0.0, True),
    "solo_left":        ("Locomotion", "Possessed",    0.42,  3.4, 0.0, True),
    "toe_lift":         ("Locomotion", "Possessed",    0.45,  4.0, 0.0, True),
    "run_ball":         ("Locomotion", "Possessed",    -1,    4.4, 0.0, True),
    "kick_run":         ("Locomotion", "Possessed",    0.55,  4.6, 0.0, True),
    "sidestep":         ("Cut",        "None",         -1,    2.5, 2.2, False),
    "drop_kick":        ("Kick",       "Possessed",    0.52,  0.0, 0.0, False),
    "kick_place":       ("Kick",       "Possessed",    0.56,  0.0, 0.0, False),
    "kick_out":         ("Kick",       "Possessed",    0.50,  0.0, 0.0, False),
    "hand_pass":        ("Pass",       "Possessed",    0.44,  0.0, 0.0, False),
    "pickup":           ("Approach",   "Approaching",  0.55,  0.0, 0.0, False),
    "catch":            ("Approach",   "Aerial",       0.50,  0.0, 0.0, False),
    "hook":             ("Tackle",     "Contested",    0.40,  0.0, 0.0, False),
    "tackle_reach":     ("Tackle",     "None",         -1,    0.0, 0.0, False),
    "head_hit":         ("Recovery",   "None",         -1,    0.0, 0.0, False),
    "hit_react":        ("Recovery",   "None",         -1,    0.0, 0.0, False),
    "knocked_down":     ("Recovery",   "None",         -1,    0.0, 0.0, False),
    "trip":             ("Recovery",   "None",         -1,    0.0, 0.0, False),
    "stumble":          ("Recovery",   "None",         -1,    0.0, 0.0, False),
    "pushed":           ("Recovery",   "None",         -1,    0.0, 0.0, False),
    "dive_roll":        ("Recovery",   "None",         -1,    0.0, 0.0, False),
    "get_up":           ("Recovery",   "None",         -1,    0.0, 0.0, False),
    "celebrate_jump":   ("Celebrate",  "None",         -1,    0.0, 0.0, False),
    "keeper_idle":      ("Keeper",     "None",         -1,    0.0, 0.0, True),
    "keeper_ready":     ("Keeper",     "None",         -1,    0.0, 0.0, True),
    "keeper_high_catch":("KeeperDive", "Aerial",       0.45,  0.0, 0.0, False),
    "keeper_scoop":     ("KeeperDive", "Approaching",  0.50,  0.0, 0.0, False),
    "dive_high":        ("KeeperDive", "Aerial",       0.40,  0.0, 0.0, False),
    "dive_save":        ("KeeperDive", "Contested",    0.45,  0.0, 0.0, False),
}
