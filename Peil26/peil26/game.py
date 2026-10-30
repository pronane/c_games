"""PEIL 26 application: menus, input, and the match loop."""

from __future__ import annotations

import sys
from pathlib import Path

import pygame

from peil26.audio import Audio
from peil26.match import HumanInput, Match
from peil26.render import Renderer, draw_menu_panel
from peil26.settings import CONTROLS_TEXT, RULES_TEXT, VERSION
from peil26.teams import COUNTIES

MODES = ["broadcast", "follow", "goal", "tactical", "low"]
LENGTHS = [
    ("Quick  ·  8 minutes", 8, 8.0),
    ("League  ·  35 minutes", 35, 10.0),
    ("Senior clock  ·  35 minutes", 35, 6.0),
]


def project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def log_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent / "peil26.log"
    return project_root() / "peil26.log"


def load_fonts():
    root = project_root() / "assets" / "fonts"
    def face(name, size):
        path = root / name
        if path.exists():
            return pygame.font.Font(str(path), size)
        return pygame.font.SysFont("arial", size)
    return {
        "xl": face("Rajdhani-Bold.ttf", 84),
        "lg": face("Rajdhani-Bold.ttf", 54),
        "md": face("Rajdhani-SemiBold.ttf", 28),
        "sm": face("Rajdhani-Medium.ttf", 20),
        "xs": face("Rajdhani-Medium.ttf", 16),
        "score": face("Rajdhani-Bold.ttf", 32),
    }


