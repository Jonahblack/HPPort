import React, { useEffect, useRef, useState, useCallback } from "react";
import { ConversationConfig, PortraitState } from "../types";
import { Mic, MicOff, Volume2, Send, Sparkles, AlertCircle } from "lucide-react";

interface VoiceControllerProps {
  config: ConversationConfig;
  state: PortraitState;
  onWakeWord: () => void;
  onUserInput: (text: string) => void;
  onStopPhrase: () => void;
  setMouthLevel: (level: number) => void;
  speechTextToSay: string | null;
  onSpeechDone: () => void;
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
  isDemoMode,
}) => {
  const [manualText, setManualText] = useState("");
  const [isMicListening, setIsMicListening] = useState(false);
  const [sttSupported, setSttSupported] = useState(true);
  const recognitionRef = useRef<any>(null);
  const mouthAnimRef = useRef<number | null>(null);

  // Initialize Web Speech Recognition
  useEffect(() => {
    const SpeechRecognition =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;

    if (!SpeechRecognition) {
      setSttSupported(false);
      return;
    }

    try {
      const recognition = new SpeechRecognition();
      recognition.continuous = true;
      recognition.interimResults = true;
      recognition.lang = config.language || "en-US";

      recognition.onresult = (event: any) => {
        let transcript = "";
        for (let i = event.resultIndex; i < event.results.length; ++i) {
          transcript += event.results[i][0].transcript;
        }
        transcript = transcript.trim().toLowerCase();

        // 1. Wake word spotting while IDLE
        if (state === PortraitState.IDLE) {
          const wakeWord = (config.wake_word || "portrait").toLowerCase();
          if (transcript.includes(wakeWord)) {
            recognition.abort();
            onWakeWord();
            return;
          }
        }

        // 2. Continuous listening for user utterance while in LISTENING state
        if (state === PortraitState.LISTENING) {
          const isFinal = event.results[event.results.length - 1].isFinal;
          const stopPhrase = (config.stop_phrase || "goodbye portrait").toLowerCase();

          if (transcript.includes(stopPhrase)) {
            recognition.abort();
            onStopPhrase();
            return;
          }

          if (isFinal && transcript.length > 0) {
            recognition.abort();
            onUserInput(transcript);
          }
        }
      };

      recognition.onerror = (err: any) => {
        if (err.error !== "no-speech") {
          console.warn("Speech recognition error:", err.error);
        }
      };

      recognition.onend = () => {
        setIsMicListening(false);
        // Automatically restart if state is IDLE or LISTENING and not demo mode
        if (
          !isDemoMode &&
          (state === PortraitState.IDLE || state === PortraitState.LISTENING)
        ) {
          try {
            recognition.start();
            setIsMicListening(true);
          } catch {
            // ignore rapid restart error
          }
        }
      };

      recognitionRef.current = recognition;
    } catch (e) {
      console.warn("Could not setup SpeechRecognition:", e);
      setSttSupported(false);
    }

    return () => {
      if (recognitionRef.current) {
        try {
          recognitionRef.current.abort();
        } catch {}
      }
    };
  }, [config.language, config.wake_word, config.stop_phrase, state, isDemoMode, onWakeWord, onUserInput, onStopPhrase]);

  // Manage Speech Recognition Start/Stop based on FSM State
  useEffect(() => {
    const recognition = recognitionRef.current;
    if (!recognition || isDemoMode) return;

    if (state === PortraitState.IDLE || state === PortraitState.LISTENING) {
      try {
        recognition.start();
        setIsMicListening(true);
      } catch (err) {
        // already started
      }
    } else {
      try {
        recognition.abort();
        setIsMicListening(false);
      } catch (err) {}
    }
  }, [state, isDemoMode]);

  // TTS Speech Synthesis with Real-Time Lip-Sync
  useEffect(() => {
    if (!speechTextToSay) return;

    if (!("speechSynthesis" in window)) {
      // Fallback mouth animation timer
      let start = performance.now();
      const duration = Math.min(Math.max(speechTextToSay.length * 50, 1800), 5000);

      const animMouth = () => {
        const elapsed = performance.now() - start;
        if (elapsed < duration) {
          const level = Math.abs(Math.sin(elapsed * 0.015)) * 0.8 + Math.random() * 0.2;
          setMouthLevel(level);
          mouthAnimRef.current = requestAnimationFrame(animMouth);
        } else {
          setMouthLevel(0);
          onSpeechDone();
        }
      };
      mouthAnimRef.current = requestAnimationFrame(animMouth);
      return;
    }

    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(speechTextToSay);
    utterance.lang = config.language || "en-US";
    utterance.rate = 0.95; // eerie, measured pace
    utterance.pitch = 0.9;

    // Pick an expressive English voice if available
    const voices = window.speechSynthesis.getVoices();
    const spookyVoice = voices.find(
      (v) =>
        v.lang.startsWith("en") &&
        (v.name.includes("Male") || v.name.includes("UK") || v.name.includes("Natural") || v.name.includes("Google"))
    );
    if (spookyVoice) {
      utterance.voice = spookyVoice;
    }

    // Lip sync animation loop while speaking
    let isSpeaking = true;
    const animateMouth = () => {
      if (!isSpeaking) return;
      // Syllable oscillation pattern
      const now = performance.now();
      const wave = (Math.sin(now * 0.018) + 1) * 0.45;
      const jitter = Math.random() * 0.15;
      setMouthLevel(Math.min(1.0, wave + jitter));
      mouthAnimRef.current = requestAnimationFrame(animateMouth);
    };

    utterance.onstart = () => {
      isSpeaking = true;
      mouthAnimRef.current = requestAnimationFrame(animateMouth);
    };

    utterance.onend = () => {
      isSpeaking = false;
      if (mouthAnimRef.current) cancelAnimationFrame(mouthAnimRef.current);
      setMouthLevel(0);
      onSpeechDone();
    };

    utterance.onerror = (e) => {
      console.warn("TTS playback encountered issue, continuing:", e);
      isSpeaking = false;
      if (mouthAnimRef.current) cancelAnimationFrame(mouthAnimRef.current);
      setMouthLevel(0);
      onSpeechDone();
    };

    window.speechSynthesis.speak(utterance);

    return () => {
      window.speechSynthesis.cancel();
      if (mouthAnimRef.current) cancelAnimationFrame(mouthAnimRef.current);
      setMouthLevel(0);
    };
  }, [speechTextToSay, config.language, setMouthLevel, onSpeechDone]);

  const handleManualSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!manualText.trim()) return;

    if (state === PortraitState.IDLE) {
      onWakeWord();
      setTimeout(() => {
        onUserInput(manualText.trim());
        setManualText("");
      }, 400);
    } else {
      onUserInput(manualText.trim());
      setManualText("");
    }
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
          disabled={!manualText.trim()}
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
