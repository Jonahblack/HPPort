import express, { Request, Response } from "express";
import path from "path";
import cors from "cors";
import dotenv from "dotenv";
import { createServer as createViteServer } from "vite";
import { GoogleGenAI } from "@google/genai";

dotenv.config();

const app = express();
const PORT = 3000;

app.use(cors());
app.use(express.json());

// In-memory runtime configuration store matching portrait_config.json defaults
let currentConfig = {
  demo_mode: {
    enabled: false,
    auto_wake_on_start: true,
    auto_wake_interval_seconds: 0,
    scripted_user_input: "Tell me a short spooky greeting.",
  },
  renderer: {
    width: 800,
    height: 480,
    fps: 30,
    window_title: "Talking Portrait",
    background_color: [18, 21, 28],
    accent_color: [198, 134, 73],
    eye_color: [248, 244, 236],
    pupil_color: [32, 28, 27],
    mouth_color: [126, 48, 43],
    status_text_color: [232, 228, 220],
  },
  camera: {
    enabled: true,
    hailo_threshold: 0.55,
    poll_interval_seconds: 0.12,
    cooldown_seconds: 15.0,
    motion_fallback_enabled: true,
    voice_only_fallback: true,
  },
  conversation: {
    language: "en-US",
    wake_word: "portrait",
    stop_phrase: "goodbye portrait",
    gemini_model: "gemini-2.5-flash",
    system_prompt:
      "You are a haunted talking portrait mounted on a wall in an ancient Victorian manor. You are warm, playful, witty, and slightly eerie/uncanny. Keep replies concise (1 to 3 short spoken sentences) and engaging.",
    listen_timeout_seconds: 7.0,
    phrase_time_limit_seconds: 7.0,
    wake_listen_timeout_seconds: 1.0,
    wake_phrase_limit_seconds: 2.0,
    max_history_messages: 8,
    max_silence_turns: 2,
    greeting_on_camera: "Hello there... I saw you approach the gallery. What whispers do you bring?",
    greeting_on_voice: "Ah, someone speaks to the frame! I am listening.",
    silence_prompt: "The silence lingers like cobwebs... speak up if you dare.",
    farewell: "Very well. Rest until the midnight hour calls again.",
  },
  cooldown: {
    seconds: 10.0,
  },
};

// Preset personas
export const PERSONA_PRESETS: Record<string, { system_prompt: string; wake_word: string; stop_phrase: string; greeting_on_camera: string; greeting_on_voice: string }> = {
  haunted_portrait: {
    system_prompt: "You are Lord Alistair, a haunted talking portrait mounted on a wall in an ancient Victorian manor. You are warm, playful, witty, and slightly eerie/uncanny. Keep replies concise (1 to 3 short spoken sentences) and engaging.",
    wake_word: "portrait",
    stop_phrase: "goodbye portrait",
    greeting_on_camera: "Hello there... I saw you approach the gallery. What whispers do you bring?",
    greeting_on_voice: "Ah, someone speaks to the frame! I am listening.",
  },
  talking_fish: {
    system_prompt: "You are Wilhelm, a witty, quirky, but kind conversational talking fish mounted on a trophy plaque. Keep replies concise (1-3 sentences) and speak in a friendly tone.",
    wake_word: "wilhelm",
    stop_phrase: "goodbye wilhelm",
    greeting_on_camera: "Hey there stranger! Take a look at this trophy wall! What's up?",
    greeting_on_voice: "Hey there! I'm Wilhelm the singing fish. What's on your mind?",
  },
  spooky_witch: {
    system_prompt: "You are Morgana, an ancient witch sealed within a crystal portrait. You speak in mischievous, whimsical rhymes and dark charms. Keep replies concise (1-3 sentences).",
    wake_word: "morgana",
    stop_phrase: "goodbye morgana",
    greeting_on_camera: "Eye of newt and candlelight... a mortal steps into my sight!",
    greeting_on_voice: "Speak your charm or ask your spell, what secrets shall this portrait tell?",
  },
};

// Lazy GenAI client
let genAIInstance: GoogleGenAI | null = null;
function getGenAI(): GoogleGenAI | null {
  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) return null;
  if (!genAIInstance) {
    genAIInstance = new GoogleGenAI({ apiKey });
  }
  return genAIInstance;
}

// API Routes
app.get("/api/health", (_req: Request, res: Response) => {
  res.json({
    status: "ok",
    hasApiKey: !!process.env.GEMINI_API_KEY,
    timestamp: new Date().toISOString(),
  });
});

