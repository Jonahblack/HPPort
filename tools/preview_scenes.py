#!/usr/bin/env python3
"""Preview compatible clip routes without camera, microphone, models, or speech."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pygame
from config import load_config
from renderer.renderer import PortraitRenderer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(Path(__file__).resolve().parents[1] / "portrait_config.json"))
    parser.add_argument("--fullscreen", action="store_true")
    parser.add_argument("--cycle", action="store_true", help="Preview the complete reading/tinkering cycle")
    args = parser.parse_args()
    config = load_config(args.config, demo_mode=True)
    config["renderer"].setdefault("scene_director", {})["enabled"] = True
    config["renderer"]["scene_director"]["preview"] = True
    config["renderer"]["fullscreen"] = args.fullscreen
    renderer = PortraitRenderer(config)
    ids = ("page_flip", "tinker_box_study", "get_out_book", "get_out_tinker_box",
           "look_up", "return_to_book", "put_away_book", "put_away_tinker")
    cycle = iter(("page_flip", "put_away_book", "get_out_tinker_box", "tinker_box_study",
                  "put_away_tinker", "get_out_book")) if args.cycle else iter(())
    pending = next(cycle, None)
    running = True
    try:
        print("1-8 select actions; compatible entry routes play first. I: diagnostics, Esc: quit.")
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key in (pygame.K_ESCAPE, pygame.K_q)):
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if pygame.K_1 <= event.key <= pygame.K_8:
                        pending = None
                        renderer.trigger_animation(ids[event.key - pygame.K_1])
                    elif event.key == pygame.K_i:
                        renderer.toggle_anim_debug_hud()
            if not running:
                break
            renderer.scene_director.update(idle=False)
            if pending and renderer.scene_director.settled:
                if renderer.trigger_animation(pending):
                    pending = next(cycle, None)
            renderer.set_subtitle("Asset preview: no visitor interaction or speech")
            renderer.render()
    finally:
        renderer.cleanup()


if __name__ == "__main__":
    main()
