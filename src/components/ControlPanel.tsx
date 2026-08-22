import React from "react";
import { AppConfig, PersonaType } from "../types";
import { Settings, Sliders, Sparkles, RefreshCw, X, Shield, Volume2, Camera, Eye, User } from "lucide-react";

interface ControlPanelProps {
  config: AppConfig;
  onChangeConfig: (newConfig: AppConfig) => void;
  isOpen: boolean;
  onClose: () => void;
  personaType: PersonaType;
  onSelectPersona: (persona: PersonaType) => void;
  onResetDefaults: () => void;
}

export const ControlPanel: React.FC<ControlPanelProps> = ({
  config,
  onChangeConfig,
  isOpen,
  onClose,
  personaType,
  onSelectPersona,
  onResetDefaults,
}) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex justify-end transition-opacity">
      <div className="w-full max-w-md bg-stone-900 border-l border-stone-800 h-full overflow-y-auto p-6 flex flex-col gap-6 text-stone-200 shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between pb-4 border-b border-stone-800">
          <div className="flex items-center gap-2">
            <Sliders className="w-5 h-5 text-amber-500" />
            <h2 className="font-cinzel text-lg font-bold tracking-wider text-amber-100">
              PORTRAIT SETTINGS
            </h2>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-lg text-stone-400 hover:text-stone-100 hover:bg-stone-800 transition-colors cursor-pointer"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* 1. Persona Selector */}
        <div className="flex flex-col gap-2">
          <label className="text-xs font-semibold text-stone-400 uppercase tracking-wider">
            Active Persona Preset
          </label>
          <div className="grid grid-cols-2 gap-2">
            <button
              onClick={() => onSelectPersona("photo_portrait")}
              className={`p-2.5 rounded-lg border text-left flex flex-col gap-1 transition-all cursor-pointer ${
                personaType === "photo_portrait"
                  ? "bg-amber-950/80 border-amber-400 text-amber-100 shadow-md ring-1 ring-amber-400/40"
                  : "bg-stone-950 border-stone-800 text-stone-400 hover:border-stone-700"
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="text-base">🧔👓</span>
                <span className="text-[9px] bg-amber-900 text-amber-200 px-1 rounded font-mono">Real Photo</span>
              </div>
              <span className="text-xs font-bold font-cinzel text-stone-200">Lord Cadogan (Photo)</span>
              <span className="text-[10px] text-stone-400">Glasses, Beard, 3-Mouth Layers</span>
            </button>

            <button
              onClick={() => onSelectPersona("haunted_portrait")}
              className={`p-2.5 rounded-lg border text-left flex flex-col gap-1 transition-all cursor-pointer ${
                personaType === "haunted_portrait"
                  ? "bg-amber-950/60 border-amber-500 text-amber-100 shadow-md"
                  : "bg-stone-950 border-stone-800 text-stone-400 hover:border-stone-700"
              }`}
            >
              <span className="text-base">🖼️</span>
              <span className="text-xs font-bold font-cinzel">Noble Alistair</span>
              <span className="text-[10px] text-stone-400">Haunted Knight</span>
            </button>

            <button
              onClick={() => onSelectPersona("talking_fish")}
              className={`p-2.5 rounded-lg border text-left flex flex-col gap-1 transition-all cursor-pointer ${
                personaType === "talking_fish"
                  ? "bg-sky-950/60 border-sky-500 text-sky-100 shadow-md"
                  : "bg-stone-950 border-stone-800 text-stone-400 hover:border-stone-700"
              }`}
            >
              <span className="text-base">🐟</span>
              <span className="text-xs font-bold font-cinzel">Wilhelm</span>
              <span className="text-[10px] text-stone-400">Talking Trophy Fish</span>
            </button>

            <button
              onClick={() => onSelectPersona("spooky_witch")}
              className={`p-2.5 rounded-lg border text-left flex flex-col gap-1 transition-all cursor-pointer ${
                personaType === "spooky_witch"
                  ? "bg-purple-950/60 border-purple-500 text-purple-100 shadow-md"
                  : "bg-stone-950 border-stone-800 text-stone-400 hover:border-stone-700"
              }`}
            >
              <span className="text-base">🧙‍♀️</span>
              <span className="text-xs font-bold font-cinzel">Morgana</span>
              <span className="text-[10px] text-stone-400">Enchanted Witch</span>
            </button>
          </div>
        </div>

        {/* 2. Wake Word & Stop Phrase */}
        <div className="flex flex-col gap-4 bg-stone-950 p-4 rounded-xl border border-stone-800/80">
          <h3 className="text-xs font-bold text-amber-300 uppercase tracking-wider flex items-center gap-1.5">
            <Volume2 className="w-3.5 h-3.5" />
            Voice Commands
          </h3>

          <div className="flex flex-col gap-1">
            <label className="text-xs text-stone-400">Wake Word</label>
            <input
              type="text"
              value={config.conversation.wake_word}
              onChange={(e) =>
                onChangeConfig({
                  ...config,
                  conversation: { ...config.conversation, wake_word: e.target.value },
                })
              }
              className="bg-stone-900 border border-stone-700 rounded-lg px-3 py-1.5 text-sm text-stone-100 focus:outline-none focus:border-amber-500"
            />
          </div>

          <div className="flex flex-col gap-1">
            <label className="text-xs text-stone-400">Stop Phrase</label>
            <input
              type="text"
              value={config.conversation.stop_phrase}
              onChange={(e) =>
                onChangeConfig({
                  ...config,
                  conversation: { ...config.conversation, stop_phrase: e.target.value },
                })
              }
              className="bg-stone-900 border border-stone-700 rounded-lg px-3 py-1.5 text-sm text-stone-100 focus:outline-none focus:border-amber-500"
            />
          </div>
        </div>

        {/* 3. System Prompt */}
        <div className="flex flex-col gap-2">
          <label className="text-xs font-semibold text-stone-400 uppercase tracking-wider flex items-center gap-1.5">
            <Sparkles className="w-3.5 h-3.5 text-amber-400" />
            Personality & Gemini Prompt
          </label>
          <textarea
            rows={3}
            value={config.conversation.system_prompt}
            onChange={(e) =>
              onChangeConfig({
                ...config,
                conversation: { ...config.conversation, system_prompt: e.target.value },
              })
            }
            className="bg-stone-950 border border-stone-800 rounded-lg p-3 text-xs text-stone-200 focus:outline-none focus:border-amber-500 font-sans leading-relaxed"
          />
        </div>

        {/* 4. Camera & Optical Sensors */}
        <div className="flex flex-col gap-3 bg-stone-950 p-4 rounded-xl border border-stone-800/80">
          <h3 className="text-xs font-bold text-amber-300 uppercase tracking-wider flex items-center gap-1.5">
            <Camera className="w-3.5 h-3.5" />
            Camera & Trigger Calibration
          </h3>

          <div className="flex items-center justify-between">
            <span className="text-xs text-stone-300">Enable Optical Camera Trigger</span>
            <input
              type="checkbox"
              checked={config.camera.enabled}
              onChange={(e) =>
                onChangeConfig({
                  ...config,
                  camera: { ...config.camera, enabled: e.target.checked },
                })
              }
              className="accent-amber-500 w-4 h-4 cursor-pointer"
            />
          </div>

          <div className="flex flex-col gap-1">
            <div className="flex justify-between text-xs text-stone-400">
              <span>Trigger Sensitivity Threshold</span>
              <span className="font-mono">{Math.round(config.camera.hailo_threshold * 100)}%</span>
            </div>
            <input
              type="range"
              min="0.15"
              max="0.85"
              step="0.05"
              value={config.camera.hailo_threshold}
              onChange={(e) =>
                onChangeConfig({
                  ...config,
                  camera: { ...config.camera, hailo_threshold: parseFloat(e.target.value) },
                })
              }
              className="accent-amber-500 cursor-pointer"
            />
          </div>

          <div className="flex flex-col gap-1">
            <div className="flex justify-between text-xs text-stone-400">
              <span>Cooldown Period</span>
              <span className="font-mono">{config.cooldown.seconds}s</span>
            </div>
            <input
              type="range"
              min="3"
              max="30"
              step="1"
              value={config.cooldown.seconds}
              onChange={(e) =>
                onChangeConfig({
                  ...config,
                  cooldown: { seconds: parseInt(e.target.value, 10) },
                })
              }
              className="accent-amber-500 cursor-pointer"
            />
          </div>
        </div>

        {/* 5. Demo Simulation Mode */}
        <div className="flex items-center justify-between bg-stone-950 p-4 rounded-xl border border-stone-800/80">
          <div className="flex flex-col">
            <span className="text-xs font-bold text-stone-300">Demo Simulation Mode</span>
            <span className="text-[11px] text-stone-500">Auto-triggers scripted responses</span>
          </div>
          <input
            type="checkbox"
            checked={config.demo_mode.enabled}
            onChange={(e) =>
              onChangeConfig({
                ...config,
                demo_mode: { ...config.demo_mode, enabled: e.target.checked },
              })
            }
            className="accent-amber-500 w-4 h-4 cursor-pointer"
          />
        </div>

        {/* Reset Defaults Button */}
        <div className="mt-auto pt-4 border-t border-stone-800 flex justify-between">
          <button
            onClick={onResetDefaults}
            className="text-xs text-stone-400 hover:text-amber-400 flex items-center gap-1.5 transition-colors cursor-pointer"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            <span>Reset Defaults</span>
          </button>
          <button
            onClick={onClose}
            className="bg-amber-600 hover:bg-amber-500 text-amber-50 px-4 py-1.5 rounded-lg text-xs font-semibold font-cinzel transition-colors cursor-pointer"
          >
            Done
          </button>
        </div>
      </div>
    </div>
  );
};
