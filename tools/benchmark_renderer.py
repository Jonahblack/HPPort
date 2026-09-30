#!/usr/bin/env python3
"""Profile the shipped native portrait without starting conversation services.

Run on the Pi's display for useful device numbers. --headless uses SDL's dummy
video driver for repeatable development checks, excluding real display costs.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import platform
from pathlib import Path
import statistics
import sys
import time


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


class UnthrottledClock:
    """Exclude the renderer's intentional frame-rate sleep from measurements."""

    def tick(self, _fps: int) -> int:
        return 0


def positive_integer(value: str) -> int:
    result = int(value)
    if result <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return result


def nonnegative_integer(value: str) -> int:
    result = int(value)
    if result < 0:
        raise argparse.ArgumentTypeError("must be zero or greater")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames", type=positive_integer, default=300, help="measured frames (default: 300)")
    parser.add_argument("--warmup", type=nonnegative_integer, default=30, help="unmeasured frames (default: 30)")
    parser.add_argument("--headless", action="store_true", help="use dummy video; excludes real display costs")
    parser.add_argument("--config", type=Path, default=REPO_ROOT / "portrait_config.json", help="portrait configuration file")
    args = parser.parse_args()

    # The renderer initializes SDL audio, but this tool must not acquire a
    # speaker device or start speech, microphone, camera or cloud services.
    os.environ["SDL_AUDIODRIVER"] = "dummy"
    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    if args.headless:
        os.environ["SDL_VIDEODRIVER"] = "dummy"

    import pygame
    from config import load_config
    from renderer.renderer import PortraitRenderer
    from state_machine import PortraitState

    config = load_config(str(args.config))
    renderer_config = config["renderer"]
    renderer_config["show_debug_hud"] = False
    renderer_config["show_camera_pip"] = False
    assets = Path(renderer_config.get("assets_dir", "assets"))
    if not assets.is_absolute():
        renderer_config["assets_dir"] = str(REPO_ROOT / assets)
    config["tts"]["audio_driver"] = "dummy"

    renderer = None
    try:
        renderer = PortraitRenderer(config)
        renderer.clock = UnthrottledClock()
        renderer.set_state(PortraitState.SPEAKING)
        renderer.set_subtitle("Welcome, traveller. Tell me what brings you to this enchanted portrait today.")
        samples = []
        for frame in range(args.warmup + args.frames):
            for event in pygame.event.get():
                if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                    raise KeyboardInterrupt
            renderer.set_audio_amplitude((frame % 3) * 0.35)
            started = time.perf_counter()
            renderer.render()
            elapsed_ms = (time.perf_counter() - started) * 1000
            if frame >= args.warmup:
                samples.append(elapsed_ms)

        ordered = sorted(samples)
        print(json.dumps({
            "platform": platform.platform(),
            "architecture": platform.machine(),
            "python": platform.python_version(),
            "pygame": pygame.version.ver,
            "sdl": ".".join(map(str, pygame.get_sdl_version())),
            "video_driver": pygame.display.get_driver(),
            "headless": pygame.display.get_driver() == "dummy",
            "resolution": list(renderer.screen.get_size()),
            "config": str(args.config.resolve()),
            "asset_mode": renderer.asset_mode,
            "base_sprite_loaded": renderer.sprites.get("base") is not None,
            "ambient_motes": renderer.ambient_motes,
            "camera_motion": renderer.camera_motion,
            "warmup_frames": args.warmup,
            "measured_frames": len(samples),
            "configured_fps": renderer.fps,
            "unthrottled": True,
            "median_ms": round(statistics.median(samples), 3),
            "p95_ms": round(ordered[math.ceil(len(ordered) * 0.95) - 1], 3),
            "mean_ms": round(statistics.mean(samples), 3),
            "max_ms": round(max(samples), 3),
            "scope": "render() including display.flip; excludes startup, frame limiter and all conversation services",
        }, indent=2))
    finally:
        if renderer is not None:
            renderer.cleanup()
        else:
            pygame.quit()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Renderer benchmark cancelled.", file=sys.stderr)
        raise SystemExit(130)
