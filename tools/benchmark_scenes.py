#!/usr/bin/env python3
"""Exercise original video through the real renderer and emit reproducible local measurements."""

import argparse
import json
import os
from pathlib import Path
import platform
import statistics
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def hardware_info():
    info = {"platform": platform.platform(), "machine": platform.machine(),
            "python": platform.python_version(), "cpu_count": os.cpu_count()}
    try:
        info["physical_memory_bytes"] = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    except (AttributeError, OSError, ValueError):
        if sys.platform == "win32":
            import ctypes
            class Memory(ctypes.Structure):
                _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong)] + [
                    (name, ctypes.c_ulonglong) for name in ("physical", "available", "page", "available_page", "virtual", "available_virtual", "extended")]
            memory = Memory()
            memory.length = ctypes.sizeof(memory)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory)):
                info["physical_memory_bytes"] = memory.physical
    try:
        info["temperature_c"] = float(Path("/sys/class/thermal/thermal_zone0/temp").read_text()) / 1000
    except (OSError, ValueError):
        pass
    return info


def run(config_path, headless=False, preview=False, output=None):
    if headless:
        os.environ["SDL_VIDEODRIVER"] = "dummy"
        os.environ["SDL_AUDIODRIVER"] = "dummy"
    import pygame
    from config import load_config
    from renderer.renderer import PortraitRenderer
    config = load_config(config_path, demo_mode=True)
    config["renderer"]["scene_director"]["preview"] = preview
    renderer = PortraitRenderer(config)
    director, player = renderer.scene_director, renderer.transition_player
    trace, intervals, durations, work = [], [], [], []
    started, cpu_started = time.monotonic(), time.process_time()
    previous = started
    saved = set()
    snapshots = {}
    out = Path(output) if output else None
    if out:
        out.mkdir(parents=True, exist_ok=True)
    try:
        actions = ["look_up", "return_to_book"] if not preview else [
            "page_flip", "put_away_book", "get_out_tinker_box", "tinker_box_study", "put_away_tinker", "get_out_book"]
        for action in actions:
            if not director.request_action(action):
                raise RuntimeError(f"Could not request {action}")
            action_started = time.monotonic()
            active_seen = False
            while True:
                for event in pygame.event.get():
                    if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                        raise KeyboardInterrupt
                renderer.update_scene()
                renderer.render()
                after = time.monotonic()
                intervals.append(after - previous)
                previous = after
                work.append(renderer.last_render_work_ms)
                if director.error:
                    raise RuntimeError(director.error)
                key = (action, player.current_frame_index)
                if out and player.active_sequence_id == action and player.is_playing and key not in saved and player.current_frame_index in (0, 120, 239):
                    snapshots[f"{action}_{player.current_frame_index:03d}.png"] = renderer.screen.copy()
                    saved.add(key)
                active_seen |= director.active is not None
                if active_seen and director.settled:
                    durations.append({"action": action, "seconds": after - action_started,
                                      "end_scene": director.scene, "last_frame": player.current_frame_index,
                                      "playback": player.last_playback})
                    trace.append({"time": after - started, "scene": director.scene})
                    break
                if after - action_started > 60:
                    raise TimeoutError(f"Action did not finish: {action}")
        report = {"hardware": hardware_info(), "headless": headless,
                  "display": list(renderer.screen.get_size()), "source_fps": 24,
                  "display_fps": renderer.fps, "decode_width": player.max_width,
                  "rgb_budget_bytes": player.memory_bytes, "elapsed_seconds": time.monotonic() - started,
                  "cpu_seconds": time.process_time() - cpu_started, "decoder_wait_events": player.stalls,
                  "preparation_wait_events": player.preparation_waits,
                  "frame_interval_ms_median": statistics.median(intervals) * 1000,
                  "frame_interval_ms_p95": sorted(intervals)[int((len(intervals) - 1) * .95)] * 1000,
                  "render_work_ms_median": statistics.median(work),
                  "actions": durations, "trace": trace,
                  "limitations": "Renderer/video only; speech/camera load and visual approval require the actual Pi."}
        if out:
            # PNG compression is deliberately outside timed playback.
            for name, surface in snapshots.items():
                pygame.image.save(surface, out / name)
            (out / "measurements.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))
        return report
    finally:
        renderer.cleanup()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(Path(__file__).resolve().parents[1] / "portrait_config.json"))
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--preview-cycle", action="store_true")
    parser.add_argument("--output", default=".cache/scene-benchmark")
    args = parser.parse_args()
    run(args.config, args.headless, args.preview_cycle, args.output)


if __name__ == "__main__":
    main()