app.get("/api/config", (_req: Request, res: Response) => {
  res.json({
    config: currentConfig,
    presets: PERSONA_PRESETS,
    hasApiKey: !!process.env.GEMINI_API_KEY,
  });
});

app.post("/api/config", (req: Request, res: Response) => {
  if (req.body && typeof req.body === "object") {
    currentConfig = {
      ...currentConfig,
      ...req.body,
      conversation: {
        ...currentConfig.conversation,
        ...(req.body.conversation || {}),
      },
      renderer: {
        ...currentConfig.renderer,
        ...(req.body.renderer || {}),
      },
      camera: {
        ...currentConfig.camera,
        ...(req.body.camera || {}),
      },
    };
  }
  res.json({ success: true, config: currentConfig });
});

app.post("/api/chat", async (req: Request, res: Response) => {
  const { message, history = [], systemPrompt, model } = req.body;

  if (!message || typeof message !== "string") {
    return res.status(400).json({ error: "Message is required" });
  }

  const apiKey = process.env.GEMINI_API_KEY;
  const ai = getGenAI();

  const chosenModel = model || currentConfig.conversation.gemini_model || "gemini-2.5-flash";
  const chosenPrompt =
    systemPrompt || currentConfig.conversation.system_prompt || "You are a haunted talking portrait.";

  // If Gemini API is configured, use real Gemini SDK
  if (ai && apiKey) {
    try {
      // Build contents array
      const contents: Array<{ role: string; parts: Array<{ text: string }> }> = [];

      // Add recent history
      if (Array.isArray(history)) {
        const recent = history.slice(-6);
        for (const item of recent) {
          if (item && item.role && item.text) {
            contents.push({
              role: item.role === "user" ? "user" : "model",
              parts: [{ text: item.text }],
            });
          }
        }
      }

      contents.push({
        role: "user",
        parts: [{ text: message }],
      });

      const response = await ai.models.generateContent({
        model: chosenModel,
        contents: contents,
        config: {
          systemInstruction: chosenPrompt,
          temperature: 0.85,
          maxOutputTokens: 250,
        },
      });

      const replyText = response.text?.trim() || "The spirits in the portrait murmur softly...";
      return res.json({
        reply: replyText,
        source: "gemini",
        model: chosenModel,
      });
    } catch (err: any) {
      console.error("Gemini API call failed:", err?.message || err);
      // Fallback with uncanny personality if rate-limited or transient network error
      const fallbackReplies = [
        "A cold chill sweeps through the hall. The spirits hear you clearly, mortal.",
        "The oil on my canvas ripples with curiosity. Tell me more of the outside realm.",
        "Centuries have passed since anyone spoke with such curiosity. I am listening closely.",
        "A shadow flickers across the frame. What strange questions mortals ask these days!",
      ];
      const randomFallback = fallbackReplies[Math.floor(Math.random() * fallbackReplies.length)];
      return res.json({
        reply: randomFallback,
        source: "fallback",
        note: "API returned error: " + (err?.message || "Check GEMINI_API_KEY in settings"),
      });
    }
  }

  // Graceful offline fallback simulation when GEMINI_API_KEY is not configured yet
  const simulatedReplies: Record<string, string> = {
    hello: "Greetings, traveler of the living realm. What brings your footsteps to my corridor?",
    spooky: "The clock strikes the witching hour, and the shadows dance across my gilded frame...",
    joke: "Why don't skeletons fight each other? They simply don't have the guts!",
    secret: "The walls of this manor keep many secrets, but few are as ancient as the ghost behind my painted eyes.",
  };

  const lower = message.toLowerCase();
  let selected = "The portrait's eyes follow you intently. (Set GEMINI_API_KEY in environment for full generative AI dialogues!)";

  for (const [k, v] of Object.entries(simulatedReplies)) {
    if (lower.includes(k)) {
      selected = v;
      break;
    }
  }

  return res.json({
    reply: selected,
    source: "simulation",
    note: "Add GEMINI_API_KEY in Settings to enable real-time Gemini responses.",
  });
});

async function startServer() {
  if (process.env.NODE_ENV !== "production") {
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: "spa",
    });
    app.use(vite.middlewares);
  } else {
    const distPath = path.join(process.cwd(), "dist");
    app.use(express.static(distPath));
    app.get("*", (_req, res) => {
      res.sendFile(path.join(distPath, "index.html"));
    });
  }

  app.listen(PORT, "0.0.0.0", () => {
    console.log(`[TalkingPortrait] Server running on http://0.0.0.0:${PORT}`);
  });
}

startServer();
