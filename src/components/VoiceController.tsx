import React, { useEffect, useRef, useState } from "react";
import { ConversationConfig, PortraitState } from "../types";
import { Mic, Send, AlertCircle } from "lucide-react";

interface VoiceControllerProps {
  config: ConversationConfig;
  state: PortraitState;
  onWakeWord: () => void;
  onUserInput: (text: string) => void;
  onStopPhrase: () => void;
  setMouthLevel: (level: number) => void;
  speechTextToSay: string | null;
  onSpeechDone: () => void;
  onSpeechStart: (delaySeconds: number) => void;
  isDemoMode: boolean;
}

export const VoiceController: React.FC<VoiceControllerProps> = ({
  config,
  state,
  onWakeWord,
  onUserInput,
  onStopPhrase,
  setMouthLevel,
  speechTextToSay,
  onSpeechDone,
  onSpeechStart,
  isDemoMode,
}) => {
  const [manualText, setManualText] = useState("");
  const [isMicListening, setIsMicListening] = useState(false);
  const [sttSupported, setSttSupported] = useState(true);
  const [micError, setMicError] = useState("");
  const mouthAnimRef = useRef<number | null>(null);
  const selectedVoiceRef = useRef<SpeechSynthesisVoice | null>(null);
  const callbacksRef = useRef({ config, state, onWakeWord, onUserInput, onStopPhrase, setMouthLevel, onSpeechDone, onSpeechStart });
  callbacksRef.current = { config, state, onWakeWord, onUserInput, onStopPhrase, setMouthLevel, onSpeechDone, onSpeechStart };
  const listeningEnabled = !isDemoMode && (state === PortraitState.IDLE || state === PortraitState.LISTENING);

  // A recognition instance owns its restart timer. Cleanup disables its handlers
  // before abort(), whose asynchronous onend must never restart a stale mic.
  useEffect(() => {
    const SpeechRecognition =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;

    if (!SpeechRecognition) {
      setSttSupported(false);
      return;
    }

    if (!listeningEnabled) return;
    let disposed = false;
    let handled = false;
    let blocked = false;
    let restartTimer: ReturnType<typeof setTimeout> | undefined;
    let recognition: any;
    try {
      recognition = new SpeechRecognition();
    } catch (error) {
      console.warn("Could not initialize microphone:", error);
      setSttSupported(false);
      return;
    }
    const start = () => {
      if (disposed || handled || blocked) return;
      try {
        recognition.start();
      } catch (error) {
        console.warn("Could not start microphone:", error);
      }
    };
    try {
      recognition.continuous = true;
      recognition.interimResults = true;
      recognition.lang = config.language || "en-US";

      recognition.onresult = (event: any) => {
        if (disposed || handled) return;
        const current = callbacksRef.current;
        let transcript = "";
        let finalTranscript = "";
        for (let i = event.resultIndex; i < event.results.length; ++i) {
          transcript += event.results[i][0].transcript;
          if (event.results[i].isFinal) finalTranscript += event.results[i][0].transcript;
        }
        const normalized = transcript.trim().toLowerCase();

        // 1. Wake word spotting while IDLE
        if (current.state === PortraitState.IDLE) {
          const wakeWord = (current.config.wake_word || "portrait").toLowerCase();
          if (normalized.includes(wakeWord)) {
            handled = true;
            recognition.abort();
            current.onWakeWord();
            return;
          }
        }

        // 2. Continuous listening for user utterance while in LISTENING state
        if (current.state === PortraitState.LISTENING) {
          const stopPhrase = (current.config.stop_phrase || "goodbye portrait").toLowerCase();

          if (normalized.includes(stopPhrase)) {
            handled = true;
            recognition.abort();
            current.onStopPhrase();
            return;
          }

          if (finalTranscript.trim()) {
            handled = true;
            recognition.abort();
            current.onUserInput(finalTranscript.trim());
          }
        }
      };

      recognition.onerror = (err: any) => {
        if (disposed) return;
        if (["not-allowed", "service-not-allowed", "audio-capture", "language-not-supported"].includes(err.error)) {
          blocked = true;
          setMicError("Microphone unavailable. Check browser permissions or use the text prompt.");
        }
        if (err.error !== "no-speech" && err.error !== "aborted") {
          console.warn("Speech recognition error:", err.error);
        }
      };

      recognition.onend = () => {
        if (disposed) return;
        setIsMicListening(false);
        if (!handled && !blocked) {
          restartTimer = setTimeout(start, 300);
        }
      };
      recognition.onstart = () => {
        if (disposed) return;
        setMicError("");
        setIsMicListening(true);
      };
      start();
    } catch (e) {
      console.warn("Could not setup SpeechRecognition:", e);
      setSttSupported(false);
    }

    return () => {
      disposed = true;
      clearTimeout(restartTimer);
      recognition.onend = null;
      recognition.onstart = null;
      recognition.onresult = null;
      recognition.onerror = null;
      try { recognition.abort(); } catch {}
      setIsMicListening(false);
    };
  }, [config.language, listeningEnabled]);

  // Web Speech has no gender field. Prefer known masculine English voices,
  // then retain the chosen voice across model and callback changes.
  useEffect(() => {
    if (!("speechSynthesis" in window)) return;
    selectedVoiceRef.current = null;
    const chooseVoice = () => {
      if (selectedVoiceRef.current) return;
      const language = (config.language || "en-US").toLowerCase();
      const voices = window.speechSynthesis.getVoices().filter((voice) =>
        voice.lang.toLowerCase().startsWith(language.split("-")[0])
      );
      const maleName = /\b(male|david|mark|george|daniel|alex|guy|ryan|james|arthur|oliver|thomas|fred|aaron)\b/i;
      const score = (voice: SpeechSynthesisVoice) =>
        (maleName.test(voice.name) && !/\bfemale\b/i.test(voice.name) ? 100 : 0) +
        (voice.lang.toLowerCase() === language ? 10 : 0) + (voice.localService ? 1 : 0);
      voices.sort((a, b) => score(b) - score(a) || a.voiceURI.localeCompare(b.voiceURI));
      selectedVoiceRef.current = voices[0] || null;
    };
    chooseVoice();
    window.speechSynthesis.addEventListener("voiceschanged", chooseVoice);
    return () => window.speechSynthesis.removeEventListener("voiceschanged", chooseVoice);
  }, [config.language]);

  // TTS Speech Synthesis with Real-Time Lip-Sync
  useEffect(() => {
    if (!speechTextToSay) return;
    let active = true;
    let finished = false;
    const finish = () => {
      if (!active || finished) return;
      finished = true;
      if (mouthAnimRef.current !== null) cancelAnimationFrame(mouthAnimRef.current);
      callbacksRef.current.setMouthLevel(0);
      callbacksRef.current.onSpeechDone();
    };
    const stopAnimation = () => {
      active = false;
      if (mouthAnimRef.current !== null) cancelAnimationFrame(mouthAnimRef.current);
      mouthAnimRef.current = null;
      callbacksRef.current.setMouthLevel(0);
    };

    if (!("speechSynthesis" in window)) {
      // Fallback mouth animation timer
      const start = performance.now();
      const duration = Math.min(Math.max(speechTextToSay.length * 50, 1800), 5000);

      const animMouth = () => {
        if (!active) return;
        const elapsed = performance.now() - start;
        if (elapsed < duration) {
          const level = Math.abs(Math.sin(elapsed * 0.015)) * 0.8 + Math.random() * 0.2;
          callbacksRef.current.setMouthLevel(level);
          mouthAnimRef.current = requestAnimationFrame(animMouth);
        } else {
          finish();
        }
      };
      mouthAnimRef.current = requestAnimationFrame(animMouth);
      return stopAnimation;
    }

    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(speechTextToSay);
    utterance.lang = callbacksRef.current.config.language || "en-US";
    utterance.rate = 1.0;
    utterance.pitch = 0.85;

    if (selectedVoiceRef.current) utterance.voice = selectedVoiceRef.current;

    // Lip sync animation loop while speaking
    let lastFrame = 0;
    const animateMouth = () => {
      if (!active || finished) return;
      // Syllable oscillation pattern
      const now = performance.now();
      if (now - lastFrame >= 1000 / 30) {
        const wave = (Math.sin(now * 0.018) + 1) * 0.45;
        callbacksRef.current.setMouthLevel(Math.min(1.0, wave + Math.random() * 0.15));
        lastFrame = now;
      }
      mouthAnimRef.current = requestAnimationFrame(animateMouth);
    };

    const queuedAt = performance.now();
    utterance.onstart = () => {
      if (!active) return;
      callbacksRef.current.onSpeechStart((performance.now() - queuedAt) / 1000);
      mouthAnimRef.current = requestAnimationFrame(animateMouth);
    };

    utterance.onend = finish;

    utterance.onerror = (e) => {
      if (!active) return;
      console.warn("TTS playback encountered issue, continuing:", e.error);
      finish();
    };

    window.speechSynthesis.speak(utterance);

    return () => {
      stopAnimation();
      utterance.onstart = null;
      utterance.onend = null;
      utterance.onerror = null;
      window.speechSynthesis.cancel();
    };
  }, [speechTextToSay]);

  const handleManualSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!manualText.trim() || (state !== PortraitState.IDLE && state !== PortraitState.LISTENING)) return;
    onUserInput(manualText.trim());
    setManualText("");
  };

  return (
    <div className="bg-stone-900/90 border border-stone-800 rounded-xl p-4 flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Mic className={`w-4 h-4 ${isMicListening ? "text-amber-400 animate-pulse" : "text-stone-500"}`} />
          <span className="font-cinzel text-xs font-bold tracking-wider text-stone-200">
            VOICE & CONVERSATION ENGINE
          </span>
        </div>
        <div className="flex items-center gap-2 text-xs">
          <span className="text-stone-400">Wake word:</span>
          <span className="bg-amber-950/80 text-amber-300 font-mono px-2 py-0.5 rounded border border-amber-800/60 font-semibold">
            "{config.wake_word}"
          </span>
        </div>
      </div>

      {!sttSupported && (
        <div className="flex items-center gap-2 text-xs text-amber-300 bg-amber-950/40 p-2 rounded border border-amber-800/40">
          <AlertCircle className="w-4 h-4 shrink-0 text-amber-400" />
          <span>Speech Recognition API not supported in this browser; use the text dialogue prompt below.</span>
        </div>
      )}
      {micError && <p role="status" className="text-xs text-amber-300">{micError}</p>}

      {/* Interactive text conversation input */}
      <form onSubmit={handleManualSubmit} className="flex gap-2">
        <input
          type="text"
          value={manualText}
          onChange={(e) => setManualText(e.target.value)}
          placeholder={`Speak to the portrait or type (e.g. "${config.wake_word}, what is your secret?")...`}
          className="flex-1 bg-stone-950 border border-stone-700 rounded-lg px-3 py-2 text-sm text-stone-100 placeholder-stone-500 focus:outline-none focus:border-amber-500 transition-colors"
        />
        <button
          type="submit"
          disabled={!manualText.trim() || (state !== PortraitState.IDLE && state !== PortraitState.LISTENING)}
          className="bg-amber-700 hover:bg-amber-600 disabled:opacity-40 disabled:hover:bg-amber-700 text-amber-100 px-4 py-2 rounded-lg text-sm font-medium flex items-center gap-1.5 transition-colors cursor-pointer"
        >
          <Send className="w-4 h-4" />
          <span className="hidden sm:inline">Send</span>
        </button>
      </form>

      <div className="flex items-center justify-between text-[11px] text-stone-400">
        <span>Say <strong className="text-stone-300">"{config.stop_phrase}"</strong> to end chat session</span>
        <span className="text-stone-500">Auto-lip sync active</span>
      </div>
    </div>
  );
};
