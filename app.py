"""Scout AGV teacher app (Phase 2, step 3): live video + head boxes, drive keys, game state, "Student caught".

    .venv\\Scripts\\python.exe app.py --port COM57                 (robot + laptop webcam)
    .venv\\Scripts\\python.exe app.py                              (vision only, no robot)
    .venv\\Scripts\\python.exe app.py --port COM57 --source http://<camera-ip>/stream

Keys (click the window first): R arm, W/A/S/D or arrows drive, 1/2/3 speed, SPACE e-stop,
C = student caught, N = new round, ESC quit.  Mouse: the two buttons on the right.

Safety: the Uno decides (30 % cap, 250 ms deadman, latched e-stop). This app never arms on its own and
sends V from this main loop at 30 Hz. Nothing is recorded; video stays on this laptop.
"""
from __future__ import annotations

import argparse
import sys
import time

import cv2
import numpy as np
import pygame

from game import CAUGHT, DETECTED, SEARCH, TRACKING, Game
from robot_link import RobotLink
from vision import FrameSource, PoseDetector, draw_tracks
from vision.worker import VisionWorker

LOOP_HZ = 30
STALE_S = 0.5                     # video older than this is flagged (and will block auto-tracking)
SPEED_LEVELS = {pygame.K_1: 10, pygame.K_2: 20, pygame.K_3: 30}

VIDEO_W, VIDEO_H = 640, 480
PANEL_X, PANEL_W = VIDEO_W + 20, 300
WIN_W, WIN_H = PANEL_X + PANEL_W + 10, VIDEO_H + 20

BG, FG, DIM = (24, 28, 34), (232, 232, 232), (140, 146, 156)
GREEN, RED, AMBER, BLUE, GREY = (46, 160, 67), (200, 50, 50), (214, 150, 30), (60, 120, 210), (70, 74, 82)
STATE_COLORS = {SEARCH: BLUE, DETECTED: AMBER, TRACKING: GREEN, CAUGHT: (150, 90, 200)}


def to_surface(bgr: np.ndarray) -> pygame.Surface:
    h, w = bgr.shape[:2]
    scale = min(VIDEO_W / w, VIDEO_H / h)
    if scale != 1:
        bgr = cv2.resize(bgr, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA)
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    return pygame.image.frombuffer(rgb.tobytes(), (rgb.shape[1], rgb.shape[0]), "RGB")


