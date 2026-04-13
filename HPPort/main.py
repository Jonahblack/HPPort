import argparse
import time

from camera_trigger import PersonTriggerService
from config import load_config
from conversation import ConversationManager
from renderer import PortraitRenderer
from state_machine import PortraitState, PortraitStateMachine


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Talking portrait for Raspberry Pi 5")
    parser.add_argument("--config", default=None, help="Path to portrait JSON config")
    parser.add_argument("--demo", action="store_true", help="Enable demo mode without camera")
    return parser


def main() -> None:
    args = build_argument_parser().parse_args()
    app_config = load_config(args.config)
    if args.demo:
        app_config.raw["demo_mode"]["enabled"] = True
        app_config.raw["camera"]["enabled"] = False

    renderer = PortraitRenderer(app_config.raw["renderer"])
    conversation = ConversationManager(app_config)
    camera_service = PersonTriggerService(app_config.raw["camera"], root_dir=app_config.root_dir)
    fsm = PortraitStateMachine()

    renderer.start()
    if not app_config.demo_mode:
        camera_service.start()

    try:
        try:
            conversation.prime_microphone()
        except Exception:
            pass

        silence_turns = 0
        pending_reply = ""
        pending_user_text = ""
        cooldown_started = 0.0
        demo_auto_fired = False
        demo_interval = float(app_config.raw["demo_mode"].get("auto_wake_interval_seconds", 0))
        last_demo_wake = time.monotonic()

        while not renderer.quit_requested():
            camera_status = camera_service.status
            renderer.update(
                fsm.state,
                camera_mode=camera_status.mode,
                camera_available=camera_status.available,
            )

            if fsm.state == PortraitState.IDLE:
                renderer.update(PortraitState.IDLE, mouth_level=0.0, status_text="Waiting for a person or wake word.")
                trigger_reason = None

                if app_config.demo_mode and app_config.raw["demo_mode"].get("auto_wake_on_start", True) and not demo_auto_fired:
                    trigger_reason = "demo"
                    demo_auto_fired = True
                elif app_config.demo_mode and demo_interval > 0 and time.monotonic() - last_demo_wake >= demo_interval:
                    trigger_reason = "demo"
                    last_demo_wake = time.monotonic()
                elif renderer.consume_demo_trigger():
                    trigger_reason = "demo"
                    last_demo_wake = time.monotonic()
                elif camera_service.consume_trigger():
                    trigger_reason = "camera"
                else:
                    try:
                        if conversation.detect_wake_word_once():
                            trigger_reason = "voice"
                    except Exception:
                        trigger_reason = None

                if trigger_reason:
                    fsm.transition(PortraitState.WAKE_PENDING, reason=trigger_reason)
                    silence_turns = 0
                    continue

                time.sleep(0.05)
                continue

            if fsm.state == PortraitState.WAKE_PENDING:
                reason = fsm.get("reason", "voice")
                greeting = conversation.greet_text(reason)
                renderer.update(PortraitState.WAKE_PENDING, status_text=f"Wake triggered by {reason}.")
                fsm.transition(PortraitState.SPEAKING, phase="greeting", next_state=PortraitState.LISTENING, speech_text=greeting)
                continue

            if fsm.state == PortraitState.LISTENING:
                renderer.update(PortraitState.LISTENING, mouth_level=0.0, status_text="Listening...")
                user_text = None
                if app_config.demo_mode:
                    user_text = str(app_config.raw["demo_mode"].get("scripted_user_input", "Tell me a spooky joke.")).strip()
                    time.sleep(0.6)
                else:
                    try:
                        user_text = conversation.listen_once()
                    except Exception:
                        user_text = None

                if not user_text:
                    silence_turns += 1
                    if silence_turns >= app_config.max_silence_turns:
                        fsm.transition(PortraitState.COOLDOWN)
                        cooldown_started = time.monotonic()
                        continue
                    prompt = app_config.raw["conversation"]["silence_prompt"]
                    fsm.transition(PortraitState.SPEAKING, phase="reprompt", next_state=PortraitState.LISTENING, speech_text=prompt)
                    continue

                if conversation.is_stop_phrase(user_text):
                    farewell = app_config.raw["conversation"]["farewell"]
                    fsm.transition(PortraitState.SPEAKING, phase="farewell", next_state=PortraitState.COOLDOWN, speech_text=farewell)
                    cooldown_started = time.monotonic()
                    continue

                pending_user_text = user_text
                silence_turns = 0
                fsm.transition(PortraitState.THINKING)
                continue

            if fsm.state == PortraitState.THINKING:
                renderer.update(PortraitState.THINKING, mouth_level=0.0, status_text="Thinking...")
                try:
                    pending_reply = conversation.generate_reply(pending_user_text)
                except Exception as exc:
                    pending_reply = (
                        "I ran into a problem reaching my voice or language service. "
                        "Please check the API keys and network connection."
                    )
                    renderer.update(PortraitState.THINKING, status_text=str(exc))
                if not pending_reply:
                    pending_reply = "I do not have a reply just yet. Please try asking again."
                fsm.transition(PortraitState.SPEAKING, phase="reply", next_state=PortraitState.LISTENING, speech_text=pending_reply)
                continue

            if fsm.state == PortraitState.SPEAKING:
                text = fsm.get("speech_text", "")
                next_state = fsm.get("next_state", PortraitState.LISTENING)
                renderer.update(PortraitState.SPEAKING, status_text=text[:72])
                try:
                    conversation.say(text, on_level=lambda level: renderer.update(PortraitState.SPEAKING, mouth_level=level))
                except Exception:
                    renderer.update(PortraitState.SPEAKING, mouth_level=0.7)
                    time.sleep(min(max(len(text) * 0.04, 1.5), 4.0))
                    renderer.update(PortraitState.SPEAKING, mouth_level=0.0)

                if next_state == PortraitState.COOLDOWN:
                    cooldown_started = time.monotonic()
                    fsm.transition(PortraitState.COOLDOWN)
                else:
                    fsm.transition(next_state)
                continue

            if fsm.state == PortraitState.COOLDOWN:
                renderer.update(PortraitState.COOLDOWN, mouth_level=0.0, status_text="Cooling down...")
                if cooldown_started == 0.0:
                    cooldown_started = time.monotonic()
                if time.monotonic() - cooldown_started >= app_config.cooldown_seconds:
                    cooldown_started = 0.0
                    conversation.reset_history()
                    fsm.transition(PortraitState.IDLE)
                else:
                    time.sleep(0.1)
    finally:
        camera_service.stop()
        conversation.close()
        renderer.stop()


if __name__ == "__main__":
    main()
