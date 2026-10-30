"""Match simulation for PEIL 26.

The clock, restarts, and fouls follow the 2026 Gaelic football playing
rules. Human input is a plain snapshot so the renderer and the tests can
both drive a match without pygame.
"""

from __future__ import annotations

import math
import random
from collections import deque
from dataclasses import dataclass

from peil26 import ai
from peil26.rules import (
    ballistics,
    card_result,
    clamp,
    classify_crossing,
    dist,
    dist_to_goal,
    gk_receive_legal,
    in_large_rectangle,
    in_small_square,
    inside_20,
    mark_type,
    on_or_outside_arc,
    solo_and_go_ok,
    structure_ok,
    two_point_strike,
)
from peil26.settings import (
    ATTACK_HALF_ROLES,
    BALL_R,
    CENTER_Z,
    CROSSBAR,
    EXTRA_HALF_MIN,
    GRAVITY,
    HALF,
    MAX_SUBS,
    OWN_HALF_ROLES,
    PENALTY_DIST,
    PITCH_L,
    PITCH_W,
    SIN_BIN_MIN,
    STEP_M,
)
from peil26.teams import formation_of, make_team

GOAL_LINES = [
    "Goal. The net is shaking.",
    "Goal. That finish had nerve in it.",
    "He picked his spot and buried it.",
]
POINT_LINES = [
    "Point. A clean strike between the posts.",
    "Over the bar, and the umpire is reaching.",
    "That's a score, taken with real balance.",
]
TWO_LINES = [
    "Two points. He stood outside the arc.",
    "Two points. That is a huge score in this game.",
    "From on the 40, and he made no mistake.",
]


@dataclass
class HumanInput:
    move_x: float = 0.0
    move_z: float = 0.0
    sprint: bool = False
    kick_held: bool = False
    kick_pressed: bool = False
    kick_released: bool = False
    hand: bool = False
    fist: bool = False
    hook: bool = False
    solo: bool = False
    bounce: bool = False
    tackle: bool = False
    block: bool = False
    sidestep: bool = False
    switch: bool = False
    mark: bool = False
    confirm: bool = False
    jump: bool = False
    to_arc: bool = False
    aim: tuple | None = None
    aim_high: bool | None = None


class Ball:
    def __init__(self):
        self.x = HALF
        self.y = 0.22
        self.z = CENTER_Z
        self.vx = self.vy = self.vz = 0.0
        self.px = self.x
        self.py = self.y
        self.pz = self.z
        self.holder = None
        self.in_flight = False
        self.kick_type = None
        self.kick_origin = (HALF, CENTER_Z)
        self.kicker_pid = None
        self.kicker_team = None
        self.kicker_dist = 0.0
        self.two_point = False
        self.teammate_touched = False
        self.bounced = False
        self.set_kind = None
        self.from_mark = False
        self.square_at_kick = False
        self.last_team = None
        self.last_pid = None
        self.curve = 0.0
        self.curve_t = 0.0
        self.spin = 0.0
        self.resolved = False
        self.kickout_goal = None
        self.hooter_flight = False
        self.attacker_touch_after_hooter = False

    @property
    def held(self) -> bool:
        return self.holder is not None


