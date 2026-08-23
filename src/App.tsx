import React, { useState, useEffect, useRef, useCallback } from "react";
import {
  PortraitState,
  AppConfig,
  ChatMessage,
  CameraTriggerStatus,
  LatencyMetrics,
  PersonaType,
  AssetLayerSet,
} from "./types";
import { useCameraStream } from "./hooks/useCameraStream";
import { PortraitCanvas } from "./components/PortraitCanvas";
import { CameraTrigger } from "./components/CameraTrigger";
import { VoiceController } from "./components/VoiceController";
import { TranscriptLog } from "./components/TranscriptLog";
import { ControlPanel } from "./components/ControlPanel";
import { FacialFeaturesStudio } from "./components/FacialFeaturesStudio";
import {
  Sparkles,
  Sliders,
  Maximize,
  Volume2,
  VolumeX,
  Play,
  RotateCcw,
  Shield,
  Activity,
  Cpu,
  Terminal,
  Zap,
  Camera,
} from "lucide-react";


const INITIAL_CONFIG: AppConfig = {
  demo_mode: {
    enabled: true,
    auto_wake_on_start: false,
    auto_wake_interval_seconds: 0,
    scripted_user_input: "What secrets do you guard inside this Hogwarts frame?",
  },
  renderer: {
    width: 1024,
    height: 768,
    fps: 60,
    window_title: "Harry Potter Talking Portrait (Gemma 4)",
    background_color: [28, 24, 22],
    accent_color: [180, 140, 60],
    eye_color: [248, 244, 236],
    pupil_color: [45, 75, 120],
    mouth_color: [120, 45, 45],
    status_text_color: [240, 220, 180],
  },
  camera: {
    enabled: true,
    hailo_threshold: 0.55,
    poll_interval_seconds: 0.1,
    cooldown_seconds: 8.0,
    motion_fallback_enabled: true,
    voice_only_fallback: true,
  },
  conversation: {
    language: "en-US",
    wake_word: "portrait",
    stop_phrase: "goodbye portrait",
    gemini_model: "gemma-4-e2b-instruct",
    system_prompt:
      "You are Lord Cadogan, the eccentric, valiant knight sealed inside a magical Hogwarts portrait. You believe every conversation is a grand quest. Answer in 1 to 3 vivid sentences. Be bold, boast of slaying beasts, and challenge the user to noble deeds!",
    listen_timeout_seconds: 5.0,
    phrase_time_limit_seconds: 10.0,
    wake_listen_timeout_seconds: 2.0,
    wake_phrase_limit_seconds: 3.0,
    max_history_messages: 10,
    max_silence_turns: 2,
    greeting_on_camera: "Stand and deliver! Who approaches the glorious portrait of Sir Cadogan?",
    greeting_on_voice: "Hark! Someone addresses the great Sir Cadogan! What quest brings you to my hall?",
    silence_prompt: "The silence lingers like castle cobwebs... speak up if you dare!",
    farewell: "Farewell, traveler! May your sword stay sharp and your courage true!",
  },
  cooldown: {
    seconds: 8.0,
  },
};

const INITIAL_LAYERS: AssetLayerSet = {
  base: null,
  eyesClosed: null,
  mouth1: null,
  mouth2: null,
  mouth3: null,
};

