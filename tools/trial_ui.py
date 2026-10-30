"""Windows for human trial mode: the trial view (pygame, or OpenCV if pygame is missing)
and the network keypad that drives a full-stack world over UDP."""
from __future__ import annotations

import time

import cv2
import numpy as np

from catalog.effects import ring_points
from world import weather as wx

HELP = "arrows/WASD walk  Shift run  C squat  K kneel  N add  Tab switch  R reset  E weather  Z rings  P pause  Q quit"


# --------------------------------------------------------------------------- drawing

def draw_overlay(session, show_rings=True):
    """The camera picture with the top bar, optional zone rings and the plan view."""
    img = session.frame.copy()
    world, cam = session.world, session.world.cam
    if show_rings:
        for buf, colour in ((session.fsm.cfg.warn_buffer_m, (0, 190, 255)), (session.fsm.cfg.alarm_buffer_m, (0, 0, 255))):
            ring = ring_points(world.site, buf, 180)
            uv, z = cam.project(np.hstack([ring, np.zeros((len(ring), 1))]))
            pts = np.round(uv[z > 0]).astype(np.int32)
            cv2.polylines(img, [pts], True, colour, 2, cv2.LINE_AA)
    wid = world.scene.active_controlled
    w = session.worker(wid) if wid is not None else None
    true_d = f"{next((t['edge_m'] for t in session.truth['workers'] if t['id'] == wid), float('nan')):.2f} m" if w else "-"
    app_d = f"{min(session.dist.values()):.2f} m" if session.dist else "-"
    zone_s = max((session.fsm.zone_time(p, session.t) for p in session.fsm.people), default=0.0)
    o = session.outputs
    bar = (f"true {true_d} | app {app_d} | in zone {zone_s:.1f} s | horn {o['horn'] or 'off'} | "
           f"strobe {'ON' if o['strobe'] else 'off'} | laser {'ON' if session.arm.laser_on else 'off'} | "
           f"{world.preset.name}")
    cv2.rectangle(img, (0, 0), (img.shape[1], 30), (0, 0, 0), -1)
    cv2.putText(img, bar, (8, 21), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)
    cv2.putText(img, HELP, (8, img.shape[0] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)
    _plan_view(img, session)
    return img


def _plan_view(img, session, size=(260, 200), scale=9.0):
    """Top-down inset: pole, pit, both rings, workers and the laser beam."""
    w, h = size
    x0, y0 = img.shape[1] - w - 8, 38
    inset = np.full((h, w, 3), 30, np.uint8)
    cx, cy = w / 2, h / 2

    def px(x, y):
        return int(cx + x * scale), int(cy - y * scale)
    site = session.world.site
    for buf, colour in ((session.fsm.cfg.warn_buffer_m, (0, 190, 255)), (session.fsm.cfg.alarm_buffer_m, (0, 0, 255))):
        ring = ring_points(site, buf, 90)
        cv2.polylines(inset, [np.array([px(*p) for p in ring], np.int32)], True, colour, 1, cv2.LINE_AA)
    cv2.fillPoly(inset, [np.array([px(*p) for p in session.pit], np.int32)], (90, 90, 90))
    pole = site["camera"]["xy"]
    cv2.circle(inset, px(*pole), 4, (255, 255, 255), -1)
    a = session.arm_cfg
    d = session.dot()
    if d is not None:
        cv2.line(inset, px(*a["xy"]), px(*d), (60, 255, 60), 1, cv2.LINE_AA)
    for t in session.truth["workers"]:
        colour = (255, 220, 0) if t["id"] == session.world.scene.active_controlled else (200, 200, 200)
        cv2.circle(inset, px(t["x"], t["y"]), 4, colour, -1)
    img[y0:y0 + h, x0:x0 + w] = cv2.addWeighted(img[y0:y0 + h, x0:x0 + w], 0.25, inset, 0.75, 0)


# --------------------------------------------------------------------------- trial window

def run_window(session):
    try:
        import pygame
    except ImportError:
        return _run_window_cv(session)
    pygame.init()
    screen = pygame.display.set_mode((session.world.W, session.world.H))
    pygame.display.set_caption("Danger-zone pole: human trial")
    clock, rings, paused = pygame.time.Clock(), True, False
    session.add_worker()
    while True:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                return
            if ev.type == pygame.KEYDOWN:
                k = ev.key
                if k in (pygame.K_q, pygame.K_ESCAPE):
                    pygame.quit()
                    return
                if k == pygame.K_n:
                    session.add_worker()
                elif k == pygame.K_TAB:
                    session.world.scene.switch_controlled()
                elif k == pygame.K_r:
                    _reset(session)
                elif k == pygame.K_e:
                    _next_weather(session)
                elif k == pygame.K_z:
                    rings = not rings
                elif k == pygame.K_p:
                    paused = not paused
                elif k in (pygame.K_c, pygame.K_k):
                    session.posture("squat" if k == pygame.K_c else "kneel")
        pressed = pygame.key.get_pressed()
        keys = {name for name, codes in (("up", (pygame.K_UP, pygame.K_w)), ("down", (pygame.K_DOWN, pygame.K_s)),
                                         ("left", (pygame.K_LEFT, pygame.K_a)), ("right", (pygame.K_RIGHT, pygame.K_d)))
                if any(pressed[c] for c in codes)}
        run = pressed[pygame.K_LSHIFT] or pressed[pygame.K_RSHIFT]
        if not paused:
            session.step(keys, run)
        img = draw_overlay(session, rings)
        surf = pygame.image.frombuffer(cv2.cvtColor(img, cv2.COLOR_BGR2RGB).tobytes(), (img.shape[1], img.shape[0]), "RGB")
        screen.blit(surf, (0, 0))
        pygame.display.flip()
        clock.tick(1.0 / session.dt)


def _run_window_cv(session):
    """Fallback without pygame. OpenCV reports key presses, not holds, so each press is held 0.25 s."""
    held, rings, paused = {}, True, False
    keymap = {82: "up", 84: "down", 81: "left", 83: "right", ord("w"): "up", ord("s"): "down",
              ord("a"): "left", ord("d"): "right", ord("W"): "up", ord("S"): "down", ord("A"): "left", ord("D"): "right"}
    session.add_worker()
    try:
        while True:
            t0 = time.monotonic()
            k = cv2.waitKeyEx(1) & 0xFFFF if hasattr(cv2, "waitKeyEx") else cv2.waitKey(1)
            low = k & 0xFF
            if low in (ord("q"), 27):
                break
            if (k & 0xFF00) == 0xFF00 or k in (82, 84, 81, 83):
                k = k & 0xFF
            if k in keymap:
                held[keymap[k]] = t0 + 0.25
            elif low == ord("n"):
                session.add_worker()
            elif low == 9:
                session.world.scene.switch_controlled()
            elif low == ord("r"):
                _reset(session)
            elif low == ord("e"):
                _next_weather(session)
            elif low == ord("z"):
                rings = not rings
            elif low == ord("p"):
                paused = not paused
            elif low in (ord("c"), ord("k")):
                session.posture("squat" if low == ord("c") else "kneel")
            keys = {name for name, until in held.items() if until > t0}
            run = any(chr(c).isupper() for c in (k,) if 65 <= c <= 90)
            if not paused:
                session.step(keys, run)
            cv2.imshow("Danger-zone pole: human trial", draw_overlay(session, rings))
            time.sleep(max(0.0, session.dt - (time.monotonic() - t0)))
    except cv2.error:
        raise SystemExit("No window available: install pygame (pip install pygame) or opencv-python with GUI support")
    cv2.destroyAllWindows()


def _reset(session):
    session.world.scene.reset("idle")
    session.fsm.people.clear()
    session.fsm.level = 0
    session.add_worker()


def _next_weather(session):
    names = wx.NAMES
    session.world.set_weather(names[(names.index(session.world.preset.name) + 1) % len(names)])


# --------------------------------------------------------------------------- network keypad

def run_sender(addr):
    """Small keypad window that sends the held keys to a world's control port ~10 times a second."""
    from world.controls import send
    try:
        import pygame
    except ImportError:
        raise SystemExit("--send needs pygame for key-hold detection: pip install pygame")
    pygame.init()
    screen = pygame.display.set_mode((360, 160))
    pygame.display.set_caption(f"Trial keypad -> {addr}")
    font = pygame.font.SysFont(None, 26)
    last = 0.0
    while True:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT or (ev.type == pygame.KEYDOWN and ev.key in (pygame.K_q, pygame.K_ESCAPE)):
                pygame.quit()
                return
            if ev.type == pygame.KEYDOWN:
                cmd = {pygame.K_n: "add_worker", pygame.K_TAB: "switch", pygame.K_r: "reset"}.get(ev.key)
                if cmd:
                    send(addr, {"cmd": cmd})
                elif ev.key in (pygame.K_c, pygame.K_k):
                    send(addr, {"cmd": "posture", "posture": "squat" if ev.key == pygame.K_c else "kneel"})
        pressed = pygame.key.get_pressed()
        keys = [name for name, codes in (("up", (pygame.K_UP, pygame.K_w)), ("down", (pygame.K_DOWN, pygame.K_s)),
                                         ("left", (pygame.K_LEFT, pygame.K_a)), ("right", (pygame.K_RIGHT, pygame.K_d)))
                if any(pressed[c] for c in codes)]
        run = bool(pressed[pygame.K_LSHIFT] or pressed[pygame.K_RSHIFT])
        now = time.monotonic()
        if keys and now - last >= 0.1:
            send(addr, {"cmd": "keys", "keys": keys, "run": run})
            last = now
        screen.fill((25, 25, 25))
        screen.blit(font.render(f"sending to {addr}", True, (200, 200, 200)), (12, 12))
        screen.blit(font.render(f"keys: {' '.join(keys) or '-'}{'  RUN' if run else ''}", True, (255, 220, 0)), (12, 60))
        screen.blit(font.render("N add  Tab switch  R reset  Q quit", True, (160, 160, 160)), (12, 110))
        pygame.display.flip()
        time.sleep(0.02)
