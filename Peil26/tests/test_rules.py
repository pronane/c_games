"""Rule tests for the 2026 playing rules simulated by PEIL 26."""

from __future__ import annotations

import unittest

from peil26.match import HumanInput, Match
from peil26.rules import (
    card_result,
    classify_crossing,
    gk_receive_legal,
    mark_type,
    solo_and_go_ok,
    structure_ok,
    two_point_strike,
)
from peil26.settings import PITCH_L


def match(**kw):
    base = dict(half_minutes=2, human_team=None, auto_continue=True, allow_extra=False, seed=3, intro=0.2)
    base.update(kw)
    return Match(**base)


class PureRules(unittest.TestCase):
    def test_scores(self):
        self.assertEqual(classify_crossing(1.2, 45, "punt", 12, False, None, False), ("goal", 3))
        self.assertEqual(classify_crossing(4.0, 45, "punt", 22, False, None, False), ("point", 1))
        self.assertEqual(classify_crossing(4.2, 45, "punt", 42, False, None, False), ("point", 2))
        self.assertEqual(classify_crossing(4.2, 45, "punt", 42, True, None, False), ("point", 1))
        self.assertEqual(classify_crossing(4.2, 45, "hand", 42, False, None, False), ("wide", 0))
        self.assertEqual(classify_crossing(4.2, 45, "45", 45, False, "fortyfive", False), ("point", 1))
        self.assertEqual(classify_crossing(1.1, 45, "punt", 8, False, None, True), ("square", 0))
        self.assertEqual(classify_crossing(4.0, 52, "punt", 20, False, None, False), ("wide", 0))
        self.assertEqual(classify_crossing(2.5, 45, "punt", 20, False, None, False)[0], "crossbar")

    def test_two_point_flag(self):
        self.assertTrue(two_point_strike("punt", 40.0, None))
        self.assertFalse(two_point_strike("punt", 28.0, None))
        self.assertFalse(two_point_strike("hand", 50.0, None))
        self.assertFalse(two_point_strike("45", 45.0, "fortyfive"))
        self.assertFalse(two_point_strike("sideline", 50.0, "sideline"))

    def test_marks(self):
        # Kick from x=80, catch at x=130, attacking the goal at 145.
        self.assertEqual(mark_type("punt", 80, 130, 145, False, None), "advanced")
        self.assertIsNone(mark_type("punt", 80, 130, 145, True, None))
        self.assertIsNone(mark_type("hand", 80, 130, 145, False, None))
        self.assertIsNone(mark_type("punt", 110, 130, 145, False, None))
        self.assertEqual(mark_type("kickout", 20, 50, 145, False, 0.0), "kickout")
        self.assertIsNone(mark_type("kickout", 20, 30, 145, False, 0.0))
        self.assertIsNone(mark_type("punt", 70, 130, 145, False, None, set_kind="free"))
        self.assertEqual(mark_type("punt", 70, 130, 145, False, None, set_kind="mark", from_mark=True), "advanced")

    def test_solo_and_go(self):
        ok, why = solo_and_go_ok(70, 45, 73, 45, 1, 145)
        self.assertTrue(ok, why)
        ok, why = solo_and_go_ok(70, 45, 67, 45, 1, 145)
        self.assertFalse(ok)
        self.assertEqual(why, "backwards")
        ok, _ = solo_and_go_ok(130, 45, 132, 45, 1, 145)
        self.assertFalse(ok)

    def test_cards_and_structure_and_keeper(self):
        self.assertEqual(card_result(0, 0, "yellow"), "yellow")
        self.assertEqual(card_result(1, 0, "yellow"), "red")
        self.assertEqual(card_result(0, 0, "black"), "black")
        self.assertEqual(card_result(1, 0, "black"), "red")
        self.assertEqual(card_result(0, 1, "black"), "red")
        self.assertTrue(structure_ok(4, 3, 15))
        self.assertFalse(structure_ok(3, 3, 15))
        self.assertFalse(structure_ok(4, 2, 15))
        self.assertTrue(structure_ok(2, 1, 6))
        self.assertFalse(gk_receive_legal(False, False))
        self.assertTrue(gk_receive_legal(True, False))
        self.assertTrue(gk_receive_legal(False, True))