class Game:
    def __init__(self, screenshot: str | None = None):
        pygame.mixer.pre_init(44100, -16, 2, 512)
        pygame.init()
        pygame.display.set_caption("PEIL 26  —  Gaelic Football")
        self.screen = pygame.display.set_mode((1280, 720), pygame.RESIZABLE)
        self._icon()
        self.clock = pygame.time.Clock()
        self.fonts = load_fonts()
        self.renderer = Renderer()
        self.renderer.build(self.fonts["xs"])
        self.audio = Audio()
        self.running = True
        self.state = "title"
        self.index = 0
        self.match: Match | None = None
        self.attract = Match(home="Dublin", away="Kerry", half_minutes=10, human_team=None, time_scale=12, auto_continue=True, allow_extra=False, seed=26, intro=0.4)
        self.home = 0
        self.away = 1
        self.difficulty = 1
        self.length = 1
        self.side = 0
        self.rules_scroll = 0
        self.paused = False
        self.sub_off = 0
        self.sub_on = 0
        self.just = set()
        self.aim = None
        self.aim_high = None
        self.screenshot = screenshot
        self.frames = 0
        self.replay_i = 0
        self.replay_on = False
        self.audio.start_music()
        if screenshot:
            self._start_match()
            self.match.debug_open()
            self.state = "play"

    def _icon(self):
        icon = pygame.Surface((64, 64))
        icon.fill((12, 28, 18))
        pygame.draw.circle(icon, (28, 120, 58), (32, 34), 22)
        pygame.draw.arc(icon, (255, 196, 64), (8, 10, 48, 48), 0.3, 2.8, 3)
        pygame.draw.line(icon, (240, 240, 240), (32, 8), (32, 56), 2)
        pygame.display.set_icon(icon)

    def run(self):
        while self.running:
            dt = min(0.05, self.clock.tick(60) / 1000.0)
            self.just = set()
            self._events()
            self._update(dt)
            self._draw()
            pygame.display.flip()
            self.frames += 1
            if self.screenshot and self.frames > 150:
                pygame.image.save(self.screen, self.screenshot)
                self.running = False
        self.audio.stop_bed()
        self.audio.stop_music()
        pygame.quit()

    def _events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                self.just.add(event.key)
                if event.key == pygame.K_F11:
                    self._fullscreen()
                elif event.key == pygame.K_m:
                    self.audio.toggle_mute()
                    if not self.audio.muted and self.state == "play":
                        self.audio.start_bed()
            elif event.type == pygame.MOUSEBUTTONDOWN:
                self.just.add(("mouse", event.button))
            elif event.type == pygame.VIDEORESIZE:
                self.screen = pygame.display.set_mode((event.w, event.h), pygame.RESIZABLE)

    def _fullscreen(self):
        flags = self.screen.get_flags()
        if flags & pygame.FULLSCREEN:
            self.screen = pygame.display.set_mode((1280, 720), pygame.RESIZABLE)
        else:
            self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)

    def _update(self, dt):
        if self.state == "title":
            self.attract.update(dt)
            self.renderer.cam.follow(self.attract, dt)
            self._menu_nav(["Play match", "Rules of 2026", "Controls", "Quit"], self._title_pick)
        elif self.state == "teams":
            self.attract.update(dt)
            self.renderer.cam.follow(self.attract, dt)
            self._team_input()
        elif self.state == "rules":
            if pygame.K_UP in self.just or pygame.K_w in self.just:
                self.rules_scroll = max(0, self.rules_scroll - 1)
            if pygame.K_DOWN in self.just or pygame.K_s in self.just:
                self.rules_scroll += 1
            if pygame.K_ESCAPE in self.just:
                self.state = "title"
        elif self.state == "controls":
            if pygame.K_ESCAPE in self.just or pygame.K_RETURN in self.just:
                self.state = "title"
        elif self.state == "play":
            self._play(dt)
        elif self.state == "pause":
            self._menu_nav(["Resume", "Substitutions", "Camera", "Rules", "Quit to menu"], self._pause_pick)
        elif self.state == "subs":
            self._sub_input()

    def _menu_nav(self, lines, pick):
        n = len(lines)
        if pygame.K_UP in self.just or pygame.K_w in self.just:
            self.index = (self.index - 1) % n
        if pygame.K_DOWN in self.just or pygame.K_s in self.just:
            self.index = (self.index + 1) % n
        if pygame.K_RETURN in self.just or ("mouse", 1) in self.just:
            pick(self.index)

    def _title_pick(self, i):
        if i == 0:
            self.state = "teams"
            self.index = 0
        elif i == 1:
            self.state = "rules"
            self.rules_scroll = 0
        elif i == 2:
            self.state = "controls"
        else:
            self.running = False

    def _pause_pick(self, i):
        if i == 0:
            self.state = "play"
        elif i == 1:
            self.state = "subs"
            self.index = 0
        elif i == 2 and self.match:
            cur = MODES.index(self.renderer.cam.mode) if self.renderer.cam.mode in MODES else 0
            self.renderer.cam.mode = MODES[(cur + 1) % len(MODES)]
        elif i == 3:
            self.state = "rules"
        else:
            self._to_title()

    def _team_input(self):
        if pygame.K_ESCAPE in self.just:
            self.state = "title"
            return
        if pygame.K_UP in self.just:
            self.index = (self.index - 1) % 6
        if pygame.K_DOWN in self.just:
            self.index = (self.index + 1) % 6
        step = -1 if pygame.K_LEFT in self.just else 1 if pygame.K_RIGHT in self.just else 0
        if step:
            if self.index == 0:
                self.home = (self.home + step) % len(COUNTIES)
                if self.home == self.away:
                    self.away = (self.away + step) % len(COUNTIES)
            elif self.index == 1:
                self.away = (self.away + step) % len(COUNTIES)
                if self.away == self.home:
                    self.home = (self.home + step) % len(COUNTIES)
            elif self.index == 2:
                self.difficulty = (self.difficulty + step) % 3
            elif self.index == 3:
                self.length = (self.length + step) % len(LENGTHS)
            elif self.index == 4:
                self.side = 1 - self.side
        if pygame.K_RETURN in self.just and self.index == 5:
            self._start_match()

    def _start_match(self):
        label, minutes, scale = LENGTHS[self.length]
        diff = ("easy", "medium", "hard")[self.difficulty]
        self.match = Match(
            home=COUNTIES[self.home]["name"],
            away=COUNTIES[self.away]["name"],
            half_minutes=minutes,
            difficulty=diff,
            human_team=self.side,
            time_scale=scale,
            seed=pygame.time.get_ticks() % 10000 or 7,
        )
        self.state = "play"
        self.paused = False
        self.replay_on = False
        self.audio.stop_music()
        self.audio.start_bed()

    def _to_title(self):
        self.state = "title"
        self.index = 0
        self.match = None
        self.audio.stop_bed()
        self.audio.start_music()

    def _play(self, dt):
        match = self.match
        if match is None:
            return
        if pygame.K_ESCAPE in self.just and match.phase not in ("half_time", "full_time", "extra_prompt"):
            self.state = "pause"
            self.index = 0
            return
        keys = pygame.key.get_pressed()
        for i, mode in enumerate(MODES):
            if getattr(pygame, f"K_{i+1}") in self.just:
                self.renderer.cam.mode = mode
        w, h = self.screen.get_size()
        mx, my = pygame.mouse.get_pos()
        self.aim = self.renderer.cam.ground_at(mx, my, w, h)
        self.aim_high = None
        player = match.controlled_player()
        if player:
            bar = self.renderer.cam.project(match.attack_goal_x(player.team), 2.5, 45, w, h)
            if bar:
                self.aim_high = my < bar[1] - 8
        joy = self._joy_move()
        mxv = (keys[pygame.K_d] or keys[pygame.K_RIGHT]) - (keys[pygame.K_a] or keys[pygame.K_LEFT])
        # W / up moves toward the far sideline, which is up the broadcast picture.
        mzv = (keys[pygame.K_w] or keys[pygame.K_UP]) - (keys[pygame.K_s] or keys[pygame.K_DOWN])
        if joy:
            mxv, mzv = joy
        inp = HumanInput(
            move_x=float(mxv),
            move_z=float(mzv),
            sprint=bool(keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]),
            kick_held=bool(keys[pygame.K_SPACE]) or ("mouse", 1) in self.just,
            kick_pressed=pygame.K_SPACE in self.just or ("mouse", 1) in self.just,
            kick_released=False,
            hand=pygame.K_q in self.just or ("mouse", 3) in self.just,
            fist=pygame.K_e in self.just,
            hook=pygame.K_h in self.just,
            solo=pygame.K_f in self.just,
            bounce=pygame.K_r in self.just,
            tackle=pygame.K_x in self.just,
            block=bool(keys[pygame.K_z]),
            sidestep=pygame.K_v in self.just,
            switch=pygame.K_c in self.just or pygame.K_TAB in self.just,
            mark=pygame.K_g in self.just,
            confirm=pygame.K_RETURN in self.just,
            jump=pygame.K_SPACE in self.just,
            to_arc=pygame.K_2 in self.just,
            aim=self.aim,
            aim_high=self.aim_high,
        )
        # Space release: if it was held last frame and is not held now.
        was = getattr(self, "_space", False)
        held = bool(keys[pygame.K_SPACE])
        inp.kick_released = was and not held
        inp.kick_held = held
        if ("mouse", 1) in self.just:
            inp.kick_pressed = True
            inp.kick_released = True
            inp.kick_held = False
        self._space = held
        # Replay overlay during a celebration, then let the match run.
        if match.phase == "celebrate" and match.replay_clip and match.celebrate_t > 0.4:
            self.replay_on = True
            self.replay_i = min(len(match.replay_clip) - 1, self.replay_i + 1)
        else:
            self.replay_on = False
            self.replay_i = 0
        match.update(dt, inp)
        self.renderer.cam.follow(match, dt)
        if match.banner_kind in ("goal", "two"):
            self.renderer.cam.shake = max(self.renderer.cam.shake, 0.35 if match.banner_kind == "goal" else 0.2)
        for name in match.sfx:
            self.audio.play(name)
        if match.ball:
            d = min(abs(match.ball.x), abs(match.ball.x - 145))
            self.audio.set_intensity(1.0 - d / 70.0)
        if match.phase == "full_time" and pygame.K_RETURN in self.just:
            self._to_title()
        if match.phase == "extra_prompt":
            if pygame.K_RETURN in self.just:
                match.request_extra()
            elif pygame.K_ESCAPE in self.just:
                match.decline_extra()

    def _joy_move(self):
        if pygame.joystick.get_count() == 0:
            return None
        try:
            pad = pygame.joystick.Joystick(0)
            if not pad.get_init():
                pad.init()
            x = pad.get_axis(0)
            y = pad.get_axis(1)
            if abs(x) < 0.18 and abs(y) < 0.18:
                return 0.0, 0.0
            return float(x), float(-y)
        except Exception:
            return None

    def _sub_input(self):
        match = self.match
        if match is None or pygame.K_ESCAPE in self.just:
            self.state = "pause"
            return
        side = match.teams[match.human_team]
        on = [p for p in side.players if p.on_pitch and not p.sent_off and not p.in_bin]
        bench = [p for p in side.players if not p.on_pitch and not p.sent_off]
        if pygame.K_UP in self.just:
            self.sub_off = (self.sub_off - 1) % max(1, len(on))
        if pygame.K_DOWN in self.just:
            self.sub_off = (self.sub_off + 1) % max(1, len(on))
        if pygame.K_LEFT in self.just:
            self.sub_on = (self.sub_on - 1) % max(1, len(bench))
        if pygame.K_RIGHT in self.just:
            self.sub_on = (self.sub_on + 1) % max(1, len(bench))
        if pygame.K_RETURN in self.just and on and bench:
            match.substitute(on[self.sub_off % len(on)].pid, bench[self.sub_on % len(bench)].pid)

    def _draw(self):
        match = self.match if self.state in ("play", "pause", "subs") else self.attract
        replay = None
        if self.state == "play" and self.replay_on and self.match and self.match.replay_clip:
            replay = self.match.replay_clip[min(self.replay_i, len(self.match.replay_clip) - 1)]
        show_hud = self.state in ("play", "pause", "subs")
        self.renderer.draw(self.screen, match, self.fonts, replay=replay, hud=show_hud)
        if self.aim and self.state == "play":
            w, h = self.screen.get_size()
            p = self.renderer.cam.project(self.aim[0], 0.12, self.aim[1], w, h)
            if p:
                pygame.draw.circle(self.screen, (255, 214, 90), (int(p[0]), int(p[1])), 10, 2)
        if self.state == "title":
            draw_menu_panel(
                self.screen, self.fonts, "GAELIC FOOTBALL   ·   2026 RULES",
                ["Play match", "Rules of 2026", "Controls", "Quit"],
                self.index, "Not affiliated with the GAA or EA  ·  Windows build",
            )
        elif self.state == "teams":
            self._draw_teams()
        elif self.state == "rules":
            self._draw_text("RULES", RULES_TEXT, self.rules_scroll)
        elif self.state == "controls":
            self._draw_text("CONTROLS", CONTROLS_TEXT, 0)
        elif self.state == "pause":
            draw_menu_panel(
                self.screen, self.fonts, f"PAUSED  ·  camera {self.renderer.cam.mode}",
                ["Resume", "Substitutions", "Camera", "Rules", "Quit to menu"],
                self.index, "M mute    F11 fullscreen",
            )
        elif self.state == "subs":
            self._draw_subs()
        elif self.state == "play" and self.match and self.match.phase in ("half_time", "full_time", "extra_prompt"):
            self._draw_break()

    def _draw_teams(self):
        w, h = self.screen.get_size()
        panel = pygame.Surface((w, h), pygame.SRCALPHA)
        panel.fill((6, 10, 18, 150))
        self.screen.blit(panel, (0, 0))
        self.screen.blit(self.fonts["lg"].render("EXHIBITION AT PEIL PARK", True, (255, 208, 84)), (48, 28))
        rows = [
            f"Home     {COUNTIES[self.home]['name']}",
            f"Away     {COUNTIES[self.away]['name']}",
            f"Level    {('Easy', 'Medium', 'Hard')[self.difficulty]}",
            f"Clock    {LENGTHS[self.length][0]}",
            f"You play {COUNTIES[self.home if self.side == 0 else self.away]['name']}",
            "Start match",
        ]
        y = 120
        for i, row in enumerate(rows):
            col = (255, 208, 90) if i == self.index else (236, 236, 236)
            self.screen.blit(self.fonts["md"].render((">  " if i == self.index else "    ") + row, True, col), (56, y))
            y += 48
        self._kit(80, 460, COUNTIES[self.home])
        self._kit(280, 460, COUNTIES[self.away])
        self.screen.blit(self.fonts["xs"].render("Left / right to change    Enter to start    Esc back", True, (170, 176, 184)), (56, h - 40))

    def _kit(self, x, y, county):
        pygame.draw.rect(self.screen, county["jersey"], (x, y, 70, 84), border_radius=8)
        pygame.draw.rect(self.screen, county["trim"], (x, y + 28, 70, 8))
        pygame.draw.rect(self.screen, county["shorts"], (x + 10, y + 86, 50, 28), border_radius=4)
        label = self.fonts["xs"].render(county["short"], True, (255, 255, 255) if sum(county["jersey"]) < 400 else (20, 20, 20))
        self.screen.blit(label, (x + 35 - label.get_width() / 2, y + 8))

    def _draw_text(self, title, body, scroll):
        w, h = self.screen.get_size()
        shade = pygame.Surface((w, h), pygame.SRCALPHA)
        shade.fill((6, 10, 18, 230))
        self.screen.blit(shade, (0, 0))
        self.screen.blit(self.fonts["lg"].render(title, True, (255, 208, 84)), (48, 24))
        lines = body.splitlines()
        y = 90 - scroll * 22
        for line in lines:
            if -20 < y < h - 20:
                self.screen.blit(self.fonts["sm"].render(line, True, (230, 232, 234)), (48, y))
            y += 22
        self.screen.blit(self.fonts["xs"].render("Esc back    Up / down to scroll", True, (160, 168, 176)), (48, h - 32))

    def _draw_subs(self):
        match = self.match
        if not match or match.human_team is None:
            return
        side = match.teams[match.human_team]
        on = [p for p in side.players if p.on_pitch and not p.sent_off and not p.in_bin]
        bench = [p for p in side.players if not p.on_pitch and not p.sent_off]
        w, h = self.screen.get_size()
        shade = pygame.Surface((w, h), pygame.SRCALPHA)
        shade.fill((6, 10, 18, 210))
        self.screen.blit(shade, (0, 0))
        self.screen.blit(self.fonts["lg"].render(f"SUBS  {side.subs_used}/5", True, (255, 208, 84)), (48, 28))
        self.screen.blit(self.fonts["sm"].render("ON THE PITCH", True, (180, 186, 194)), (48, 100))
        self.screen.blit(self.fonts["sm"].render("BENCH", True, (180, 186, 194)), (420, 100))
        for i, p in enumerate(on):
            col = (255, 208, 90) if i == self.sub_off % max(1, len(on)) else (230, 230, 230)
            self.screen.blit(self.fonts["sm"].render(f"{p.number:2}  {p.first} {p.surname}", True, col), (48, 130 + i * 24))
        for i, p in enumerate(bench):
            col = (255, 208, 90) if i == self.sub_on % max(1, len(bench)) else (230, 230, 230)
            self.screen.blit(self.fonts["sm"].render(f"{p.number:2}  {p.first} {p.surname}", True, col), (420, 130 + i * 24))
        self.screen.blit(self.fonts["xs"].render("Up/down off    Left/right on    Enter to swap    A black card cannot be replaced", True, (160, 168, 176)), (48, h - 36))

    def _draw_break(self):
        match = self.match
        w, h = self.screen.get_size()
        shade = pygame.Surface((w, h), pygame.SRCALPHA)
        shade.fill((6, 10, 18, 170))
        self.screen.blit(shade, (0, 0))
        title = {"half_time": "HALF TIME", "full_time": "FULL TIME", "extra_prompt": "LEVEL  —  EXTRA TIME?"}.get(match.phase, "")
        self.screen.blit(self.fonts["xl"].render(title, True, (255, 208, 84)), (w / 2 - 220, 70))
        y = 180
        for side in match.teams:
            line = f"{side.name}   {side.scoreline()}   ({side.total})    2-pointers {side.two_pointers}    wides {side.wides}"
            self.screen.blit(self.fonts["md"].render(line, True, side.jersey if sum(side.jersey) > 280 else (236, 236, 236)), (w / 2 - 280, y))
            y += 36
        y += 20
        poss = match.teams[0].possession + match.teams[1].possession
        for side in match.teams:
            pct = int(100 * side.possession / poss) if poss else 50
            stat = f"{side.short}  possession {pct}%   tackles {side.tackles}   fouls {side.fouls}   marks {side.marks}   cards {side.yellow}/{side.black}/{side.red}"
            self.screen.blit(self.fonts["sm"].render(stat, True, (220, 224, 228)), (w / 2 - 280, y))
            y += 28
        hint = "Enter for the second half" if match.phase == "half_time" else "Enter extra time    Esc to finish" if match.phase == "extra_prompt" else "Enter for the menu"
        self.screen.blit(self.fonts["sm"].render(hint, True, (255, 208, 90)), (w / 2 - 180, h - 80))