class Button:
    def __init__(self, rect: tuple[int, int, int, int], label: str, color: tuple):
        self.rect, self.label, self.color = pygame.Rect(rect), label, color
        self.enabled = True

    def draw(self, screen: pygame.Surface, font: pygame.font.Font) -> None:
        pygame.draw.rect(screen, self.color if self.enabled else GREY, self.rect, border_radius=10)
        text = font.render(self.label, True, FG if self.enabled else DIM)
        screen.blit(text, text.get_rect(center=self.rect.center))

    def hit(self, pos) -> bool:
        return self.enabled and self.rect.collidepoint(pos)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", help="Uno serial port, e.g. COM57. Omit for vision only.")
    ap.add_argument("--source", default="0", help="webcam number or MJPEG URL")
    ap.add_argument("--model", default="models/yolo11n-pose-640.onnx")
    ap.add_argument("--conf", type=float, default=0.40)
    args = ap.parse_args()

    robot = RobotLink(args.port)
    source = FrameSource(args.source).start()
    vision = VisionWorker(source, PoseDetector(args.model, score_threshold=args.conf)).start()
    game = Game()

    pygame.init()
    screen = pygame.display.set_mode((WIN_W, WIN_H))
    pygame.display.set_caption("Scout AGV - teacher")
    font = pygame.font.SysFont("consolas", 16)
    font_big = pygame.font.SysFont("segoeui", 30, bold=True)
    font_btn = pygame.font.SysFont("segoeui", 22, bold=True)

    btn_caught = Button((PANEL_X, 70, PANEL_W, 70), "STUDENT CAUGHT  (C)", GREEN)
    btn_estop = Button((PANEL_X, 150, PANEL_W, 50), "E-STOP  (Space)", RED)

    speed = 10
    video_surface, shown_index = None, -1
    clock = pygame.time.Clock()
    running = True
    try:
        while running:
            now = time.monotonic()
            robot.poll()

            # ------------------------------------------------------------ input
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    running = False
                elif ev.type == pygame.KEYDOWN:
                    if ev.key == pygame.K_ESCAPE:
                        running = False
                    elif ev.key == pygame.K_SPACE:
                        robot.estop()
                    elif ev.key == pygame.K_r:
                        robot.arm()
                    elif ev.key == pygame.K_c:
                        game.catch(now)
                    elif ev.key == pygame.K_n:
                        game.new_round()
                    elif ev.key in SPEED_LEVELS:
                        speed = SPEED_LEVELS[ev.key]
                elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                    if btn_estop.hit(ev.pos):
                        robot.estop()
                    elif btn_caught.hit(ev.pos):
                        game.catch(now)

            # ------------------------------------------------------------ drive (every loop -> feeds deadman)
            keys = pygame.key.get_pressed()
            fwd = (keys[pygame.K_w] or keys[pygame.K_UP]) - (keys[pygame.K_s] or keys[pygame.K_DOWN])
            turn = (keys[pygame.K_d] or keys[pygame.K_RIGHT]) - (keys[pygame.K_a] or keys[pygame.K_LEFT])
            left = max(-1.0, min(1.0, fwd + turn)) * speed
            right = max(-1.0, min(1.0, fwd - turn)) * speed
            robot.drive(left, right)

            # ------------------------------------------------------------ vision + game
            result = vision.latest()
            tracks = result.tracks if result else []
            game.update(tracks, now)
            stale = result is None or result.age > STALE_S

            if result is not None and result.frame_index != shown_index:
                view = result.image.copy()
                draw_tracks(view, tracks, game.caught_ids, game.target_id)
                video_surface, shown_index = to_surface(view), result.frame_index

            # ------------------------------------------------------------ draw
            screen.fill(BG)
            if video_surface is not None:
                screen.blit(video_surface, (10, 10))
            else:
                screen.blit(font.render(f"camera: {source.status}", True, DIM), (20, 20))
            if stale and result is not None:
                pygame.draw.rect(screen, RED, (10, 10, VIDEO_W, 30))
                screen.blit(font.render(f"VIDEO STALE ({result.age:.1f} s old)", True, FG), (20, 16))

            pygame.draw.rect(screen, STATE_COLORS[game.state], (PANEL_X, 10, PANEL_W, 50), border_radius=10)
            label = game.state + ("  (lost?)" if game.target_lost and game.state != CAUGHT else "")
            txt = font_big.render(label, True, FG)
            screen.blit(txt, txt.get_rect(center=(PANEL_X + PANEL_W // 2, 35)))

            btn_caught.enabled = game.can_catch
            btn_caught.draw(screen, font_btn)
            btn_estop.draw(screen, font_btn)

            if robot.port is None:
                link = "robot: not connected (vision only)"
            elif not robot.ready:
                link = f"robot: {robot.problem or 'starting...'}"
            elif not robot.alive:
                link = "robot: NO STATUS from Uno"
            else:
                link = f"robot: {'ARMED' if robot.armed else 'disarmed (press R)'}"
            people = len([t for t in tracks if t.id not in game.caught_ids])
            rows = [
                (link, GREEN if robot.armed and robot.alive else (AMBER if robot.port else DIM)),
                (f"speed level {speed}%   cmd L={left:.0f} R={right:.0f}", FG),
                (f"wheels now L={robot.speed_l} R={robot.speed_r}", FG),
                (f"last: {robot.last_error or robot.last_reply}"[:36], RED if robot.last_error else DIM),
                ("", FG),
                (f"caught this round: {game.caught_count}", FG),
                (f"people in view: {people}", FG),
                (f"vision {result.fps:4.1f} fps  age {result.age * 1000:3.0f} ms" if result else "vision: starting...",
                 RED if stale else DIM),
                ("", FG),
                ("R arm   WASD drive   1/2/3 speed", DIM),
                ("SPACE e-stop   C caught", DIM),
                ("N new round   ESC quit", DIM),
            ]
            for i, (text, color) in enumerate(rows):
                screen.blit(font.render(text, True, color), (PANEL_X, 215 + i * 21))

            if game.state == CAUGHT:
                banner = font_big.render(f"Student caught!  ({game.caught_count})", True, FG)
                box = banner.get_rect(center=(10 + VIDEO_W // 2, 10 + VIDEO_H - 40)).inflate(30, 14)
                pygame.draw.rect(screen, STATE_COLORS[CAUGHT], box, border_radius=10)
                screen.blit(banner, banner.get_rect(center=box.center))

            pygame.display.flip()
            clock.tick(LOOP_HZ)
    finally:
        robot.close()
        vision.stop()
        source.stop()
        pygame.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