class Match:
    def __init__(
        self,
        home: str = "Dublin",
        away: str = "Kerry",
        half_minutes: int = 35,
        difficulty: str = "medium",
        human_team: int | None = 0,
        time_scale: float = 10.0,
        seed: int = 7,
        allow_extra: bool = True,
        auto_continue: bool = False,
        intro: float = 3.0,
    ):
        self.rng = random.Random(seed)
        self.difficulty = difficulty if difficulty in ("easy", "medium", "hard") else "medium"
        self.human_team = human_team
        self.time_scale = time_scale
        self.allow_extra = allow_extra
        self.auto_continue = auto_continue
        self.teams = [make_team(0, home, seed), make_team(1, away, seed + 19)]
        self.players = self.teams[0].players + self.teams[1].players
        self.ball = Ball()
        self.attack_positive = [True, False]
        self.period = 1
        self.normal_length = half_minutes * 60.0
        self.half_length = self.normal_length
        self.clock = 0.0
        self.clock_running = False
        self.hooter_sounded = False
        self.hooter_one_kick = False
        self.phase = "countdown"
        self.countdown = 0.3 if auto_continue else intro
        self.phase_t = 0.0
        self.real_time = 0.0
        self.possession_team = None
        self.controlled = None
        self.saved_control = None
        self.autoswitch = True
        self.switch_i = 0
        self.charge = 0.0
        self.hint = "Get ready for the throw-in"
        self.lock_pid = None
        self.banner = "PEIL PARK"
        self.banner_sub = "1 v 1 throw-in. Everyone else behind the 45."
        self.banner_kind = "info"
        self.banner_t = 3.0
        self.ticker = deque(maxlen=6)
        self.sfx = []
        self.tip = "Four steps, then solo or bounce. A point from outside the gold arc is worth two."
        self.tip_t = 7.0
        self.set_kind = None
        self.set_team = None
        self.taker = None
        self.set_x = HALF
        self.set_z = CENTER_Z
        self.set_timer = 0.0
        self.free_can_arc = False
        self.kickout_team = 0
        self.celebrate_t = 0.0
        self.after_celebrate = None
        self.solo_team = None
        self.solo_x = self.solo_z = 0.0
        self.solo_t = 0.0
        self.solo_started = False
        self.mark_pid = None
        self.mark_kind = None
        self.mark_x = self.mark_z = 0.0
        self.mark_t = 0.0
        self.mark_advantage_t = 0.0
        self.mark_back = None
        self.restart_grace = 0.0
        self.foul_cd = 0.0
        self.breach_t = [0.0, 0.0]
        self.shape = [(4, 3), (4, 3)]
        self.call_t = 0.0
        self.call_pid = None
        self.contestants = (None, None)
        self.throw_t = 0.0
        self.throw_jumps = {}
        self.ref_x = HALF
        self.ref_z = 18.0
        self.ref_facing = 0.0
        self.history = []
        self.replay_clip = []
        self._rec_acc = 0.0
        self.post_cd = 0.0
        self.last_scorer = ""
        self.extra_started = False
        self.venue = "Peil Park"
        self._place_throw_in()
        if human_team is not None:
            starter = self._by_role(human_team, "chf")
            self.controlled = starter.pid
        self._say("THROW-IN", "info", time=2.2)

    # ------------------------------------------------------------------
    # Geometry helpers
    # ------------------------------------------------------------------
    def attack_sign(self, team: int) -> float:
        return 1.0 if self.attack_positive[team] else -1.0

    def own_goal_x(self, team: int) -> float:
        return 0.0 if self.attack_positive[team] else PITCH_L

    def attack_goal_x(self, team: int) -> float:
        return PITCH_L if self.attack_positive[team] else 0.0

    def in_own_half(self, team: int, x: float) -> bool:
        if self.attack_positive[team]:
            return x <= HALF + 0.35
        return x >= HALF - 0.35

    def _team_attacking(self, goal_x: float) -> int:
        for t in (0, 1):
            if abs(self.attack_goal_x(t) - goal_x) < 1.0:
                return t
        return 0

    def player_by_pid(self, pid):
        if pid is None:
            return None
        for p in self.players:
            if p.pid == pid:
                return p
        return None

    def controlled_player(self):
        return self.player_by_pid(self.controlled)

    def _by_role(self, team: int, role: str):
        for p in self.teams[team].players:
            if p.role == role and p.active:
                return p
        for p in self.teams[team].players:
            if p.active:
                return p
        return self.teams[team].players[0]

    def slot(self, p):
        return formation_of(p.role if p.role in ("gk", "rcb", "fb", "lcb", "rhb", "chb", "lhb", "mf1", "mf2", "rhf", "chf", "lhf", "rff", "ff", "lff") else "mf1")

    def slot_world(self, team: int, depth: float, zf: float) -> tuple[float, float]:
        gx = self.own_goal_x(team)
        sign = self.attack_sign(team)
        x = gx + sign * (5.0 + depth * (PITCH_L - 12.0))
        z = 5.0 + zf * (PITCH_W - 10.0)
        return x, z

    def gk_pass_would_be_legal(self, kicker, gk) -> bool:
        if gk.role != "gk":
            return True
        own = self.own_goal_x(gk.team)
        both = in_large_rectangle(kicker.x, kicker.z, own) and in_large_rectangle(gk.x, gk.z, own)
        gk_up = not self.in_own_half(gk.team, gk.x)
        return gk_receive_legal(gk_up, both)

    def clock_str(self) -> str:
        t = int(self.clock)
        return f"{t // 60}:{t % 60:02d}"

    def period_name(self) -> str:
        return {1: "FIRST HALF", 2: "SECOND HALF", 3: "EXTRA TIME", 4: "EXTRA TIME"}.get(self.period, "")

    def _tied(self) -> bool:
        return self.teams[0].total == self.teams[1].total

    # ------------------------------------------------------------------
    # Loop
    # ------------------------------------------------------------------
    def update(self, dt: float, inp: HumanInput | None = None):
        dt = max(0.0, min(0.05, float(dt)))
        inp = inp or HumanInput()
        self.sfx = []
        self.real_time += dt
        self.banner_t = max(0.0, self.banner_t - dt)
        self.tip_t = max(0.0, self.tip_t - dt)
        self.post_cd = max(0.0, self.post_cd - dt)
        self.call_t = max(0.0, self.call_t - dt)
        self._decay(dt)
        phase = self.phase
        if phase == "countdown":
            self._update_countdown(dt, inp)
        elif phase == "throw_in":
            self._update_throw_in(dt, inp)
        elif phase == "open":
            self._update_open(dt, inp)
        elif phase == "solo_window":
            self._update_solo_window(dt, inp)
        elif phase == "mark_choice":
            self._update_mark_choice(dt, inp)
        elif phase == "set_piece":
            self._update_set_piece(dt, inp)
        elif phase == "celebrate":
            self._update_celebrate(dt, inp)
        elif phase == "half_time":
            self._update_half_time(dt, inp)
        elif phase == "extra_prompt":
            self.phase_t += dt
            if self.auto_continue and self.phase_t > 0.2:
                self.decline_extra()
        elif phase == "full_time":
            self.phase_t += dt
        self._update_ref(dt)
        self._update_hint(inp)
        if self.phase in ("open", "throw_in", "set_piece", "solo_window", "mark_choice"):
            self._record(dt)
        self._stick_if_held()

    def debug_open(self):
        """Skip the throw-in. Used by the rule tests."""
        self.phase = "open"
        self.clock_running = True
        self.countdown = 0
        self.ball.resolved = False
        self._reset_positions()

    def request_extra(self):
        if self.phase != "extra_prompt":
            return
        self.extra_started = True
        self.period = 2
        self.half_length = EXTRA_HALF_MIN * 60.0
        self._next_period()

    def decline_extra(self):
        self.phase = "full_time"
        self.phase_t = 0
        self._say("FULL TIME", "hooter", sfx="whistle_long", time=6)

    def substitute(self, off_pid: int, on_pid: int) -> bool:
        off = self.player_by_pid(off_pid)
        on = self.player_by_pid(on_pid)
        if not off or not on or off.team != on.team:
            return False
        side = self.teams[off.team]
        if side.subs_used >= MAX_SUBS or off.sent_off or off.in_bin or not off.on_pitch or on.on_pitch:
            self._say("SUBSTITUTION NOT ALLOWED", "info", time=1.4)
            return False
        on.role = off.role
        on.on_pitch = True
        on.x, on.z, on.facing = off.x, off.z, off.facing
        on.stamina = min(1.0, off.stamina + 0.25)
        off.on_pitch = False
        off.role = "sub"
        if self.ball.holder is off:
            self._give(on)
        side.subs_used += 1
        if self.controlled == off.pid:
            self.controlled = on.pid
        self._say(f"SUB  {on.number} {on.surname}  FOR  {off.number} {off.surname}", "info", time=2.2)
        return True

    # ------------------------------------------------------------------
    # Phases
    # ------------------------------------------------------------------
    def _update_countdown(self, dt, inp):
        self.countdown -= dt
        p = self.controlled_player()
        if p and p.active and self.human_team == p.team:
            self._apply_human_move(p, dt, inp)
        if self.countdown <= 0:
            self._begin_throw(inp)

    def _begin_throw(self, inp):
        early = self._early_break()
        if early is not None:
            other = 1 - early
            self._say("BROKE THE 45 EARLY — FREE FROM HALFWAY", "foul", sfx="whistle", time=2.2)
            self.teams[early].fouls += 1
            self._place_set("free", other, self._nearest(other, HALF, CENTER_Z), HALF, CENTER_Z)
            return
        self.phase = "throw_in"
        self.throw_t = 0.0
        self.throw_jumps = {}
        self.ball.holder = None
        self.ball.x, self.ball.z = HALF, CENTER_Z
        self.ball.y = 1.05
        self.ball.vy = 7.4
        self.ball.vx = self.ball.vz = 0.0
        self.ball.in_flight = True
        self.ball.kick_type = "throw"
        self.ball.resolved = False
        self.ball.bounced = False
        self.sfx.append("whistle")
        self._say("1 V 1 THROW-IN", "info", time=1.4)
        # AI contestants commit to a jump time around the apex.
        apex = 0.72
        for pid in self.contestants:
            if pid is None:
                continue
            err = {"easy": 0.16, "medium": 0.08, "hard": 0.035}[self.difficulty]
            self.throw_jumps[pid] = apex + self.rng.uniform(-err, err)

    def _early_break(self):
        c0, c1 = self.contestants
        for p in self.players:
            if not p.active or p.pid in (c0, c1):
                continue
            gx = self.own_goal_x(p.team)
            depth = p.x if gx < 1 else PITCH_L - p.x
            if depth > 45.4:
                return p.team
        return None

    def _update_throw_in(self, dt, inp):
        self.throw_t += dt
        self._update_ball(dt)
        apex = 0.72
        human = self.controlled_player()
        if human and human.pid in self.contestants and (inp.jump or inp.kick_pressed or inp.mark):
            self.throw_jumps.setdefault(human.pid, self.throw_t)
            if abs(self.throw_t - apex) < 0.12:
                human.jump_t = 0.48
        for pid, when in self.throw_jumps.items():
            p = self.player_by_pid(pid)
            if p and abs(self.throw_t - when) < dt + 0.02:
                p.jump_t = 0.48
        if self.throw_t >= 0.62:
            winner = self._throw_winner()
            if winner is not None and self.throw_t >= max(0.66, self.throw_jumps.get(winner.pid, 0.7)):
                self._award_throw(winner)
                return
        if self.throw_t > 1.35 or self.ball.y <= BALL_R + 0.02 and self.throw_t > 0.9:
            self._award_throw(self._throw_winner())

    def _throw_winner(self):
        apex = 0.72
        best, bd = None, 1e9
        for pid in self.contestants:
            p = self.player_by_pid(pid)
            if not p:
                continue
            when = self.throw_jumps.get(pid)
            if when is None:
                err = 0.4
            else:
                err = abs(when - apex)
            # A little catch skill, so a mistimed jump can still be beaten.
            err -= p.attrs["catch"] * 0.05
            if err < bd:
                best, bd = p, err
        return best

    def _award_throw(self, winner):
        if winner is None:
            self.phase = "open"
            self.clock_running = True
            self.ball.in_flight = False
            return
        self._give(winner)
        self.possession_team = winner.team
        self.phase = "open"
        self.clock_running = True
        self.restart_grace = 2.0
        if self.human_team == winner.team and winner.role != "gk":
            self.controlled = winner.pid
        self._say(f"BREAK  {winner.short}", "info", time=1.3)
        self.sfx.append("cheer")

    def _update_open(self, dt, inp):
        self._tick_clock(dt)
        self.restart_grace = max(0.0, self.restart_grace - dt)
        self.foul_cd = max(0.0, self.foul_cd - dt)
        self._update_actors(dt, inp)
        if self.phase != "open":
            return
        self._update_ball(dt)
        if self.phase != "open":
            return
        self._boundaries()
        if self.phase != "open":
            return
        self._separate()
        self._contests()
        if self.phase != "open":
            return
        self._structure(dt)
        self._tick_mark_advantage(dt)
        self._hooter_dead_check()

    def _update_solo_window(self, dt, inp):
        self.solo_t -= dt
        p = self.ball.holder
        human = p is not None and self.human_team == p.team
        if human and p is not None:
            self._apply_human_move(p, dt, inp)
            if inp.solo and not self.solo_started:
                self._do_solo(p)
                self.solo_started = True
            if inp.kick_pressed or inp.kick_released:
                self._place_set("free", self.solo_team, p, self.solo_x, self.solo_z)
                self._say("FREE KICK", "info", time=1.2)
                return
        if p is not None and (self.solo_started or (not human and self.solo_t < 0.7)):
            sign = self.attack_sign(self.solo_team)
            gx = self.attack_goal_x(self.solo_team)
            if not self.solo_started and not human:
                self._do_solo(p)
                p.x += sign * 1.6
                self.solo_started = True
            ok, why = solo_and_go_ok(self.solo_x, self.solo_z, p.x, p.z, sign, gx)
            moved = dist(self.solo_x, self.solo_z, p.x, p.z)
            if why == "backwards":
                self._say("SOLO AND GO CANNOT TRAVEL BACK", "foul", sfx="whistle", time=1.8)
                self._place_set("free", self.solo_team, p, self.solo_x, self.solo_z)
                return
            if ok and moved > 0.7:
                p.protect = 0.45
                self.solo_guard = (self.solo_x, self.solo_z, self.solo_team)
                self.phase = "open"
                self.clock_running = not self.hooter_sounded
                self.restart_grace = 1.2
                self._say("SOLO AND GO", "info", sfx="solo", time=1.3)
                return
            if why == "too_far":
                self._say("SOLO AND GO — OUTSIDE 4 METRES", "foul", sfx="whistle", time=1.6)
                self._place_set("free", self.solo_team, p, self.solo_x, self.solo_z)
                return
        if self.solo_t <= 0:
            taker = p or self._nearest(self.solo_team, self.solo_x, self.solo_z)
            self._place_set("free", self.solo_team, taker, self.solo_x, self.solo_z)
            self._say("FREE KICK", "info", time=1.2)

    def _update_mark_choice(self, dt, inp):
        self.mark_t -= dt
        p = self.player_by_pid(self.mark_pid)
        if p is None:
            self.phase = "open"
            return
        human = self.human_team == p.team
        if human:
            self._apply_human_move(p, dt, inp)
            # Movement during the choice doesn't count as play-on until they commit.
            p.x, p.z = self.mark_x, self.mark_z
            if inp.mark or inp.confirm:
                self._begin_mark_free(p)
                return
            if inp.kick_pressed or inp.hand or inp.fist or inp.solo or inp.hook:
                self._play_on_from_mark(p)
                return
        if self.mark_t <= 0 or not human:
            d = dist_to_goal(p.x, p.z, self.attack_goal_x(p.team))
            if human or d < 52:
                self._begin_mark_free(p)
            else:
                self._play_on_from_mark(p)

    def _update_set_piece(self, dt, inp):
        self.set_timer += dt
        taker = self.player_by_pid(self.taker)
        if taker is None or not taker.active:
            taker = self._nearest(self.set_team or 0, self.set_x, self.set_z)
            self.taker = taker.pid
        self._move_support(dt, taker)
        human = taker.team == self.human_team
        if human:
            if self.controlled != taker.pid:
                self.saved_control = self.saved_control if self.saved_control is not None else self.controlled
                self.controlled = taker.pid
            self._move_taker(taker, dt, inp)
            if inp.to_arc and self.free_can_arc:
                self._move_taker_to_arc(taker)
            ready = self.set_timer > 0.22
            if ready and (inp.kick_released or inp.kick_pressed or inp.hand or inp.fist):
                self._take_set(taker, inp)
                return
            if self.set_timer > 14.0:
                self._take_set(taker, inp)
        else:
            delay = 0.65 if self.difficulty == "hard" else 1.05
            if self.auto_continue:
                delay = 0.25
            if self.set_timer > delay:
                self._take_set(taker, inp)

    def _update_celebrate(self, dt, inp):
        self.celebrate_t -= dt
        if self.celebrate_t > 0 and not (inp.confirm and self.celebrate_t < 1.2):
            return
        if self.after_celebrate == "end" or (self.hooter_sounded and self.after_celebrate != "kickout"):
            # A score on the hooter ends the half. A wide already set after_celebrate.
            if self.hooter_sounded and self.after_celebrate == "end":
                self._end_period()
                return
        if self.after_celebrate == "kickout":
            self._begin_kickout(self.kickout_team)
            return
        if self.after_celebrate == "end":
            self._end_period()
            return
        self.phase = "open"
        self.clock_running = not self.hooter_sounded

    def _update_half_time(self, dt, inp):
        self.phase_t += dt
        if inp.confirm or (self.auto_continue and self.phase_t > 0.25):
            self._next_period()

    # ------------------------------------------------------------------
    # Actors
    # ------------------------------------------------------------------
    def _update_actors(self, dt, inp):
        call = None
        human = self.controlled_player()
        if human and human.active and human.team == self.human_team:
            self._control_human(human, dt, inp)
            if self.call_t > 0:
                call = human
        for p in self.players:
            if p.has_ball:
                p.carry_t += dt
            else:
                p.carry_t = 0.0
            if not p.active or p is human and p.team == self.human_team:
                continue
            self._control_ai(p, dt, call)
            if p.has_ball and p.carry_t > 2.6 and p.action_cd <= 0 and self.phase == "open":
                self._force_release(p)
        for p in self.players:
            if p.active and p.has_ball:
                self._enforce_steps(p)
                if self.phase != "open":
                    return
        self._clamp_all()

    def _control_human(self, p, dt, inp):
        self._apply_human_move(p, dt, inp)
        if inp.switch and not p.has_ball:
            self._switch()
        if inp.block:
            p.blocking = 0.32
        if inp.sidestep:
            self._sidestep(p)
        if p.has_ball:
            if inp.bounce:
                self._try_bounce(p)
            if inp.solo:
                self._do_solo(p, skill=True)
            if inp.kick_held:
                self.charge = min(1.0, self.charge + dt / 0.52)
            if inp.hand:
                self._human_pass(p, "hand", inp)
                self.charge = 0
            elif inp.fist:
                self._human_pass(p, "fist", inp)
                self.charge = 0
            elif inp.hook:
                self._human_kick(p, inp, max(0.55, self.charge), forced="hook")
                self.charge = 0
            elif inp.kick_released:
                power = self.charge if self.charge > 0.12 else 0.5
                self.charge = 0
                self._human_kick(p, inp, power)
        else:
            self.charge = 0
            if inp.tackle:
                self._try_tackle(p)
            if inp.hand:
                self.call_t = 1.4
                self.call_pid = p.pid
                self._say("CALLING FOR IT", "info", time=0.7)

    def _control_ai(self, p, dt, call):
        if p.has_ball and self.phase == "open" and p.action_cd <= 0:
            gx = self.attack_goal_x(p.team)
            dgoal = dist_to_goal(p.x, p.z, gx)
            if dgoal < 24 and abs(p.z - CENTER_Z) < 12 and p.role != "gk":
                sign = self.attack_sign(p.team)
                goal_try = dgoal < 22
                ty = 0.9 if goal_try else 3.55
                # Aim inside a post so a goal is a real finish, not always at the keeper's chest.
                tz = CENTER_Z + self.rng.choice((-1.6, -0.6, 0.7, 1.7))
                self._strike(p, "punt", gx + sign * 2.8, tz, ty, 0.88, None)
                self.teams[p.team].shots += 1
                p.carry_t = 0.0
                p.action_cd = 0.45
                return
        if p.think <= 0 or p.order is None:
            p.order = ai.decide(self, p)
            p.think = 0.14 + (p.pid % 5) * 0.015
        order = p.order or {}
        if call and p.has_ball and p.team == call.team and p.action_cd <= 0:
            d = dist(p.x, p.z, call.x, call.z)
            if 5 < d < 32 and self._lane_ok(p, call.x, call.z):
                kind = "hand" if d < 16 else "punt"
                self._strike(p, kind, call.x, call.z, 1.35 if d < 16 else 1.7, 0.58, None)
                self.call_t = 0
                p.action_cd = 0.5
                return
        self._move_toward(p, order.get("tx", p.x), order.get("tz", p.z), dt, order.get("sprint", False))
        action = order.get("action")
        if action and p.action_cd <= 0 and self.phase == "open":
            self._exec_ai_action(p, order)
            order["action"] = None
            p.action_cd = 0.42

    def _force_release(self, p):
        """Stop an AI carrier soloing into a dead end with the ball."""
        gx = self.attack_goal_x(p.team)
        sign = self.attack_sign(p.team)
        dgoal = dist_to_goal(p.x, p.z, gx)
        p.carry_t = 0.0
        p.action_cd = 0.55
        if dgoal < 26 and abs(p.z - CENTER_Z) < 18:
            ty = 0.95 if dgoal < 15 else 3.55
            self._strike(p, "punt", gx + sign * 2.4, CENTER_Z + self.rng.uniform(-0.8, 0.8), ty, 0.8, None)
            self.teams[p.team].shots += 1
            return
        best, bd = None, 1e9
        for m in self.players:
            if m.team == p.team and m.active and m is not p and (m.x - p.x) * sign > 6:
                dd = dist(p.x, p.z, m.x, m.z)
                if 8 < dd < 40 and dd < bd:
                    best, bd = m, dd
        if best is not None:
            kind = "hand" if bd < 15 else "punt"
            self._strike(p, kind, best.x + sign * 1.5, best.z, 1.45 if bd < 15 else 1.8, 0.62, None)
            return
        self._strike(p, "punt", p.x + sign * 26, CENTER_Z, 1.8, 0.64, None)

    def _exec_ai_action(self, p, order):
        action = order.get("action")
        aim = order.get("aim") or (p.x + self.attack_sign(p.team) * 10, p.z)
        ay = order.get("aim_y", 1.4)
        power = order.get("power", 0.6)
        if action == "solo" and p.has_ball:
            self._do_solo(p)
        elif action == "bounce" and p.has_ball:
            self._try_bounce(p)
        elif action == "sidestep":
            self._sidestep(p)
        elif action in ("kick", "hook", "hand", "fist") and p.has_ball:
            kind = {"kick": "punt", "hook": "hook", "hand": "hand", "fist": "fist"}[action]
            self._strike(p, kind, aim[0], aim[1], ay, power, None)
            p.carry_t = 0.0
            if kind == "punt" and ay > 2.2:
                self.teams[p.team].shots += 1
        elif action == "tackle":
            self._try_tackle(p)
        elif action == "block":
            p.blocking = 0.35
        elif action == "jump":
            p.jump_t = 0.48

    def _move_toward(self, p, tx, tz, dt, sprint):
        dx, dz = tx - p.x, tz - p.z
        d = math.hypot(dx, dz)
        if d < 0.12:
            p.vx *= 0.4
            p.vz *= 0.4
            return
        speed = self._speed(p, sprint and d > 1.4)
        dirx, dirz = dx / d, dz / d
        step = min(d, speed * dt)
        ox, oz = p.x, p.z
        p.x += dirx * step
        p.z += dirz * step
        p.vx, p.vz = dirx * speed, dirz * speed
        p.facing = math.atan2(dirz, dirx)
        if sprint and d > 1.5:
            p.stamina = max(0.22, p.stamina - dt * 0.07)
        self._note_steps(p, ox, oz)

    def _apply_human_move(self, p, dt, inp):
        mx, mz = inp.move_x, inp.move_z
        mag = math.hypot(mx, mz)
        if mag > 1:
            mx, mz = mx / mag, mz / mag
        ox, oz = p.x, p.z
        if mag > 0.08:
            speed = self._speed(p, inp.sprint)
            p.vx, p.vz = mx * speed, mz * speed
            p.x += p.vx * dt
            p.z += p.vz * dt
            p.facing = math.atan2(mz, mx)
            if inp.sprint:
                p.stamina = max(0.22, p.stamina - dt * 0.085)
        else:
            p.vx = p.vz = 0.0
            if p.has_ball and inp.aim is not None:
                p.facing = math.atan2(inp.aim[1] - p.z, inp.aim[0] - p.x)
        self._note_steps(p, ox, oz)

    def _speed(self, p, sprint: bool) -> float:
        base = 5.15 + p.pace * 3.35
        if sprint:
            base += 1.35
        base *= 0.70 + 0.30 * p.stamina
        if p.has_ball:
            base *= 0.94
        if p.stumble_t > 0:
            base *= 0.5
        if not (p.team == self.human_team and p.pid == self.controlled):
            base *= {"easy": 0.84, "medium": 1.0, "hard": 1.06}[self.difficulty]
        else:
            base *= 1.04
        return base

    def _note_steps(self, p, ox, oz):
        if not p.has_ball or self.phase not in ("open", "solo_window"):
            return
        moved = math.hypot(p.x - ox, p.z - oz)
        if moved > 0.004:
            p.steps += moved / STEP_M

    def _enforce_steps(self, p):
        if not p.has_ball or self.phase != "open":
            return
        if p.steps < 4.0:
            return
        if p.solo_lock > 0.04 and p.steps >= 4.85:
            self._technical(p, "overcarry")
            return
        if p.solo_lock <= 0:
            self._do_solo(p, auto=True)

    def _clamp_all(self):
        for p in self.players:
            if p.active:
                self._clamp_player(p)

    def _clamp_player(self, p):
        p.x = clamp(p.x, 0.7, PITCH_L - 0.7)
        p.z = clamp(p.z, 0.7, PITCH_W - 0.7)
        if p.role == "gk":
            gx = self.own_goal_x(p.team)
            sign = self.attack_sign(p.team)
            hunting = self.ball.y > 1.1 and dist(p.x, p.z, self.ball.x, self.ball.z) < 7 and abs(self.ball.x - gx) < 18
            if not hunting:
                if sign > 0:
                    p.x = min(max(p.x, gx + 0.6), gx + 18)
                else:
                    p.x = max(min(p.x, gx - 0.6), gx - 18)
        if self.phase == "open":
            self._clamp_structure(p)

    def _clamp_structure(self, p):
        if p.pid == self.controlled and p.team == self.human_team:
            return
        sign = self.attack_sign(p.team)
        if p.role in OWN_HALF_ROLES:
            if sign > 0:
                p.x = min(p.x, HALF - 0.7)
            else:
                p.x = max(p.x, HALF + 0.7)
        if p.role in ATTACK_HALF_ROLES:
            if sign > 0:
                p.x = max(p.x, HALF + 0.7)
            else:
                p.x = min(p.x, HALF - 0.7)

    def _separate(self):
        active = [p for p in self.players if p.active]
        for i, a in enumerate(active):
            for b in active[i + 1 :]:
                dx, dz = b.x - a.x, b.z - a.z
                d = math.hypot(dx, dz) or 0.0001
                if d < 0.82:
                    push = (0.82 - d) * 0.5
                    a.x -= dx / d * push
                    a.z -= dz / d * push
                    b.x += dx / d * push
                    b.z += dz / d * push
                    self._shoulder(a, b, d)

    def _shoulder(self, a, b, d):
        if d > 0.7 or self.phase != "open":
            return
        if a.y > 0.35 or b.y > 0.35:
            return
        carrier = a if a.has_ball else b if b.has_ball else None
        if carrier is None or a.team == b.team:
            return
        other = b if carrier is a else a
        if self._is_behind(other, carrier):
            return
        if math.hypot(a.vx, a.vz) + math.hypot(b.vx, b.vz) < 3.5:
            return
        if other.action_cd > 0:
            return
        other.stumble_t = 0.28
        other.action_cd = 0.6
        if self.rng.random() < 0.35:
            self.sfx.append("shoulder")

    # ------------------------------------------------------------------
    # Ball skills
    # ------------------------------------------------------------------
    def _give(self, p):
        if self.ball.holder and self.ball.holder is not p:
            self.ball.holder.has_ball = False
        self.ball.holder = p
        p.has_ball = True
        p.steps = 0.0
        p.bounce_used = False
        self.ball.in_flight = False
        self.ball.vx = self.ball.vy = self.ball.vz = 0.0
        self.ball.last_team = p.team
        self.ball.last_pid = p.pid
        self.possession_team = p.team
        self._stick(p)

    def _drop_ball(self):
        if self.ball.holder:
            self.ball.holder.has_ball = False
            self.ball.holder = None
        self.ball.in_flight = False
        self.ball.vx = self.ball.vy = self.ball.vz = 0.0

    def _stick(self, p):
        self.ball.x = p.x + math.cos(p.facing) * 0.36
        self.ball.z = p.z + math.sin(p.facing) * 0.36
        self.ball.y = 1.12 + p.y
        if 0.08 < p.solo_t < 0.22:
            self.ball.y = 0.26 + p.y
        if 0.06 < p.bounce_t < 0.2:
            self.ball.y = 0.12
        self.ball.vx = p.vx
        self.ball.vz = p.vz

    def _stick_if_held(self):
        if self.ball.holder and self.ball.holder.has_ball:
            self._stick(self.ball.holder)

    def _do_solo(self, p, auto=False, skill=False):
        if not p.has_ball:
            return
        p.steps = 0.0
        p.bounce_used = False
        p.solo_t = 0.30
        p.solo_lock = 0.24
        if skill:
            p.protect = max(p.protect, 0.30)
        self.teams[p.team].solos += 1
        if auto and p.pid == self.controlled:
            self._say("SOLO", "info", time=0.6)
        self.sfx.append("solo")

    def _try_bounce(self, p):
        if not p.has_ball or self.phase not in ("open", "solo_window"):
            return
        if p.bounce_used:
            self._technical(p, "double_bounce")
            return
        p.bounce_used = True
        p.steps = 0.0
        p.bounce_t = 0.32
        p.solo_lock = 0.2
        self.sfx.append("bounce")

    def _sidestep(self, p):
        if p.action_cd > 0:
            return
        ang = p.facing + (1.0 if (p.pid + int(self.real_time * 10)) % 2 == 0 else -1.0)
        p.x += math.cos(ang) * 1.15
        p.z += math.sin(ang) * 1.15
        p.facing = ang
        p.protect = max(p.protect, 0.26)
        p.action_cd = 0.9
        self.sfx.append("solo")

    def _human_pass(self, p, kind, inp):
        ax, az, mate = self._aim_point(p, inp)
        if mate is not None and not self.gk_pass_would_be_legal(p, mate):
            self._say("CANNOT HAND-PASS TO THE KEEPER THERE", "foul", time=1.3)
        ty = 1.25 if kind == "hand" else 1.35
        if mate is not None:
            ax, az = mate.x + mate.vx * 0.15, mate.z + mate.vz * 0.15
        self._strike(p, kind, ax, az, ty, 0.55, None)

    def _human_kick(self, p, inp, power, forced=None):
        gx = self.attack_goal_x(p.team)
        sign = self.attack_sign(p.team)
        ax, az, mate = self._aim_point(p, inp)
        z_at = self._z_on_line(p.x, p.z, ax, az, gx)
        toward = (ax - p.x) * sign > 2.0
        at_posts = z_at is not None and abs(z_at - CENTER_Z) < 11
        dgoal = dist_to_goal(p.x, p.z, gx)
        kind = forced or "punt"
        ty = 1.6
        tx, tz = ax, az
        if kind == "punt" and toward and at_posts and dgoal < 58 and mate is None:
            if inp.aim_high is True or (inp.aim_high is None and dgoal >= 16):
                kind = "punt"
                tz = clamp(z_at if z_at is not None else CENTER_Z, CENTER_Z - 2.6, CENTER_Z + 2.6)
                tx = gx + sign * 2.4
                ty = 3.85
                self.teams[p.team].shots += 1
            elif dgoal < 22:
                tz = clamp(z_at if z_at is not None else CENTER_Z, CENTER_Z - 2.2, CENTER_Z + 2.2)
                tx = gx + sign * 2.4
                ty = 0.85 + (1.0 - power) * 0.45
                self.teams[p.team].shots += 1
        elif kind == "punt" and mate is not None and (not at_posts or dgoal > 24):
            tx = mate.x + mate.vx * 0.25
            tz = mate.z + mate.vz * 0.25
            ty = 1.7
        elif kind == "hook":
            ty = 1.8
        self._strike(p, kind, tx, tz, ty, power, None)

    def _aim_point(self, p, inp):
        if inp.aim is not None:
            ax, az = inp.aim
        else:
            ax = p.x + math.cos(p.facing) * 18
            az = p.z + math.sin(p.facing) * 18
        mate = self._lock_mate(p, ax, az)
        self.lock_pid = mate.pid if mate else None
        return ax, az, mate

    def _lock_mate(self, p, ax, az):
        aim_ang = math.atan2(az - p.z, ax - p.x)
        best, bang = None, 0.22
        for m in self.players:
            if m.team != p.team or not m.active or m is p:
                continue
            d = dist(p.x, p.z, m.x, m.z)
            if d < 4 or d > 42:
                continue
            ang = math.atan2(m.z - p.z, m.x - p.x)
            diff = abs((aim_ang - ang + math.pi) % (2 * math.pi) - math.pi)
            if diff < bang:
                best, bang = m, diff
        return best

    def _z_on_line(self, x, z, ax, az, line_x):
        if abs(ax - x) < 0.05:
            return None
        t = (line_x - x) / (ax - x)
        if t < 0:
            return None
        return z + t * (az - z)

    def _strike(self, p, kick_type, tx, tz, ty, power, set_kind):
        if not p.has_ball:
            return
        power = clamp(power, 0.22, 1.0)
        opp, od = self._nearest_opp(p)
        pressure = max(0.0, 2.1 - od) * 0.55 if opp else 0.0
        err = (1.0 - p.kick) * 1.15 + pressure * 0.35
        if p.team == self.human_team and p.pid == self.controlled:
            err *= {"easy": 0.35, "medium": 0.62, "hard": 0.9}[self.difficulty]
        tz += self.rng.uniform(-err, err)
        ty += self.rng.uniform(-err * 0.12, err * 0.12)
        d = math.hypot(tx - p.x, tz - p.z)
        if kick_type in ("hand", "fist"):
            flight = clamp(d / (10.5 + power * 5.0), 0.22, 1.15)
            ty = clamp(ty, 0.8, 1.75)
        else:
            flight = clamp(d / (11.5 + power * 14.5), 0.26, 2.7)
        vx, vy, vz = ballistics(p.x, 1.05, p.z, tx, ty, tz, flight)
        sp = math.hypot(vx, vz)
        cap = 30.0 if kick_type not in ("hand", "fist") else 18.0
        if sp > cap:
            vx *= cap / sp
            vz *= cap / sp
        blocker = self._blocker(p)
        if blocker is not None and kick_type not in ("hand", "fist"):
            vx, vz = -vx * 0.25 + self.rng.uniform(-2, 2), self.rng.uniform(-4, 4)
            vy = 1.4
            self._say(f"BLOCK DOWN  {blocker.short}", "info", sfx="block", time=1.3)
            blocker.blocking = 0
        self._release(p, vx, vy, vz, kick_type, set_kind)
        if kick_type == "hook":
            self.ball.curve = (4.5 + power * 3.5) * (1 if p.pid % 2 == 0 else -1)
            self.ball.curve_t = 0.75
        p.kick_t = 0.32
        p.facing = math.atan2(tz - p.z, tx - p.x)
        self.sfx.append("hand" if kick_type in ("hand", "fist") else "kick")
        if kick_type in ("punt", "hook", "penalty", "45", "sideline") and ty > 2.4:
            self.teams[p.team].shots += 0  # counted by the caller when it is a shot

    def _release(self, p, vx, vy, vz, kick_type, set_kind):
        p.has_ball = False
        self.ball.holder = None
        self.ball.x = p.x + math.cos(p.facing) * 0.42
        self.ball.z = p.z + math.sin(p.facing) * 0.42
        self.ball.y = 1.05
        self.ball.vx, self.ball.vy, self.ball.vz = vx, vy, vz
        self.ball.px, self.ball.py, self.ball.pz = self.ball.x, self.ball.y, self.ball.z
        self.ball.in_flight = True
        self.ball.kick_type = kick_type
        self.ball.kick_origin = (p.x, p.z)
        self.ball.kicker_pid = p.pid
        self.ball.kicker_team = p.team
        gx = self.attack_goal_x(p.team)
        self.ball.kicker_dist = dist_to_goal(p.x, p.z, gx)
        self.ball.two_point = two_point_strike(kick_type, self.ball.kicker_dist, set_kind)
        self.ball.teammate_touched = False
        self.ball.bounced = False
        self.ball.set_kind = set_kind
        self.ball.from_mark = set_kind == "mark"
        self.ball.square_at_kick = self._square_occupied(p.team, p.pid)
        self.ball.last_team = p.team
        self.ball.last_pid = p.pid
        self.ball.resolved = False
        self.ball.curve_t = 0.0
        self.ball.kickout_goal = self.own_goal_x(p.team) if kick_type == "kickout" else None
        self.ball.hooter_flight = self.hooter_sounded
        self.ball.attacker_touch_after_hooter = False
        self.ball.released_at = self.real_time
        self.possession_team = p.team

    def _square_occupied(self, team, ignore_pid) -> bool:
        gx = self.attack_goal_x(team)
        for p in self.players:
            if p.team == team and p.active and p.pid != ignore_pid and in_small_square(p.x, p.z, gx):
                return True
        return False

    def _blocker(self, kicker):
        fx, fz = math.cos(kicker.facing), math.sin(kicker.facing)
        for p in self.players:
            if p.team == kicker.team or not p.active or p.blocking <= 0:
                continue
            dx, dz = p.x - kicker.x, p.z - kicker.z
            if math.hypot(dx, dz) < 2.15 and dx * fx + dz * fz > 0.2:
                return p
        return None

    def _update_ball(self, dt):
        b = self.ball
        b.px, b.py, b.pz = b.x, b.y, b.z
        if b.holder:
            self._stick(b.holder)
            return
        b.vy -= GRAVITY * dt
        if b.curve_t > 0:
            b.curve_t -= dt
            sp = math.hypot(b.vx, b.vz) or 1.0
            b.vx += (-b.vz / sp) * b.curve * dt
            b.vz += (b.vx / sp) * b.curve * dt
        b.x += b.vx * dt
        b.y += b.vy * dt
        b.z += b.vz * dt
        damp = math.exp(-0.04 * dt)
        b.vx *= damp
        b.vz *= damp
        b.spin += math.hypot(b.vx, b.vz) * dt * 0.4
        if b.y <= BALL_R:
            b.y = BALL_R
            if b.vy < -1.25:
                b.vy = -b.vy * 0.55
                b.vx *= 0.84
                b.vz *= 0.84
                b.bounced = True
                self.sfx.append("bounce")
            else:
                b.vy = 0.0
                fr = math.exp(-2.6 * dt)
                b.vx *= fr
                b.vz *= fr
                if math.hypot(b.vx, b.vz) < 0.3:
                    b.vx = b.vz = 0.0
                    b.in_flight = False
        else:
            b.in_flight = True
        self._posts()

    def _posts(self):
        if self.post_cd > 0 or self.ball.holder:
            return
        b = self.ball
        for gx, side in ((0.0, 1.0), (PITCH_L, -1.0)):
            for pz in (CENTER_Z - 3.25, CENTER_Z + 3.25):
                if abs(b.x - gx) < 0.3 and abs(b.z - pz) < 0.3 and 0.0 <= b.y <= 8.0:
                    b.vx = side * abs(b.vx) * 0.45 + side * 2.0
                    b.vz += (b.z - pz) * 6.0
                    b.x = gx + side * 0.4
                    b.vy += 1.4
                    self.post_cd = 0.35
                    self.sfx.append("post")
                    self._say("OFF THE POST", "info", time=1.1)
                    return
            if abs(b.x - gx) < 0.3 and abs(b.y - CROSSBAR) < 0.16 and abs(b.z - CENTER_Z) < 3.2:
                b.vy = abs(b.vy) * 0.35 + 1.5
                b.vx = side * abs(b.vx) * 0.4 + side * 1.5
                b.x = gx + side * 0.4
                self.post_cd = 0.35
                self.sfx.append("post")
                self._say("OFF THE CROSSBAR", "info", time=1.1)
                return

    def _boundaries(self):
        b = self.ball
        if b.resolved or b.holder:
            return
        for gx in (0.0, PITCH_L):
            if (b.px - gx) * (b.x - gx) < 0.0:
                denom = (b.x - b.px) or 1e-6
                t = clamp((gx - b.px) / denom, 0.0, 1.0)
                y = b.py + t * (b.y - b.py)
                z = b.pz + t * (b.z - b.pz)
                if -1.0 <= z <= PITCH_W + 1.0:
                    self._resolve_endline(gx, y, z)
                    return
        if b.z < 0.0 or b.z > PITCH_W:
            self._sideline()
            return
        if b.x < -1.5 or b.x > PITCH_L + 1.5:
            gx = 0.0 if b.x < 0 else PITCH_L
            self._resolve_endline(gx, b.y, clamp(b.z, 0.0, PITCH_W))

    def _resolve_endline(self, gx, y, z):
        b = self.ball
        b.resolved = True
        scoring = self._team_attacking(gx)
        conceding = 1 - scoring
        kicker_dist = b.kicker_dist
        if b.kick_origin and b.kicker_team is not None and self.attack_goal_x(b.kicker_team) != gx:
            kicker_dist = dist_to_goal(b.kick_origin[0], b.kick_origin[1], gx)
        square = bool(b.square_at_kick and b.kicker_team == scoring)
        result, value = classify_crossing(
            y, z, b.kick_type or "punt", kicker_dist, b.teammate_touched, b.set_kind, square
        )
        if self.hooter_sounded and b.hooter_flight and b.attacker_touch_after_hooter and result in ("goal", "point"):
            result = "dead"
        if result in ("post", "crossbar"):
            b.resolved = False
            side = 1.0 if gx < 1 else -1.0
            b.x = gx + side * 0.45
            b.y = max(BALL_R, y)
            b.z = clamp(z, 2.0, PITCH_W - 2.0)
            b.vx = side * 4.0
            b.vy = 2.0
            self.sfx.append("post")
            self._say("OFF THE POST" if result == "post" else "OFF THE CROSSBAR", "info", time=1.1)
            return
        if result == "square":
            self._square_ball(conceding, gx)
            return
        if result == "goal":
            if self._keeper_save(gx, y, z):
                self._save_ball(gx, y, z)
                return
            self._score(scoring, "goal", 3)
            return
        if result == "point":
            self._score(scoring, "point", value)
            return
        last = b.last_team
        if last == conceding and result != "dead":
            if self.hooter_sounded:
                self._end_period()
                return
            self._award_45(scoring, z, gx)
            return
        if last == scoring:
            self.teams[scoring].wides += 1
        if self.hooter_sounded:
            self._say("DEAD BALL — HALF OVER", "wide", time=1.4)
            self._end_period()
            return
        self._say("WIDE", "wide", sfx="groan", time=1.2)
        self.kickout_team = conceding
        self.phase = "celebrate"
        self.celebrate_t = 0.8
        self.after_celebrate = "kickout"
        self.clock_running = False
        self._drop_ball()

    def _keeper_save(self, gx, y, z) -> bool:
        defending = 1 - self._team_attacking(gx)
        gk = self._by_role(defending, "gk")
        if gk is None or not gk.active:
            return False
        if abs(gk.x - gx) > 4.0:
            return False
        z_off = abs(z - gk.z)
        reach = 1.05 + gk.attrs["catch"] * 1.15
        if z_off > reach or y > 1.85:
            return False
        chance = 0.34 + gk.attrs["catch"] * 0.22 - z_off * 0.14
        if defending != self.human_team:
            chance *= {"easy": 0.45, "medium": 0.85, "hard": 1.05}[self.difficulty]
        return self.rng.random() < chance

    def _save_ball(self, gx, y, z):
        b = self.ball
        side = 1.0 if gx < 1.0 else -1.0
        b.resolved = False
        b.x = gx + side * 1.4
        b.y = max(0.5, min(y, 1.6))
        b.z = clamp(z, CENTER_Z - 3.0, CENTER_Z + 3.0)
        b.vx = side * 5.5
        b.vy = 1.6
        b.vz = self.rng.uniform(-2.2, 2.2)
        b.in_flight = True
        b.bounced = True
        gk = self._by_role(1 - self._team_attacking(gx), "gk")
        if gk:
            gk.dive = 1.0 if z > gk.z else -1.0
            gk.kick_t = 0.2
        self.sfx.append("save")
        self._say("SAVE", "save", time=1.1)

    def _sideline(self):
        self.ball.resolved = True
        if self.hooter_sounded:
            self._end_period()
            return
        last = self.ball.last_team
        award = 0 if last is None else 1 - last
        z = 1.1 if self.ball.z < 1 else PITCH_W - 1.1
        x = clamp(self.ball.px, 5.0, PITCH_L - 5.0)
        self._say("SIDELINE BALL", "info", sfx="whistle", time=1.2)
        self._place_set("sideline", award, self._nearest(award, x, z), x, z)

    def _contests(self):
        b = self.ball
        if b.holder or b.resolved or self.phase != "open":
            return
        self._maybe_jump()
        cands = []
        for p in self.players:
            if not p.active:
                continue
            rad = 1.12 + (0.4 if p.role == "gk" else 0.0) + (0.22 if p.jump_t > 0 else 0.0)
            if p.pid == self.controlled and p.team == self.human_team:
                rad += 0.18
            # The kicker cannot reclaim their own strike until it has left the hand.
            if p.pid == b.kicker_pid and self.real_time - getattr(b, "released_at", -10) < 0.45:
                if dist(p.x, p.z, b.kick_origin[0], b.kick_origin[1]) < 3.2:
                    continue
            d = self._dist_seg(p.x, p.z, b.px, b.pz, b.x, b.z)
            height_ok = b.y < 0.6 or abs(b.y - (1.05 + p.y)) < 1.2
            if d <= rad and height_ok and b.y < 3.05:
                cands.append(p)
        if not cands:
            return
        winner = max(cands, key=self._claim)
        if self._claim(winner) > 0.05:
            self._on_catch(winner)

    def _maybe_jump(self):
        b = self.ball
        if b.y < 1.45:
            return
        for p in self.players:
            if not p.active or p.jump_t > 0:
                continue
            if dist(p.x, p.z, b.x, b.z) < 2.4 and abs(b.y - 1.6) < 1.6:
                if p.role == "gk" or p.attrs["catch"] > 0.5:
                    p.jump_t = 0.48

    def _claim(self, p) -> float:
        d = dist(p.x, p.z, self.ball.x, self.ball.z)
        score = p.attrs["catch"] * 1.25 - d * 0.55
        if p.jump_t > 0:
            score += 0.4
        if p.role == "gk" and in_large_rectangle(p.x, p.z, self.own_goal_x(p.team)):
            score += 0.5
        if p.pid == self.controlled and p.team == self.human_team:
            score += 0.22
        return score

    def _on_catch(self, p):
        b = self.ball
        if b.kick_type == "kickout" and p.team == b.kicker_team and b.kickout_goal is not None:
            if not on_or_outside_arc(p.x, p.z, b.kickout_goal):
                self._short_kickout(p)
                return
            self.teams[p.team].kickouts_won += 1
        if p.role == "gk" and b.kicker_team == p.team and b.kicker_pid not in (None, p.pid):
            kicker = self.player_by_pid(b.kicker_pid)
            if kicker and not self.gk_pass_would_be_legal(kicker, p):
                self._gk_foul(p)
                return
        if self.hooter_sounded and b.hooter_flight:
            if p.team == b.kicker_team:
                b.attacker_touch_after_hooter = True
            self._end_period()
            return
        if b.in_flight and b.kicker_team == p.team and b.kicker_pid not in (None, p.pid):
            b.teammate_touched = True
        self._give(p)
        if self.human_team == p.team and self.autoswitch and p.role != "gk":
            self.controlled = p.pid
        mt = mark_type(
            b.kick_type or "",
            b.kick_origin[0],
            p.x,
            self.attack_goal_x(p.team),
            b.bounced,
            b.kickout_goal,
            b.set_kind,
            b.from_mark,
        )
        if mt and b.kick_type != "throw":
            self._offer_mark(p, mt)
            return
        self.restart_grace = max(self.restart_grace, 0.6)

    def _dist_seg(self, px, pz, x1, z1, x2, z2) -> float:
        dx, dz = x2 - x1, z2 - z1
        l2 = dx * dx + dz * dz
        if l2 < 1e-6:
            return dist(px, pz, x2, z2)
        t = clamp(((px - x1) * dx + (pz - z1) * dz) / l2, 0.0, 1.0)
        return dist(px, pz, x1 + t * dx, z1 + t * dz)

    # ------------------------------------------------------------------
    # Fouls, cards, restarts
    # ------------------------------------------------------------------
    def _technical(self, p, kind):
        if self.foul_cd > 0 or self.phase not in ("open", "solo_window"):
            return
        self.foul_cd = 0.5
        self.teams[p.team].fouls += 1
        name = "OVERCARRYING" if kind == "overcarry" else "DOUBLE BOUNCE"
        self._say(name, "foul", sfx="whistle", time=1.6)
        spot = (p.x, p.z)
        self._drop_ball()
        self._place_set("free", 1 - p.team, self._nearest(1 - p.team, spot[0], spot[1]), spot[0], spot[1])

    def _try_tackle(self, defender):
        carrier = self.ball.holder
        if carrier is None or carrier.team == defender.team or self.phase != "open":
            return
        if defender.action_cd > 0:
            return
        d = dist(defender.x, defender.z, carrier.x, carrier.z)
        if d > 1.7:
            return
        defender.action_cd = 0.55
        guard = getattr(self, "solo_guard", None)
        if carrier.protect > 0 and guard and dist(defender.x, defender.z, guard[0], guard[1]) < 4.2:
            self._fifty(defender.team, (carrier.x, carrier.z), "CHALLENGE ON THE SOLO AND GO — 50 METRES")
            return
        if self._is_behind(defender, carrier):
            self._personal_foul(defender, carrier, "pull")
            return
        if defender.y > 0.42:
            self._personal_foul(defender, carrier, "charge")
            return
        chance = 0.30 + defender.attrs["tackle"] * 0.42 - carrier.pace * 0.12
        if defender.team != self.human_team:
            chance *= {"easy": 0.62, "medium": 1.0, "hard": 1.18}[self.difficulty]
        else:
            chance += 0.08
        if self.rng.random() < chance:
            self._dispossess(defender, carrier)
        else:
            defender.stumble_t = 0.22

    def _is_behind(self, defender, carrier) -> bool:
        fx, fz = math.cos(carrier.facing), math.sin(carrier.facing)
        rx, rz = defender.x - carrier.x, defender.z - carrier.z
        return rx * fx + rz * fz < -0.42

    def _dispossess(self, defender, carrier):
        carrier.has_ball = False
        self.ball.holder = None
        self.ball.in_flight = True
        ang = math.atan2(defender.z - carrier.z, defender.x - carrier.x)
        self.ball.vx = math.cos(ang) * 3.5
        self.ball.vz = math.sin(ang) * 3.5
        self.ball.vy = 0.8
        self.ball.y = 1.0
        self.ball.last_team = defender.team
        self.ball.last_pid = defender.pid
        self.ball.kick_type = "tackle"
        self.ball.bounced = True
        self.ball.resolved = False
        self.possession_team = defender.team
        self.teams[defender.team].tackles += 1
        carrier.stumble_t = 0.35
        self.sfx.append("tackle")
        if self.rng.random() < 0.5:
            self._say("TURNOVER", "info", time=0.8)

    def _personal_foul(self, fouler, victim, kind):
        if self.foul_cd > 0 or self.phase not in ("open", "throw_in"):
            return
        self.foul_cd = 0.45
        self.teams[fouler.team].fouls += 1
        own = self.own_goal_x(fouler.team)
        in_large = in_large_rectangle(victim.x, victim.z, own) or in_large_rectangle(fouler.x, fouler.z, own)
        goal_chance = dist_to_goal(victim.x, victim.z, self.attack_goal_x(victim.team)) < 17
        cynical = kind in ("pull", "trip") and (in_large or goal_chance)
        card = "black" if cynical else None
        self._drop_ball()
        if cynical:
            shown = self._show_card(fouler, card, silent=True)
            self._say(f"PENALTY  +  {shown.upper()} CARD", "penalty", sfx="whistle_long", time=2.2)
            self._begin_penalty(victim.team)
            return
        title = {"pull": "PULL DOWN", "trip": "TRIP", "charge": "CHARGE", "push": "PUSH"}.get(kind, "FOUL")
        if card:
            self._show_card(fouler, card, silent=True)
        attack_g = self.attack_goal_x(victim.team)
        if not inside_20(victim.x, attack_g):
            self.solo_team = victim.team
            self.solo_x, self.solo_z = victim.x, victim.z
            self.solo_t = 1.05
            self.solo_started = False
            self.phase = "solo_window"
            self.clock_running = False
            taker = victim if victim.active else self._nearest(victim.team, victim.x, victim.z)
            self._give(taker)
            if self.human_team == victim.team:
                self.controlled = taker.pid
            self._say(f"{title}  —  F TO SOLO AND GO", "foul", sfx="whistle", time=1.5)
            return
        self._say(title, "foul", sfx="whistle", time=1.4)
        self._place_set("free", victim.team, self._nearest(victim.team, victim.x, victim.z), victim.x, victim.z)

    def _show_card(self, p, infraction, silent=False):
        shown = card_result(p.yellow, p.black, infraction)
        if shown == "yellow":
            p.yellow += 1
            self.teams[p.team].yellow += 1
        elif shown == "black":
            p.black += 1
            p.in_bin = True
            p.sin_bin = SIN_BIN_MIN * 60.0
            p.has_ball = False
            p.z = -2.5
            p.x = HALF
            self.teams[p.team].black += 1
        else:
            p.sent_off = True
            p.on_pitch = False
            p.in_bin = False
            p.has_ball = False
            self.teams[p.team].red += 1
        if self.ball.holder is p:
            self._drop_ball()
        if self.controlled == p.pid and not p.active:
            self._switch()
        if not silent:
            label = {"yellow": "YELLOW CARD", "black": "BLACK CARD  10 MIN", "red": "RED CARD"}[shown]
            self._say(f"{label}  {p.short}", shown if shown != "black" else "black", sfx="whistle_long", time=2.2)
        return shown

    def _fifty(self, against, spot, reason):
        if self.foul_cd > 0:
            return
        self.foul_cd = 0.4
        awarded = 1 - against
        sign = self.attack_sign(awarded)
        gx = self.attack_goal_x(awarded)
        x = spot[0] + sign * 50.0
        x = self._not_inside(awarded, x, 13.0)
        z = clamp(spot[1], 8.0, PITCH_W - 8.0)
        if dist_to_goal(x, z, gx) < 40.0:
            x = gx - sign * 40.0
        self.free_can_arc = True
        self._drop_ball()
        self._say(reason, "foul", sfx="whistle", time=1.8)
        self._place_set("free", awarded, self._nearest(awarded, x, z), x, z, can_arc=True)

    def _not_inside(self, team, x, min_depth):
        gx = self.attack_goal_x(team)
        sign = self.attack_sign(team)
        limit = gx - sign * min_depth
        if sign > 0 and x > limit:
            return limit
        if sign < 0 and x < limit:
            return limit
        return clamp(x, 2.0, PITCH_L - 2.0)

    def _short_kickout(self, catcher):
        other = 1 - catcher.team
        gx = self.attack_goal_x(other)
        sign = self.attack_sign(other)
        x = gx - sign * 40.0
        self._drop_ball()
        self._say("KICK-OUT DID NOT CLEAR THE 40", "foul", sfx="whistle", time=1.8)
        self._place_set("free", other, self._nearest(other, x, CENTER_Z), x, CENTER_Z, can_arc=True)

    def _gk_foul(self, gk):
        self.teams[gk.team].fouls += 1
        self._drop_ball()
        self._say("KEEPER CANNOT TAKE THAT PASS", "foul", sfx="whistle", time=1.8)
        self._place_set("free", 1 - gk.team, self._nearest(1 - gk.team, gk.x, gk.z), gk.x, gk.z)

    def _square_ball(self, conceding, gx):
        # Free out to the defending team, 13 m from the goal the score was chalked off at.
        x = 13.0 if gx < 1.0 else PITCH_L - 13.0
        self._drop_ball()
        self._say("SQUARE BALL — SCORE DISALLOWED", "foul", sfx="whistle", time=2.0)
        self._place_set("free", conceding, self._nearest(conceding, x, CENTER_Z), x, CENTER_Z)

    def _structure(self, dt):
        if self.restart_grace > 0:
            return
        for team in (0, 1):
            own, opp, active = self._shape_counts(team)
            self.shape[team] = (own, opp)
            if structure_ok(own, opp, active):
                self.breach_t[team] = 0.0
                continue
            self.breach_t[team] += dt
            if self.breach_t[team] > 2.05 and self.foul_cd <= 0:
                self._structure_foul(team)
                return

    def _shape_counts(self, team):
        own = opp = active = 0
        for p in self.players:
            if p.team != team or not p.active:
                continue
            active += 1
            if self.in_own_half(team, p.x):
                own += 1
            elif p.role != "gk":
                opp += 1
        return own, opp, active

    def _structure_foul(self, team):
        self.foul_cd = 0.5
        self.breach_t[team] = 0.0
        self.teams[team].fouls += 1
        other = 1 - team
        gx = self.attack_goal_x(other)
        sign = self.attack_sign(other)
        x = gx - sign * 40.0
        self._drop_ball()
        self._say(f"STRUCTURE  {self.teams[team].short}  —  FREE ON THE ARC", "structure", sfx="whistle", time=2.0)
        self._place_set("free", other, self._best_kicker(other), x, CENTER_Z, can_arc=True)

    def _offer_mark(self, p, kind):
        self.phase = "mark_choice"
        self.mark_pid = p.pid
        self.mark_kind = kind
        self.mark_x, self.mark_z = p.x, p.z
        self.mark_t = 0.15 if self.human_team != p.team else 1.7
        self.clock_running = False
        self.teams[p.team].marks += 1
        title = "ADVANCED MARK" if kind == "advanced" else "KICK-OUT MARK"
        self._say(f"{title}  {p.short}", "mark", sfx="whistle", time=1.6)
        if self.human_team == p.team:
            self.controlled = p.pid

    def _begin_mark_free(self, p):
        self.mark_advantage_t = 0
        self._place_set("mark", p.team, p, self.mark_x, self.mark_z)
        self.ball.from_mark = True

    def _play_on_from_mark(self, p):
        self.phase = "open"
        self.clock_running = not self.hooter_sounded
        self.mark_advantage_t = 3.0
        self.mark_back = (p.team, p.pid, self.mark_x, self.mark_z)
        p.protect = 0.45
        self._say("PLAY ON", "info", time=0.8)

    def _tick_mark_advantage(self, dt):
        if self.mark_advantage_t <= 0 or not self.mark_back:
            return
        self.mark_advantage_t -= dt
        team, pid, x, z = self.mark_back
        if self.possession_team == team and self.mark_advantage_t > 0:
            return
        if self.possession_team != team and self.phase == "open":
            p = self.player_by_pid(pid) or self._nearest(team, x, z)
            self.mark_advantage_t = 0
            self.mark_back = None
            self._say("NO ADVANTAGE — BACK FOR THE MARK", "mark", sfx="whistle", time=1.6)
            self._place_set("mark", team, p, x, z)
            return
        if self.mark_advantage_t <= 0:
            self.mark_back = None

    def _begin_penalty(self, team):
        gx = self.attack_goal_x(team)
        sign = self.attack_sign(team)
        x = gx - sign * PENALTY_DIST
        taker = self._best_kicker(team)
        dgk = self._by_role(1 - team, "gk")
        if dgk:
            dgk.x = gx - sign * 0.7
            dgk.z = CENTER_Z
        self.teams[team].frees += 1
        self._place_set("penalty", team, taker, x, CENTER_Z)

    def _award_45(self, team, z, gx):
        sign = 1.0 if gx < 1.0 else -1.0
        x = gx + sign * 45.0
        z = clamp(z, 10.0, PITCH_W - 10.0)
        self.teams[team].frees += 1
        self._say("FORTY-FIVE", "info", sfx="whistle", time=1.4)
        self._place_set("fortyfive", team, self._best_kicker(team), x, z)

    def _begin_kickout(self, team):
        team = team if team in (0, 1) else 0
        gk = self._by_role(team, "gk")
        gx = self.own_goal_x(team)
        sign = self.attack_sign(team)
        x = gx + sign * 20.0
        self._shape_kickout(team)
        self.teams[team].kickouts += 1
        self.saved_control = self.controlled
        self._place_set("kickout", team, gk, x, CENTER_Z)
        self._say("KICK-OUT  ·  MUST CLEAR THE 40", "kickout", time=1.5)
        self.restart_grace = 2.2

    def _shape_kickout(self, kicking):
        for p in self.players:
            if not p.active or p.role == "gk":
                continue
            own = self.own_goal_x(p.team)
            sgn = self.attack_sign(p.team)
            if p.role in OWN_HALF_ROLES:
                p.x = own + sgn * (7 + (p.number % 4) * 2.5)
            elif p.role in ATTACK_HALF_ROLES:
                p.x = own + sgn * (PITCH_L * 0.64)
            elif p.team == kicking:
                p.x = own + sgn * (50 + (p.number % 4) * 3)
            else:
                kg = self.own_goal_x(kicking)
                ks = self.attack_sign(kicking)
                p.x = kg + ks * (34 + (p.number % 5) * 1.8)
            p.z = clamp(8 + (p.number * 6.3) % 74, 5, PITCH_W - 5)
            p.x = clamp(p.x, 1.5, PITCH_L - 1.5)

    def _place_set(self, kind, team, taker, x, z, can_arc=False):
        if taker is None:
            taker = self._nearest(team, x, z)
        self.phase = "set_piece"
        self.set_kind = kind
        self.set_team = team
        self.taker = taker.pid
        self.set_x, self.set_z = clamp(x, 1.5, PITCH_L - 1.5), clamp(z, 1.5, PITCH_W - 1.5)
        self.set_timer = 0.0
        self.free_can_arc = can_arc or self.free_can_arc
        self.clock_running = False
        self._drop_ball()
        taker.x, taker.z = self.set_x, self.set_z
        gx = self.attack_goal_x(team)
        taker.facing = math.atan2(CENTER_Z - taker.z, gx - taker.x)
        self._give(taker)
        if self.human_team == team:
            self.controlled = taker.pid
        self._push_out(self.set_x, self.set_z, 13.0, taker.pid)
        self.teams[team].frees += 0

    def _push_out(self, x, z, radius, ignore_pid):
        for p in self.players:
            if not p.active or p.pid == ignore_pid:
                continue
            d = dist(p.x, p.z, x, z)
            if 0.05 < d < radius:
                p.x = x + (p.x - x) / d * radius
                p.z = z + (p.z - z) / d * radius
                p.x = clamp(p.x, 1.0, PITCH_L - 1.0)
                p.z = clamp(p.z, 1.0, PITCH_W - 1.0)

    def _move_taker(self, p, dt, inp):
        self._apply_human_move(p, dt, inp)
        dx, dz = p.x - self.set_x, p.z - self.set_z
        if math.hypot(dx, dz) > 4.0:
            s = 4.0 / math.hypot(dx, dz)
            p.x = self.set_x + dx * s
            p.z = self.set_z + dz * s
        gx = self.attack_goal_x(p.team)
        if dist_to_goal(p.x, p.z, gx) + 0.15 < dist_to_goal(self.set_x, self.set_z, gx):
            p.x, p.z = self.set_x, self.set_z
        if inp.aim is not None:
            p.facing = math.atan2(inp.aim[1] - p.z, inp.aim[0] - p.x)
        self._stick(p)

    def _move_taker_to_arc(self, p):
        gx = self.attack_goal_x(p.team)
        sign = self.attack_sign(p.team)
        p.x = gx - sign * 40.2
        p.z = CENTER_Z
        self.set_x, self.set_z = p.x, p.z
        self._stick(p)
        self._say("BROUGHT TO THE 40", "info", time=1.0)

    def _move_support(self, dt, taker):
        for p in self.players:
            if not p.active or p is taker:
                continue
            if self.set_kind == "kickout":
                continue
            tx, tz = p.x, p.z
            # Hold a loose shape rather than freezing.
            self._move_toward(p, tx, tz, dt, False)

    def _take_set(self, taker, inp):
        kind = self.set_kind
        if kind == "kickout":
            encroached = False
            for p in self.players:
                if p.team != taker.team and p.active and dist(p.x, p.z, taker.x, taker.z) < 12.6:
                    encroached = True
                    break
            if encroached:
                self._fifty(1 - taker.team, (taker.x, taker.z), "ENCROACHMENT ON THE KICK-OUT — 50 METRES")
                return
        self._push_out(taker.x, taker.z, 12.5, taker.pid)
        power = self.charge if self.charge > 0.15 else 0.72
        self.charge = 0.0
        if kind == "kickout":
            tx, tz = self._kickout_aim(taker)
            self._strike(taker, "kickout", tx, tz, 2.5, 0.86, "kickout")
        elif kind == "penalty":
            gx = self.attack_goal_x(taker.team)
            sign = self.attack_sign(taker.team)
            tz = CENTER_Z
            ty = 1.0
            if inp.aim is not None and taker.team == self.human_team:
                tz = clamp(self._z_on_line(taker.x, taker.z, inp.aim[0], inp.aim[1], gx) or CENTER_Z, CENTER_Z - 2.3, CENTER_Z + 2.3)
                ty = 3.4 if inp.aim_high else 0.95
            else:
                tz = CENTER_Z + self.rng.uniform(-1.1, 1.1) * (1.15 - taker.kick)
            self._strike(taker, "penalty", gx + sign * 2.2, tz, ty, 0.84, "penalty")
            self.teams[taker.team].shots += 1
        elif kind == "fortyfive":
            gx = self.attack_goal_x(taker.team)
            sign = self.attack_sign(taker.team)
            self._strike(taker, "45", gx + sign * 2.2, CENTER_Z + self.rng.uniform(-0.6, 0.6), 4.0, 0.86, "fortyfive")
            self.teams[taker.team].shots += 1
        elif kind == "sideline":
            sign = self.attack_sign(taker.team)
            self._strike(taker, "sideline", taker.x + sign * 22, CENTER_Z, 1.6, 0.6, "sideline")
        else:
            # Free or mark. Human aims. AI shoots if the arc or the posts are on.
            if taker.team == self.human_team and inp.aim is not None:
                self._human_kick(taker, inp, power)
                # human_kick uses set_kind None. Patch two-point legality: a 45/sideline
                # already returned. Frees from the arc are legal two-pointers.
                self.ball.set_kind = kind
                self.ball.from_mark = kind == "mark"
                self.ball.two_point = two_point_strike("punt", self.ball.kicker_dist, kind if kind in ("fortyfive", "sideline") else None)
            else:
                self._ai_set_kick(taker, kind)
        self.phase = "open"
        self.clock_running = not self.hooter_sounded
        self.restart_grace = 1.5 if kind == "kickout" else 0.8
        if self.hooter_sounded:
            self.hooter_one_kick = True
        if kind == "kickout" and self.saved_control is not None and self.human_team == taker.team:
            # Stay on the keeper if they still have to see it away; control returns on the catch.
            pass
        self.free_can_arc = False

    def _kickout_aim(self, gk):
        sign = self.attack_sign(gk.team)
        gx = self.own_goal_x(gk.team)
        best, bs = None, -1e9
        for m in self.players:
            if m.team != gk.team or not m.active or m.role == "gk":
                continue
            depth = (m.x - gx) * sign
            if depth < 47:
                continue
            opp, od = self._nearest_opp(m)
            score = od + depth * 0.2
            if score > bs:
                best, bs = m, score
        if best:
            return best.x + sign * 1.5, best.z
        return gx + sign * 54, CENTER_Z + self.rng.choice((-12, 12, 0))

    def _ai_set_kick(self, taker, kind):
        gx = self.attack_goal_x(taker.team)
        sign = self.attack_sign(taker.team)
        d = dist_to_goal(taker.x, taker.z, gx)
        if d <= 52 and abs(taker.z - CENTER_Z) < 18:
            ty = 3.6
            self._strike(taker, "punt", gx + sign * 2.4, CENTER_Z + self.rng.uniform(-0.7, 0.7), ty, 0.82, kind)
            self.teams[taker.team].shots += 1
            self.ball.two_point = two_point_strike("punt", dist_to_goal(taker.x, taker.z, gx), None)
            self.ball.set_kind = kind
            return
        mate = None
        best = -1
        for m in self.players:
            if m.team == taker.team and m.active and m is not taker and (m.x - taker.x) * sign > 8:
                od = self._nearest_opp(m)[1]
                if od > best:
                    best, mate = od, m
        if mate:
            self._strike(taker, "punt", mate.x, mate.z, 1.8, 0.66, kind)
        else:
            self._strike(taker, "punt", taker.x + sign * 25, taker.z, 1.5, 0.6, kind)
        self.ball.set_kind = kind
        self.ball.from_mark = kind == "mark"

    # ------------------------------------------------------------------
    # Clock, hooter, periods
    # ------------------------------------------------------------------
    def _tick_clock(self, dt):
        if not self.clock_running or self.hooter_sounded:
            return
        self.clock += dt * self.time_scale
        if self.possession_team in (0, 1):
            self.teams[self.possession_team].possession += dt
        gdt = dt * self.time_scale
        for p in self.players:
            if p.in_bin:
                p.sin_bin -= gdt
                if p.sin_bin <= 0:
                    p.in_bin = False
                    p.sin_bin = 0
                    self._place_player_home(p)
                    self._say(f"{p.short} RETURNS", "info", time=1.6)
        if self.clock >= self.half_length:
            self.clock = self.half_length
            self._sound_hooter()

    def _sound_hooter(self):
        if self.hooter_sounded:
            return
        self.hooter_sounded = True
        self.sfx.append("hooter")
        if self.phase == "set_piece":
            self.hooter_one_kick = True
            self._say("HOOTER — LAST KICK", "hooter", time=1.8)
            return
        if self.phase == "open" and self.ball.in_flight and not self.ball.holder:
            self.ball.hooter_flight = True
            self._say("HOOTER", "hooter", time=1.6)
            return
        self._say("HOOTER", "hooter", time=1.6)
        self._end_period()

    def _hooter_dead_check(self):
        if not self.hooter_sounded or self.phase != "open":
            return
        b = self.ball
        dead = b.holder or (not b.in_flight and b.y <= BALL_R + 0.08 and math.hypot(b.vx, b.vz) < 0.45)
        if dead:
            self._end_period()

    def _end_period(self):
        if self.phase in ("half_time", "full_time", "extra_prompt"):
            return
        self.clock_running = False
        self._drop_ball()
        self.phase_t = 0.0
        if self.period in (1, 3):
            self.phase = "half_time"
            label = "HALF TIME" if self.period == 1 else "CHANGE ENDS"
            self._say(label, "hooter", sfx="whistle_long", time=5)
            return
        if self.period == 2 and self._tied() and self.allow_extra and not self.extra_started:
            self.phase = "extra_prompt"
            self._say("LEVEL  —  EXTRA TIME?", "hooter", sfx="whistle_long", time=6)
            return
        self.phase = "full_time"
        self._say("FULL TIME", "hooter", sfx="whistle_long", time=6)

    def _next_period(self):
        self.period += 1
        if self.period >= 3:
            self.extra_started = True
            self.half_length = EXTRA_HALF_MIN * 60.0
        else:
            self.half_length = self.normal_length
        self.clock = 0.0
        self.hooter_sounded = False
        self.hooter_one_kick = False
        self.attack_positive[0] = not self.attack_positive[0]
        self.attack_positive[1] = not self.attack_positive[1]
        for p in self.players:
            p.stamina = min(1.0, p.stamina + 0.4)
            p.steps = 0
        self._place_throw_in()
        self.phase = "countdown"
        self.countdown = 0.35 if self.auto_continue else 2.0
        self._say(self.period_name(), "info", time=1.6)

    def _score(self, team, kind, value):
        side = self.teams[team]
        scorer = self.player_by_pid(self.ball.kicker_pid)
        name = scorer.short if scorer else side.name
        self.last_scorer = name
        if kind == "goal":
            side.goals += 1
            self.sfx.append("goal")
            self._say(f"GOAL   {side.short}   {name}", "goal", time=3.0)
            self.banner_sub = self.rng.choice(GOAL_LINES)
        else:
            side.points += value
            if value >= 2:
                side.two_pointers += 1
                self.sfx.append("two")
                self._say(f"TWO POINTS   {side.short}   {name}", "two", time=2.6)
                self.banner_sub = self.rng.choice(TWO_LINES)
            else:
                self.sfx.append("point")
                self._say(f"POINT   {side.short}   {name}", "point", time=2.1)
                self.banner_sub = self.rng.choice(POINT_LINES)
        self.kickout_team = 1 - team
        self.phase = "celebrate"
        self.celebrate_t = 3.4 if kind == "goal" else 2.4
        self.after_celebrate = "end" if self.hooter_sounded else "kickout"
        self.clock_running = False
        self.replay_clip = list(self.history[-120:])
        self.mark_advantage_t = 0
        self.mark_back = None
        gx = self.attack_goal_x(team)
        self._drop_ball()
        self.ball.x = gx + (-0.8 if gx > 1 else 0.8)
        self.ball.y = 1.15 if kind == "goal" else 3.5
        self.ball.z = CENTER_Z
        self.ball.resolved = True

    # ------------------------------------------------------------------
    # Placement and queries
    # ------------------------------------------------------------------
    def _reset_positions(self):
        for side in self.teams:
            for p in side.players:
                if p.sent_off or p.in_bin or not p.on_pitch:
                    continue
                self._place_player_home(p)
                p.vx = p.vz = 0
                p.has_ball = False
                p.steps = 0
                p.bounce_used = False
        self.ball.holder = None

    def _place_player_home(self, p):
        depth, zf = self.slot(p)
        p.x, p.z = self.slot_world(p.team, depth, zf)
        p.facing = 0.0 if self.attack_positive[p.team] else math.pi
        p.y = 0

    def _place_throw_in(self):
        self._reset_positions()
        c0 = self._by_role(0, "mf1")
        c1 = self._by_role(1, "mf1")
        self.contestants = (c0.pid, c1.pid)
        c0.x, c0.z = HALF - 1.1, CENTER_Z - 0.8
        c1.x, c1.z = HALF + 1.1, CENTER_Z + 0.8
        c0.facing, c1.facing = 0.2, math.pi - 0.2
        for p in self.players:
            if not p.active or p in (c0, c1):
                continue
            gx = self.own_goal_x(p.team)
            sign = self.attack_sign(p.team)
            depth = p.x if gx < 1 else PITCH_L - p.x
            if depth > 42:
                p.x = gx + sign * 38
        self._drop_ball()
        self.ball.x, self.ball.y, self.ball.z = HALF, 0.22, CENTER_Z
        self.ball.resolved = False
        self.possession_team = None

    def _nearest(self, team, x, z):
        best, bd = None, 1e9
        for p in self.players:
            if p.team == team and p.active:
                d = dist(p.x, p.z, x, z)
                if d < bd:
                    best, bd = p, d
        return best or self.teams[team].players[0]

    def _nearest_opp(self, p):
        best, bd = None, 1e9
        for o in self.players:
            if o.team != p.team and o.active:
                d = dist(o.x, o.z, p.x, p.z)
                if d < bd:
                    best, bd = o, d
        return best, bd

    def _best_kicker(self, team):
        best, bk = None, -1
        for p in self.players:
            if p.team == team and p.active and p.role != "gk" and p.kick > bk:
                best, bk = p, p.kick
        return best or self._nearest(team, HALF, CENTER_Z)

    def _lane_ok(self, p, tx, tz) -> bool:
        dx, dz = tx - p.x, tz - p.z
        d = math.hypot(dx, dz) or 1
        dx, dz = dx / d, dz / d
        for o in self.players:
            if o.team == p.team or not o.active:
                continue
            rel = (o.x - p.x) * dx + (o.z - p.z) * dz
            if 1 < rel < d - 1:
                lat = abs((o.x - p.x) * -dz + (o.z - p.z) * dx)
                if lat < 1.1:
                    return False
        return True

    def _switch(self):
        if self.human_team is None:
            return
        mates = [p for p in self.players if p.team == self.human_team and p.active and p.pid != self.controlled]
        if not mates:
            return
        mates.sort(key=lambda p: dist(p.x, p.z, self.ball.x, self.ball.z))
        self.switch_i += 1
        self.controlled = mates[self.switch_i % len(mates)].pid
        self.sfx.append("switch")

    def _update_ref(self, dt):
        tx = clamp(self.ball.x - 6, 8, PITCH_L - 8)
        tz = clamp(min(self.ball.z, CENTER_Z) - 8, 6, 30)
        self.ref_x += (tx - self.ref_x) * min(1, dt * 1.4)
        self.ref_z += (tz - self.ref_z) * min(1, dt * 1.4)
        self.ref_facing = math.atan2(self.ball.z - self.ref_z, self.ball.x - self.ref_x)

    def _update_hint(self, inp):
        p = self.controlled_player()
        if self.phase == "throw_in":
            self.hint = "SPACE at the top of the throw-in"
            return
        if self.phase == "mark_choice":
            self.hint = "G claim the mark     SPACE play on"
            return
        if self.phase == "solo_window":
            self.hint = "F solo and go, not backwards     SPACE take the free"
            return
        if self.phase == "set_piece":
            extra = "     2 bring it to the arc" if self.free_can_arc else ""
            label = {"kickout": "KICK-OUT", "penalty": "PENALTY", "fortyfive": "45", "sideline": "SIDELINE", "mark": "MARK", "free": "FREE"}.get(self.set_kind, "FREE")
            self.hint = f"{label}   SPACE to take it{extra}"
            return
        if self.phase in ("half_time", "full_time", "extra_prompt"):
            self.hint = "ENTER to continue"
            return
        if not p or not p.has_ball:
            self.hint = "X tackle    Z block    C switch    Q call for it"
            return
        d = dist_to_goal(p.x, p.z, self.attack_goal_x(p.team))
        if p.bounce_used:
            self.hint = "BOUNCE USED — solo before you bounce again"
        elif d >= 39.8:
            self.hint = "TWO-POINT RANGE — aim over the bar"
        elif d < 18:
            self.hint = "Aim under the bar for a goal, over it for a point"
        else:
            self.hint = "SPACE kick    Q hand    E fist    F solo    R bounce    V step"
        if self.charge > 0.05:
            self.hint = f"POWER {int(self.charge * 100)}%    " + self.hint

    def _say(self, text, kind="info", sfx=None, time=1.8):
        self.banner = text
        self.banner_kind = kind
        self.banner_t = time
        self.ticker.appendleft(text)
        if sfx:
            self.sfx.append(sfx)

    def _record(self, dt):
        self._rec_acc += dt
        if self._rec_acc < 0.05:
            return
        self._rec_acc = 0.0
        frame = {
            "ball": (self.ball.x, self.ball.y, self.ball.z, self.ball.spin),
            "players": tuple(
                (p.team, p.number, p.x, p.y, p.z, p.facing, p.role, 1 if p.has_ball else 0, p.kick_t, p.dive)
                for p in self.players
                if p.on_pitch and not p.sent_off and not p.in_bin
            ),
        }
        self.history.append(frame)
        if len(self.history) > 160:
            del self.history[:40]

    def _decay(self, dt):
        for p in self.players:
            p.solo_t = max(0.0, p.solo_t - dt)
            p.bounce_t = max(0.0, p.bounce_t - dt)
            p.kick_t = max(0.0, p.kick_t - dt)
            p.stumble_t = max(0.0, p.stumble_t - dt)
            p.protect = max(0.0, p.protect - dt)
            p.solo_lock = max(0.0, p.solo_lock - dt)
            p.action_cd = max(0.0, p.action_cd - dt)
            p.blocking = max(0.0, p.blocking - dt)
            p.think = max(0.0, p.think - dt)
            if p.jump_t > 0:
                p.jump_t = max(0.0, p.jump_t - dt)
                u = 1.0 - (p.jump_t / 0.48)
                p.y = math.sin(clamp(u, 0.0, 1.0) * math.pi) * 0.68
            else:
                p.y = max(0.0, p.y - dt * 5.0)
            if abs(p.dive) > 0.01:
                p.dive *= max(0.0, 1.0 - dt * 2.5)
            if self.phase != "open":
                p.stamina = min(1.0, p.stamina + dt * 0.04)