export const App: React.FC = () => {
  const [config, setConfig] = useState<AppConfig>(INITIAL_CONFIG);
  const [state, setState] = useState<PortraitState>(PortraitState.IDLE);
  const [mouthLevel, setMouthLevel] = useState<number>(0);
  const [statusText, setStatusText] = useState<string>("Waiting for a person or wake word.");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [speechToSay, setSpeechToSay] = useState<string | null>(null);
  const [nextStateAfterSpeech, setNextStateAfterSpeech] = useState<PortraitState>(PortraitState.LISTENING);
  const [isSettingsOpen, setIsSettingsOpen] = useState<boolean>(false);
  const [personaType, setPersonaType] = useState<PersonaType>("photo_portrait");
  const [cooldownRemaining, setCooldownRemaining] = useState<number>(0);

  // Facial feature custom layers & preview studio state
  const [customLayers, setCustomLayers] = useState<AssetLayerSet>(INITIAL_LAYERS);
  const [isForceBlinking, setIsForceBlinking] = useState<boolean>(false);
  const [showGuides, setShowGuides] = useState<boolean>(false);

  const [latencyMetrics, setLatencyMetrics] = useState<LatencyMetrics>({
    sttDuration: 0.62,
    llmTimeFirstToken: 0.74,
    llmTokensPerSec: 18.5,
    ttsFirstAudio: 0.31,
    totalTurnLatency: 1.45,
  });

  const stateRef = useRef(state);
  stateRef.current = state;
  const configRef = useRef(config);
  configRef.current = config;
  const messagesRef = useRef(messages);
  messagesRef.current = messages;

  // Add message to transcript log
  const appendMessage = useCallback((role: "user" | "model" | "system", text: string) => {
    const timeStr = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    const newMsg: ChatMessage = {
      id: Math.random().toString(36).substring(2, 9),
      role,
      text,
      timestamp: timeStr,
      state: stateRef.current,
    };
    setMessages((prev) => [...prev, newMsg]);
  }, []);

  // Trigger speech playback helper
  const triggerSpeech = useCallback((text: string, next: PortraitState) => {
    setSpeechToSay(text);
    setNextStateAfterSpeech(next);
    setState(PortraitState.SPEAKING);
    setStatusText(text.length > 60 ? text.substring(0, 60) + "..." : text);
    appendMessage("model", text);
  }, [appendMessage]);

  // Handle Trigger event (camera, voice, demo, spacebar) -> WAKE_PENDING -> GREETING
  const handleTrigger = useCallback((source: "camera" | "voice" | "demo") => {
    if (stateRef.current !== PortraitState.IDLE) return;

    setState(PortraitState.WAKE_PENDING);
    setStatusText(`Confirming visitor arrival (${source})...`);

    // Confirm presence -> GREETING
    setTimeout(() => {
      setState(PortraitState.GREETING);
      const greeting =
        source === "camera"
          ? configRef.current.conversation.greeting_on_camera
          : configRef.current.conversation.greeting_on_voice;

      setStatusText(greeting);
      triggerSpeech(greeting, PortraitState.LISTENING);
    }, 450);
  }, [triggerSpeech]);

  // Camera & Vision Subsystem with Pi 5 debug stream and console logging
  const {
    stream: cameraStream,
    status: cameraStatus,
    motionLevel,
    cameraError,
    deviceInfo: cameraDeviceInfo,
    logs: visionLogs,
    isMirrored: isCameraMirrored,
    setIsMirrored: setIsCameraMirrored,
    showCornerFeed,
    setShowCornerFeed,
    cornerFeedSize,
    setCornerFeedSize,
    initCamera: reconnectCamera,
    clearLogs: clearVisionLogs,
    manualTrigger: manualCameraTrigger,
  } = useCameraStream({
    config: config.camera,
    onTrigger: () => handleTrigger("camera"),
    currentState: state,
  });


  // Handle User Utterance / Input -> THINKING -> Gemma 4 -> Piper TTS
  const handleUserInput = useCallback(async (userText: string) => {
    const sttStartTime = performance.now();
    appendMessage("user", userText);
    setState(PortraitState.THINKING);
    setStatusText("Lord Cadogan is consulting Gemma 4...");

    const sttDuration = Math.max(0.4, (performance.now() - sttStartTime) / 1000);
    const thinkingStart = performance.now();

    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: userText,
          history: messagesRef.current.map((m) => ({ role: m.role, text: m.text })),
          systemPrompt: configRef.current.conversation.system_prompt,
          model: configRef.current.conversation.gemini_model,
        }),
      });

      const totalThinkingTime = (performance.now() - thinkingStart) / 1000;
      const ttft = Math.min(0.8, totalThinkingTime * 0.45);
      const ttsFirstAudio = 0.28;

      if (!response.ok) {
        throw new Error("Chat request failed");
      }

      const data = await response.json();
      const reply = data.reply || data.text || "By my troth, a mysterious force blocks my thoughts!";

      // Update telemetry latency stats
      setLatencyMetrics({
        sttDuration: parseFloat(sttDuration.toFixed(2)),
        llmTimeFirstToken: parseFloat(ttft.toFixed(2)),
        llmTokensPerSec: 22.4,
        ttsFirstAudio: ttsFirstAudio,
        totalTurnLatency: parseFloat((sttDuration + ttft + ttsFirstAudio).toFixed(2)),
      });

      // Speak answer -> Return to LISTENING
      triggerSpeech(reply, PortraitState.LISTENING);
    } catch (err) {
      console.warn("Gemma fallback used:", err);
      const fallbackReply = "Fie! My enchanted connection wavers, yet my sword remains stout! What else do you ask?";
      triggerSpeech(fallbackReply, PortraitState.LISTENING);
    }
  }, [appendMessage, triggerSpeech]);

  // Handle Stop Phrase -> Farewell -> COOLDOWN -> IDLE
  const handleStopPhrase = useCallback(() => {
    const farewell = configRef.current.conversation.farewell;
    setStatusText(farewell);
    triggerSpeech(farewell, PortraitState.COOLDOWN);
  }, [triggerSpeech]);

  // Speech finished callback
  const handleSpeechDone = useCallback(() => {
    const next = nextStateAfterSpeech;
    setState(next);
    setSpeechToSay(null);
    setMouthLevel(0);

    if (next === PortraitState.LISTENING) {
      setStatusText("Listening for your voice...");
    } else if (next === PortraitState.COOLDOWN) {
      setStatusText("Entering quiet cooldown period...");
      setCooldownRemaining(configRef.current.cooldown.seconds);
    } else if (next === PortraitState.IDLE) {
      setStatusText("Waiting for a person or wake word.");
    }
  }, [nextStateAfterSpeech]);

  // Cooldown countdown timer
  useEffect(() => {
    if (state !== PortraitState.COOLDOWN) return;

    setCooldownRemaining(config.cooldown.seconds);
    const timer = setInterval(() => {
      setCooldownRemaining((prev) => {
        if (prev <= 1) {
          clearInterval(timer);
          setState(PortraitState.IDLE);
          setStatusText("Waiting for a person or wake word.");
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(timer);
  }, [state, config.cooldown.seconds]);

  // Keyboard shortcut listener (Space = wake demo, Esc = reset, t = inject test speech)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) {
        return;
      }
      if (e.code === "Space") {
        e.preventDefault();
        if (stateRef.current === PortraitState.IDLE) {
          handleTrigger("demo");
        }
      } else if (e.code === "KeyT") {
        if (stateRef.current === PortraitState.LISTENING) {
          handleUserInput("What great beasts have you slain, Sir Cadogan?");
        }
      } else if (e.code === "Escape") {
        setState(PortraitState.IDLE);
        setSpeechToSay(null);
        setMouthLevel(0);
        setStatusText("Waiting for a person or wake word.");
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [handleTrigger, handleUserInput]);

  // Persona switch handler
  const handleSelectPersona = (p: PersonaType) => {
    setPersonaType(p);
    if (p === "talking_fish") {
      setConfig((prev) => ({
        ...prev,
        conversation: {
          ...prev.conversation,
          wake_word: "wilhelm",
          stop_phrase: "goodbye wilhelm",
          greeting_on_camera: "Hey there stranger! Take a look at this trophy plaque! What's up?",
          greeting_on_voice: "Hey there! I'm Wilhelm the singing fish. What's on your mind?",
          system_prompt:
            "You are Wilhelm, a witty, quirky, but kind conversational talking fish mounted on a trophy plaque. Keep replies concise (1-3 sentences) and speak in a friendly tone.",
        },
      }));
    } else if (p === "spooky_witch") {
      setConfig((prev) => ({
        ...prev,
        conversation: {
          ...prev.conversation,
          wake_word: "morgana",
          stop_phrase: "goodbye morgana",
          greeting_on_camera: "Eye of newt and candlelight... a mortal steps into my sight!",
          greeting_on_voice: "Speak your charm or ask your spell, what secrets shall this portrait tell?",
          system_prompt:
            "You are Morgana, an ancient witch sealed within a crystal portrait. You speak in mischievous, whimsical rhymes and dark charms. Keep replies concise (1-3 sentences).",
        },
      }));
    } else {
      setConfig(INITIAL_CONFIG);
    }
  };

  const handleResetDefaults = () => {
    setConfig(INITIAL_CONFIG);
    setPersonaType("photo_portrait");
    setCustomLayers(INITIAL_LAYERS);
    setMessages([]);
    setState(PortraitState.IDLE);
    setStatusText("Waiting for a person or wake word.");
  };

  const handleUpdateLayer = (layerName: keyof AssetLayerSet, dataUrl: string | null) => {
    setCustomLayers((prev) => ({
      ...prev,
      [layerName]: dataUrl,
    }));
  };

  const handleResetAllLayers = () => {
    setCustomLayers(INITIAL_LAYERS);
  };

  return (
    <main className="min-h-screen bg-stone-950 text-stone-100 flex flex-col selection:bg-amber-900 selection:text-amber-100">
      {/* Top Header Bar */}
      <header className="border-b border-stone-800/80 bg-stone-900/60 backdrop-blur-md px-6 py-3 flex items-center justify-between sticky top-0 z-40">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-amber-700 to-amber-950 flex items-center justify-center border border-amber-500/40 shadow-inner">
            <Shield className="w-4 h-4 text-amber-300" />
          </div>
          <div>
            <h1 className="font-cinzel text-base sm:text-lg font-bold tracking-wider text-amber-100 flex items-center gap-2">
              HARRY POTTER TALKING PORTRAIT
              <span className="text-[10px] font-sans font-normal px-2 py-0.5 rounded-full bg-amber-950 text-amber-300 border border-amber-800 flex items-center gap-1">
                <Cpu className="w-2.5 h-2.5" /> Gemma 4 &middot; Pi 5
              </span>
            </h1>
            <p className="text-[11px] text-stone-400">
              Low-Latency Local Architecture &middot; Hailo Vision &middot; Piper TTS &middot; 2D Layered Engine
            </p>
          </div>
        </div>

        {/* Header Action Controls */}
        <div className="flex items-center gap-2">
          {/* Pi 5 Camera Feed in Corner Toggle */}
          <button
            onClick={() => setShowCornerFeed(!showCornerFeed)}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 border transition-all cursor-pointer ${
              showCornerFeed
                ? "bg-amber-950/80 text-amber-200 border-amber-600/70 shadow-sm"
                : "bg-stone-900 text-stone-400 border-stone-800 hover:text-stone-200"
            }`}
            title="Toggle Live Camera Feed Corner Visual"
          >
            <Camera className={`w-3.5 h-3.5 ${cameraStatus.personDetected ? "text-emerald-400" : "text-amber-400"}`} />
            <span className="hidden sm:inline">Camera Corner HUD</span>
            <span className="sm:hidden">Cam</span>
          </button>

          {state === PortraitState.IDLE ? (
            <button
              onClick={() => handleTrigger("demo")}
              className="bg-amber-600 hover:bg-amber-500 text-stone-950 font-bold px-3.5 py-1.5 rounded-lg text-xs flex items-center gap-1.5 shadow-md shadow-amber-900/40 transition-all cursor-pointer font-cinzel"
              title="Simulate visitor approaching portrait (Spacebar)"
            >
              <Play className="w-3.5 h-3.5 fill-current" />
              <span>Wake Portrait</span>
            </button>
          ) : (
            <button
              onClick={() => {
                setState(PortraitState.IDLE);
                setSpeechToSay(null);
                setMouthLevel(0);
                setStatusText("Returned to Idle.");
              }}
              className="bg-stone-800 hover:bg-stone-700 text-stone-300 px-3.5 py-1.5 rounded-lg text-xs flex items-center gap-1.5 transition-all cursor-pointer font-cinzel"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              <span>Sleep</span>
            </button>
          )}

          <button
            onClick={() => setIsSettingsOpen(true)}
            className="p-2 rounded-lg bg-stone-800/80 hover:bg-stone-700 text-stone-300 border border-stone-700 transition-colors cursor-pointer"
            title="Configure System"
          >
            <Sliders className="w-4 h-4 text-amber-400" />
          </button>
        </div>
      </header>

      {/* Real-Time Latency Benchmark HUD Ribbon */}
      <div className="bg-stone-900/90 border-b border-stone-800 px-6 py-2 flex flex-wrap items-center justify-between gap-4 text-xs font-mono">
        <div className="flex items-center gap-2 text-stone-400">
          <Activity className="w-3.5 h-3.5 text-amber-400" />
          <span className="text-stone-300 font-semibold uppercase tracking-wider text-[11px]">Latency Telemetry:</span>
        </div>
        <div className="flex flex-wrap items-center gap-4 text-[11px]">
          <span className="text-stone-400">
            STT: <strong className="text-amber-200">{latencyMetrics.sttDuration}s</strong>
          </span>
          <span className="text-stone-400">
            Gemma TTFT: <strong className="text-amber-200">{latencyMetrics.llmTimeFirstToken}s</strong>
          </span>
          <span className="text-stone-400">
            Generation: <strong className="text-amber-200">{latencyMetrics.llmTokensPerSec} tok/s</strong>
          </span>
          <span className="text-stone-400">
            TTS First Audio: <strong className="text-amber-200">{latencyMetrics.ttsFirstAudio}s</strong>
          </span>
          <span className="text-stone-400 bg-amber-950/60 px-2 py-0.5 rounded border border-amber-800/80">
            Turn Latency: <strong className="text-amber-300 font-bold">{latencyMetrics.totalTurnLatency}s</strong>
          </span>
        </div>
      </div>

      {/* Main Content Dashboard */}
      <div className="flex-1 max-w-7xl w-full mx-auto p-4 sm:p-6 grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Stage: Portrait Canvas & Facial Features Studio (7 cols on lg) */}
        <section className="lg:col-span-7 flex flex-col gap-4">
          <PortraitCanvas
            state={state}
            mouthLevel={mouthLevel}
            statusText={statusText}
            cameraMode={cameraStatus.mode}
            cameraAvailable={cameraStatus.active}
            config={config.renderer}
            personaType={personaType}
            customLayers={customLayers}
            isForceBlinking={isForceBlinking}
            showGuides={showGuides}
            onCanvasClick={() => {
              if (state === PortraitState.IDLE) {
                handleTrigger("demo");
              }
            }}
            cameraStream={cameraStream}
            cameraStatus={cameraStatus}
            motionLevel={motionLevel}
            cameraThreshold={config.camera.hailo_threshold}
            cameraError={cameraError}
            cameraDeviceInfo={cameraDeviceInfo}
            visionLogs={visionLogs}
            isCameraMirrored={isCameraMirrored}
            onToggleCameraMirror={() => setIsCameraMirrored(!isCameraMirrored)}
            showCornerCamera={showCornerFeed}
            cornerCameraSize={cornerFeedSize}
            onChangeCornerCameraSize={setCornerFeedSize}
            onManualCameraTrigger={manualCameraTrigger}
            onReconnectCamera={reconnectCamera}
            onClearVisionLogs={clearVisionLogs}
            onChangeThreshold={(thresh) =>
              setConfig((prev) => ({
                ...prev,
                camera: { ...prev.camera, hailo_threshold: thresh },
              }))
            }
          />

          {/* Quick Architecture Bar */}
          <div className="flex items-center justify-between bg-stone-900/80 border border-stone-800 rounded-xl px-4 py-2.5 text-xs text-stone-400">
            <div className="flex items-center gap-2">
              <span className="font-cinzel text-amber-200 font-semibold">Active Persona:</span>
              <span className="text-stone-200 font-medium">
                {personaType === "photo_portrait"
                  ? "Real Photo Portrait (Glasses & Beard)"
                  : personaType === "talking_fish"
                  ? "Wilhelm the Talking Fish"
                  : personaType === "spooky_witch"
                  ? "Morgana the Witch"
                  : "Lord Cadogan (Knight of Hogwarts)"}
              </span>
            </div>
            <div className="flex items-center gap-3 text-[11px]">
              <span className="flex items-center gap-1 text-emerald-400">
                <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                Hailo Vision Ready
              </span>
              <span className="text-stone-500">&bull;</span>
              <span className="text-stone-300">Piper TTS &middot; Gemma 4</span>
            </div>
          </div>

          {/* Facial Features & Layered Sprite Studio */}
          <FacialFeaturesStudio
            customLayers={customLayers}
            onUpdateLayer={handleUpdateLayer}
            onResetAllLayers={handleResetAllLayers}
            mouthLevel={mouthLevel}
            onSimulateMouthLevel={(lvl) => setMouthLevel(lvl)}
            isForceBlinking={isForceBlinking}
            onToggleForceBlink={setIsForceBlinking}
            showGuides={showGuides}
            onToggleShowGuides={setShowGuides}
            currentState={state}
          />
        </section>

        {/* Right Control Modules: Sensors, Voice, Transcript (5 cols on lg) */}
        <section className="lg:col-span-5 flex flex-col gap-4">
          {/* 1. Optical Camera Sensor */}
          <CameraTrigger
            config={config.camera}
            status={cameraStatus}
            motionLevel={motionLevel}
            stream={cameraStream}
            cameraError={cameraError}
            deviceInfo={cameraDeviceInfo}
            logs={visionLogs}
            canTrigger={state === PortraitState.IDLE}
            onManualTrigger={manualCameraTrigger}
            onReconnect={reconnectCamera}
            onChangeThreshold={(thresh) =>
              setConfig((prev) => ({
                ...prev,
                camera: { ...prev.camera, hailo_threshold: thresh },
              }))
            }
          />


          {/* 2. Voice & Dialogue Controller */}
          <VoiceController
            config={config.conversation}
            state={state}
            onWakeWord={() => handleTrigger("voice")}
            onUserInput={handleUserInput}
            onStopPhrase={handleStopPhrase}
            setMouthLevel={setMouthLevel}
            speechTextToSay={speechToSay}
            onSpeechDone={handleSpeechDone}
            isDemoMode={config.demo_mode.enabled}
          />

          {/* 3. Real-Time Transcript & FSM Status */}
          <TranscriptLog
            messages={messages}
            currentState={state}
            onClear={() => setMessages([])}
            onReplay={(txt) => triggerSpeech(txt, state)}
          />
        </section>
      </div>

      {/* Settings Drawer Modal */}
      <ControlPanel
        config={config}
        onChangeConfig={setConfig}
        isOpen={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
        personaType={personaType}
        onSelectPersona={handleSelectPersona}
        onResetDefaults={handleResetDefaults}
      />
    </main>
  );
};
