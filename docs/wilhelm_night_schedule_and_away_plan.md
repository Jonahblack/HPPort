# Wilhelm: Night Schedule and Away Behavior Plan

## 1. Overview & Objective

Wilhelm’s portrait is designed to feel alive within the physical world. Rather than remaining seated at his desk 24/7, Wilhelm follows a natural diurnal rhythm:
- **Daytime:** Dwells at his desk, alternating between reading his book and tinkering with his puzzle box, acknowledging approaching visitors immediately with gaze and full-length transition footage.
- **Nighttime:** Closes and packs away any active props (`put_away_book` / `put_away_tinker`), stands up, and leaves the room (`walk_away`), leaving the portrait as an unoccupied workshop (`empty_room.png`).
- **Summoned While Away:** If a visitor needs Wilhelm at night, calling for him initiates his return (`walk_in`). The visitor watches Wilhelm enter the room, approach the desk, and take a seat before conversation begins.
- **Overnight Post-Conversation Dwell:** After an overnight conversation settles, if it is still nighttime, Wilhelm waits for a brief, configurable period (e.g., 90 seconds). If no further questions are asked, he stands up and walks away again.
- **Morning Arrival:** At sunrise / morning schedule, Wilhelm returns to his study (`walk_in`), retrieves his book, and resumes his daytime routine.

---

## 2. Updated Scene Graph

```mermaid
flowchart TD
    subgraph Daytime Activities
        R[Reading] <-->|put_away_book / get_out_book| N[Neutral Desk]
        N <-->|get_out_tinker_box / put_away_tinker| T[Tinkering]
    end

    subgraph Visitor Engagement
        R <-->|look_up / return_to_book| EB[Engaged with Book]
        T <-->|look_up_from_tinker_box / return_to_tinker| ET[Engaged with Tinker Box]
        N <-->|Seated Greeting / Post-Converse Return| N
    end

    subgraph Away & Overnight Cycle
        N -->|walk_away| A[Away: Empty Room]
        A -->|walk_in (Summon or Morning)| N
    end
```

### Visual Continuity Verification

| Transition Clip | Source FPS / Duration | Entry Point | Exit Point | Seam Continuity Analysis |
| :--- | :--- | :--- | :--- | :--- |
| `walk_away.mp4` | 24 FPS / 10.0s (240f) | `neutral` desk | `away` (`empty_room`) | Starts from clean seated desk (diff 4.06px vs `get_out_tinker_box`). Ends with unoccupied room: **0.0px exact match** with `empty_room.png`. |
| `walk_in.mp4` | 24 FPS / 10.0s (240f) | `away` (`empty_room`) | `neutral` desk | Starts with unoccupied room (diff 3.88px vs `empty_room.png`). Ends with Wilhelm seated at desk: **3.22px diff** against `walk_away.mp4` start frame. |
| `empty_room.png` | 1280 x 720 still | `away` fallback | `away` fallback | Held surface during absence; replaces character sprites while Wilhelm is away. |

---

## 3. Expected Behavioral Lifecycle

### 3.1 Evening Departure (Entering Night Mode)
1. **Trigger:** The clock enters `night_start_hour` (default: 22:00 / 10:00 PM).
2. **Graceful Activity Wind-Down:**
   - If Wilhelm is actively reading: plays `put_away_book` to reach `neutral`.
   - If Wilhelm is tinkering: plays `put_away_tinker` to reach `neutral`.
   - If Wilhelm is engaged with a visitor: departure is postponed until the conversation completes and cooldown expires.
3. **Departure:** From `neutral`, `walk_away` plays at 24 FPS. Wilhelm stands up from the chair and walks out of frame.
4. **Resting Away State:** Once `walk_away` completes, scene commits to `away`. The renderer displays `empty_room.png`. Micro-saccades, blinks, and desk gaze tracking are suspended.

---

### 3.2 Summoning Wilhelm While Away
1. **Visitor Trigger:** The visitor speaks to summon Wilhelm (e.g. *"Wilhelm!"*, *"Where are you?"*, or pressing the wake trigger).
2. **Paced Return:**
   - Scene Director routes `away` $\rightarrow$ `neutral` via `walk_in`.
   - `walk_in` plays at 24 FPS for 10 seconds.
   - The user observes Wilhelm enter the room, walk to his chair, and sit down.
3. **Visual Readiness Gating:**
   - Speech synthesis begins preparing in the background during `walk_in`.
   - Audio playback is strictly gated: Wilhelm will **not** start speaking while walking or sitting down. Greeting audio begins only once `walk_in` frame 239 settles and eye contact is established.
4. **Conversation:** Multi-turn dialogue proceeds normally with Piper TTS / Gemini streaming.

---

### 3.3 Post-Conversation Overnight Dwell & Re-Departure
1. **Cooldown Settling:** When dialogue finishes, the FSM enters `COOLDOWN` then `IDLE`.
2. **Night Dwell Window:**
   - Because it is still night hours, Wilhelm remains seated at `neutral` for `night_post_conversation_dwell_seconds` (default: 90 seconds).
   - If the visitor speaks again during this window, Wilhelm responds immediately without needing to walk in again.
3. **Re-Departure:**
   - Once the dwell timer expires with no visitor activity, Wilhelm stands up and plays `walk_away`.
   - The portrait returns to `away` (`empty_room.png`).

---

### 3.4 Morning Return
1. **Trigger:** The clock enters `night_end_hour` (default: 07:00 / 7:00 AM).
2. **Return Sequence:**
   - `walk_in` plays to bring Wilhelm back to the desk.
   - Upon sitting down at `neutral`, he retrieves his book via `get_out_book` to reach `reading`.
3. **Daytime Resumed:** Normal autonomous scheduling (page turns every 30–65s, activity switches every 180–420s) resumes.

---

## 4. Configuration Schema

Configured in `portrait_config.json` under `renderer.scene_director.schedule`:

```json
{
  "scene_director": {
    "schedule": {
      "enabled": false,
      "night_start_hour": 22,
      "night_end_hour": 7,
      "night_post_conversation_dwell_seconds": 90,
      "summon_keywords": [
        "wilhelm",
        "wake up",
        "are you there",
        "hello",
        "where are you"
      ]
    }
  }
}
```

---

## 5. Questions for Review

Please review the following design decisions and let me know your preferences:

1. **Wake Trigger While Away at Night:**
   - *Option A (Recommended):* Require vocal summon (e.g. saying *"Wilhelm"* or speaking into the mic) or manual wake key. Passive camera motion alone does not summon him at night, preventing room shadows or pets from triggering a 10-second walk-in.
   - *Option B:* Allow any camera motion to wake him at night, identical to daytime.

2. **Night Dwell Duration:**
   - Is **90 seconds** an appropriate duration for Wilhelm to remain seated at his desk after an overnight conversation before standing up and walking away again, or would you prefer a shorter (e.g. 45s) or longer (e.g. 2–3 min) dwell?

3. **Speaking Pose at Night:**
   - When summoned from `away`, Wilhelm currently sits down at `neutral` (clean desk facing forward) and speaks directly from the desk. Is speaking from the clean desk preferred, or should he always pull out a book (`get_out_book`) before conversing?

4. **Time & Schedule Source:**
   - Should the night schedule use the Pi's local system wall clock (24-hour time), or would you eventually like an external light sensor / override command?