class MatchRules(unittest.TestCase):
    def test_goal_and_two_pointer(self):
        m = match(human_team=0)
        m.debug_open()
        m.ball.holder = None
        m.ball.in_flight = True
        m.ball.kick_type = "punt"
        m.ball.kicker_team = 0
        m.ball.kicker_pid = m.teams[0].players[10].pid
        m.ball.kicker_dist = 42
        m.ball.two_point = True
        m.ball.last_team = 0
        m.ball.kick_origin = (100, 45)
        m.ball.px, m.ball.py, m.ball.pz = 144.2, 4.1, 45
        m.ball.x, m.ball.y, m.ball.z = 145.6, 4.1, 45
        m.ball.resolved = False
        m._boundaries()
        self.assertEqual(m.teams[0].points, 2)
        self.assertEqual(m.teams[0].total, 2)
        self.assertEqual(m.phase, "celebrate")

        m = match()
        m.debug_open()
        m.ball.kick_type = "punt"
        m.ball.kicker_team = 0
        m.ball.kicker_pid = m.teams[0].players[13].pid
        m.ball.last_team = 0
        m.ball.kick_origin = (130, 45)
        m.ball.kicker_dist = 15
        m.ball.px, m.ball.py, m.ball.pz = 144.4, 1.1, 44
        m.ball.x, m.ball.y, m.ball.z = 145.5, 1.1, 44
        # Keep the keeper off the line so this is a finish, not a save.
        m._by_role(1, "gk").x = 70
        m._boundaries()
        self.assertEqual(m.teams[0].goals, 1)
        self.assertEqual(m.teams[0].total, 3)

    def test_handpass_is_not_a_point(self):
        m = match()
        m.debug_open()
        m.ball.kick_type = "hand"
        m.ball.kicker_team = 0
        m.ball.last_team = 0
        m.ball.kick_origin = (120, 45)
        m.ball.kicker_dist = 20
        m.ball.px, m.ball.py, m.ball.pz = 144.2, 4.0, 45
        m.ball.x, m.ball.y, m.ball.z = 145.4, 4.0, 45
        m._boundaries()
        self.assertEqual(m.teams[0].total, 0)
        self.assertEqual(m.phase, "celebrate")  # wide, then kick-out

    def test_double_bounce_and_steps(self):
        m = match(human_team=0)
        m.debug_open()
        p = m.controlled_player()
        m._give(p)
        m._try_bounce(p)
        self.assertTrue(p.bounce_used)
        m._try_bounce(p)
        self.assertEqual(m.phase, "set_piece")
        self.assertEqual(m.set_team, 1)

        m = match(human_team=0)
        m.debug_open()
        p = m.controlled_player()
        m._give(p)
        p.steps = 5.0
        p.solo_lock = 0.4
        m._enforce_steps(p)
        self.assertEqual(m.phase, "set_piece")
        self.assertIn("OVERCARRYING", m.banner)

    def test_short_kickout_and_advanced_mark(self):
        m = match()
        m.debug_open()
        catcher = m._by_role(0, "mf1")
        catcher.x, catcher.z = 30, 45
        m.ball.kick_type = "kickout"
        m.ball.kicker_team = 0
        m.ball.kicker_pid = m._by_role(0, "gk").pid
        m.ball.kickout_goal = 0.0
        m.ball.in_flight = True
        m.ball.kick_origin = (20, 45)
        m._on_catch(catcher)
        self.assertEqual(m.phase, "set_piece")
        self.assertEqual(m.set_team, 1)
        self.assertIn("40", m.banner)

        m = match()
        m.debug_open()
        catcher = m._by_role(0, "ff")
        catcher.x, catcher.z = 132, 45
        m.ball.kick_type = "punt"
        m.ball.kicker_team = 0
        m.ball.kicker_pid = m._by_role(0, "mf2").pid
        m.ball.kick_origin = (80, 45)
        m.ball.bounced = False
        m.ball.in_flight = True
        m.ball.set_kind = None
        m._on_catch(catcher)
        self.assertEqual(m.phase, "mark_choice")
        self.assertEqual(m.mark_kind, "advanced")

    def test_square_disallows_goal(self):
        m = match()
        m.debug_open()
        m.ball.kick_type = "punt"
        m.ball.kicker_team = 0
        m.ball.last_team = 0
        m.ball.square_at_kick = True
        m.ball.kick_origin = (130, 45)
        m.ball.kicker_dist = 12
        m.ball.px, m.ball.py, m.ball.pz = 144.3, 1.0, 45
        m.ball.x, m.ball.y, m.ball.z = 145.4, 1.0, 45
        m._boundaries()
        self.assertEqual(m.teams[0].goals, 0)
        self.assertEqual(m.phase, "set_piece")
        self.assertEqual(m.set_team, 1)

    def test_structure_breach(self):
        m = match()
        m.debug_open()
        m.restart_grace = 0
        for p in m.players:
            if p.team == 0:
                p.x = 110
        m._structure(2.2)
        self.assertEqual(m.phase, "set_piece")
        self.assertEqual(m.set_team, 1)
        self.assertIn("STRUCTURE", m.banner)

    def test_hooter_ends_half_but_flight_can_score(self):
        m = match(half_minutes=1, time_scale=30, human_team=None)
        m.debug_open()
        m.clock = m.half_length - 0.01
        m.clock_running = True
        m._tick_clock(0.05)
        self.assertTrue(m.hooter_sounded)

        m = match()
        m.debug_open()
        m.hooter_sounded = True
        m.ball.hooter_flight = True
        m.ball.kick_type = "punt"
        m.ball.kicker_team = 0
        m.ball.last_team = 0
        m.ball.kick_origin = (120, 45)
        m.ball.kicker_dist = 20
        m.ball.px, m.ball.py, m.ball.pz = 144.2, 3.8, 45
        m.ball.x, m.ball.y, m.ball.z = 145.5, 3.8, 45
        m._boundaries()
        self.assertEqual(m.teams[0].points, 1)
        self.assertEqual(m.after_celebrate, "end")

    def test_solo_and_go_refuses_a_backward_step(self):
        m = match(human_team=0)
        m.debug_open()
        p = m.controlled_player()
        m.phase = "solo_window"
        m.solo_team = 0
        m.solo_x, m.solo_z = p.x, p.z
        m.solo_t = 0.8
        m.solo_started = True
        m._give(p)
        p.x -= 1.2
        m._update_solo_window(0.05, HumanInput())
        self.assertEqual(m.phase, "set_piece")
        self.assertIn("BACK", m.banner)

    def test_keeper_pass_restriction(self):
        m = match()
        m.debug_open()
        gk = m._by_role(0, "gk")
        kicker = m._by_role(0, "chf")
        kicker.x, kicker.z = 60, 45
        gk.x, gk.z = 8, 45
        m.ball.kick_type = "hand"
        m.ball.kicker_team = 0
        m.ball.kicker_pid = kicker.pid
        m.ball.kick_origin = (60, 45)
        m.ball.in_flight = True
        m._on_catch(gk)
        self.assertEqual(m.phase, "set_piece")
        self.assertIn("KEEPER", m.banner)

    def test_ai_match_runs(self):
        m = match(half_minutes=1, time_scale=40, human_team=None, seed=11)
        for _ in range(60 * 25):
            m.update(1 / 30)
            if m.phase == "full_time":
                break
        self.assertIn(m.phase, ("full_time", "half_time", "open", "set_piece", "celebrate", "countdown", "throw_in"))
        self.assertGreater(m.real_time, 1.0)
        # Scores are non-negative and the total identity holds.
        for side in m.teams:
            self.assertGreaterEqual(side.goals, 0)
            self.assertEqual(side.total, side.goals * 3 + side.points)


if __name__ == "__main__":
    unittest.main()
