import React, { useState } from "react";
import { AssetLayerSet, PortraitState } from "../types";
import {
  Layers,
  Upload,
  Eye,
  Volume2,
  CheckCircle2,
  Info,
  RotateCcw,
  Sparkles,
  Sliders,
  Maximize2,
  FileCode,
  Image as ImageIcon,
} from "lucide-react";

interface FacialFeaturesStudioProps {
  customLayers: AssetLayerSet;
  onUpdateLayer: (layerName: keyof AssetLayerSet, dataUrl: string | null) => void;
  onResetAllLayers: () => void;
  mouthLevel: number;
  onSimulateMouthLevel: (level: number) => void;
  isForceBlinking: boolean;
  onToggleForceBlink: (force: boolean) => void;
  showGuides: boolean;
  onToggleShowGuides: (show: boolean) => void;
  currentState: PortraitState;
}

export const FacialFeaturesStudio: React.FC<FacialFeaturesStudioProps> = ({
  customLayers,
  onUpdateLayer,
  onResetAllLayers,
  mouthLevel,
  onSimulateMouthLevel,
  isForceBlinking,
  onToggleForceBlink,
  showGuides,
  onToggleShowGuides,
  currentState,
}) => {
  const [activeTab, setActiveTab] = useState<"layers" | "pipeline" | "docs">("layers");

  const handleFileUpload = (
    layerName: keyof AssetLayerSet,
    e: React.ChangeEvent<HTMLInputElement>
  ) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (event) => {
      if (typeof event.target?.result === "string") {
        onUpdateLayer(layerName, event.target.result);
      }
    };
    reader.readAsDataURL(file);
  };

  const getMouthShapeName = (level: number) => {
    if (level < 0.15) return { name: "MOUTH 1 (Closed)", color: "text-stone-300", bg: "bg-stone-800" };
    if (level < 0.45) return { name: "MOUTH 2 (Slightly Open)", color: "text-amber-300", bg: "bg-amber-950/80" };
    return { name: "MOUTH 3 (Open)", color: "text-orange-400", bg: "bg-orange-950/80" };
  };

  const currentMouthInfo = getMouthShapeName(mouthLevel);

  return (
    <div className="bg-stone-900/90 border border-stone-800 rounded-2xl p-5 shadow-xl flex flex-col gap-4">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-stone-800 pb-3">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-amber-950/80 border border-amber-700/50 flex items-center justify-center text-amber-300">
            <Layers className="w-4 h-4" />
          </div>
          <div>
            <h3 className="font-cinzel text-sm sm:text-base font-bold text-amber-100 flex items-center gap-2">
              Facial Features &amp; Overlay Architecture
            </h3>
            <p className="text-[11px] text-stone-400">
              Layered 2D Sprite Blending (Base + Eyes Closed + 3 Audio Mouth Shapes)
            </p>
          </div>
        </div>

        {/* Tab Toggle */}
        <div className="flex items-center gap-1 bg-stone-950 p-1 rounded-xl border border-stone-800 text-xs">
          <button
            onClick={() => setActiveTab("layers")}
            className={`px-2.5 py-1 rounded-lg transition-all ${
              activeTab === "layers" ? "bg-amber-600 text-stone-950 font-bold" : "text-stone-400 hover:text-stone-200"
            }`}
          >
            Layer Inspector
          </button>
          <button
            onClick={() => setActiveTab("pipeline")}
            className={`px-2.5 py-1 rounded-lg transition-all ${
              activeTab === "pipeline" ? "bg-amber-600 text-stone-950 font-bold" : "text-stone-400 hover:text-stone-200"
            }`}
          >
            Live Test
          </button>
          <button
            onClick={() => setActiveTab("docs")}
            className={`px-2.5 py-1 rounded-lg transition-all ${
              activeTab === "docs" ? "bg-amber-600 text-stone-950 font-bold" : "text-stone-400 hover:text-stone-200"
            }`}
          >
            Usage Notes
          </button>
        </div>
      </div>

      {/* TAB 1: Layer Inspector & Custom Uploaders */}
      {activeTab === "layers" && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-2.5 text-xs">
            {/* 1. Base Layer */}
            <div className="bg-stone-950/80 border border-stone-800 rounded-xl p-2.5 flex flex-col items-center text-center gap-2 relative group">
              <div className="w-full h-20 bg-stone-900 rounded-lg border border-stone-800 flex items-center justify-center overflow-hidden relative">
                {customLayers.base ? (
                  <img src={customLayers.base} alt="Base" className="w-full h-full object-cover" />
                ) : (
                  <div className="flex flex-col items-center justify-center text-stone-500">
                    <ImageIcon className="w-6 h-6 text-amber-400/70 mb-1" />
                    <span className="text-[10px]">Photo Base</span>
                  </div>
                )}
                <span className="absolute top-1 left-1 bg-stone-950/80 text-amber-300 text-[9px] px-1 rounded">
                  Layer 1
                </span>
              </div>
              <div>
                <p className="font-semibold text-stone-200 text-[11px]">BASE (Neutral)</p>
                <p className="text-[9px] text-stone-400">Eyes open &amp; neutral</p>
              </div>
              <label className="w-full py-1 px-2 rounded bg-stone-800 hover:bg-stone-700 text-stone-300 text-[10px] cursor-pointer flex items-center justify-center gap-1">
                <Upload className="w-3 h-3" />
                <span>Upload</span>
                <input
                  type="file"
                  accept="image/*"
                  onChange={(e) => handleFileUpload("base", e)}
                  className="hidden"
                />
              </label>
            </div>

            {/* 2. Eyes Closed Overlay */}
            <div className="bg-stone-950/80 border border-stone-800 rounded-xl p-2.5 flex flex-col items-center text-center gap-2 relative group">
              <div className="w-full h-20 bg-stone-900 rounded-lg border border-stone-800 flex items-center justify-center overflow-hidden relative">
                {customLayers.eyesClosed ? (
                  <img src={customLayers.eyesClosed} alt="Eyes Closed" className="w-full h-full object-cover" />
                ) : (
                  <div className="flex flex-col items-center justify-center text-stone-500">
                    <Eye className="w-6 h-6 text-sky-400/70 mb-1" />
                    <span className="text-[10px]">Eyelids + Glasses</span>
                  </div>
                )}
                <span className="absolute top-1 left-1 bg-sky-950 text-sky-300 text-[9px] px-1 rounded">
                  Overlay
                </span>
              </div>
              <div>
                <p className="font-semibold text-stone-200 text-[11px]">EYES CLOSED</p>
                <p className="text-[9px] text-stone-400">Blinking transparent</p>
              </div>
              <label className="w-full py-1 px-2 rounded bg-stone-800 hover:bg-stone-700 text-stone-300 text-[10px] cursor-pointer flex items-center justify-center gap-1">
                <Upload className="w-3 h-3" />
                <span>Upload</span>
                <input
                  type="file"
                  accept="image/*"
                  onChange={(e) => handleFileUpload("eyesClosed", e)}
                  className="hidden"
                />
              </label>
            </div>

            {/* 3. Mouth 1 Overlay */}
            <div className="bg-stone-950/80 border border-stone-800 rounded-xl p-2.5 flex flex-col items-center text-center gap-2 relative group">
              <div className="w-full h-20 bg-stone-900 rounded-lg border border-stone-800 flex items-center justify-center overflow-hidden relative">
                {customLayers.mouth1 ? (
                  <img src={customLayers.mouth1} alt="Mouth 1" className="w-full h-full object-cover" />
                ) : (
                  <div className="flex flex-col items-center justify-center text-stone-500">
                    <div className="w-6 h-1 bg-stone-400 rounded-full mb-1" />
                    <span className="text-[10px]">Closed Beard</span>
                  </div>
                )}
                <span className="absolute top-1 left-1 bg-stone-950 text-stone-300 text-[9px] px-1 rounded">
                  &lt; 0.15 RMS
                </span>
              </div>
              <div>
                <p className="font-semibold text-stone-200 text-[11px]">MOUTH 1</p>
                <p className="text-[9px] text-stone-400">Closed rest shape</p>
              </div>
              <label className="w-full py-1 px-2 rounded bg-stone-800 hover:bg-stone-700 text-stone-300 text-[10px] cursor-pointer flex items-center justify-center gap-1">
                <Upload className="w-3 h-3" />
                <span>Upload</span>
                <input
                  type="file"
                  accept="image/*"
                  onChange={(e) => handleFileUpload("mouth1", e)}
                  className="hidden"
                />
              </label>
            </div>

            {/* 4. Mouth 2 Overlay */}
            <div className="bg-stone-950/80 border border-stone-800 rounded-xl p-2.5 flex flex-col items-center text-center gap-2 relative group">
              <div className="w-full h-20 bg-stone-900 rounded-lg border border-stone-800 flex items-center justify-center overflow-hidden relative">
                {customLayers.mouth2 ? (
                  <img src={customLayers.mouth2} alt="Mouth 2" className="w-full h-full object-cover" />
                ) : (
                  <div className="flex flex-col items-center justify-center text-stone-500">
                    <div className="w-6 h-2 bg-amber-600 rounded-full mb-1" />
                    <span className="text-[10px]">Slightly Open</span>
                  </div>
                )}
                <span className="absolute top-1 left-1 bg-amber-950 text-amber-300 text-[9px] px-1 rounded">
                  0.15 - 0.45
                </span>
              </div>
              <div>
                <p className="font-semibold text-stone-200 text-[11px]">MOUTH 2</p>
                <p className="text-[9px] text-stone-400">Slightly open teeth</p>
              </div>
              <label className="w-full py-1 px-2 rounded bg-stone-800 hover:bg-stone-700 text-stone-300 text-[10px] cursor-pointer flex items-center justify-center gap-1">
                <Upload className="w-3 h-3" />
                <span>Upload</span>
                <input
                  type="file"
                  accept="image/*"
                  onChange={(e) => handleFileUpload("mouth2", e)}
                  className="hidden"
                />
              </label>
            </div>

            {/* 5. Mouth 3 Overlay */}
            <div className="bg-stone-950/80 border border-stone-800 rounded-xl p-2.5 flex flex-col items-center text-center gap-2 relative group">
              <div className="w-full h-20 bg-stone-900 rounded-lg border border-stone-800 flex items-center justify-center overflow-hidden relative">
                {customLayers.mouth3 ? (
                  <img src={customLayers.mouth3} alt="Mouth 3" className="w-full h-full object-cover" />
                ) : (
                  <div className="flex flex-col items-center justify-center text-stone-500">
                    <div className="w-6 h-4 bg-orange-700 rounded-full mb-1" />
                    <span className="text-[10px]">Wide Open</span>
                  </div>
                )}
                <span className="absolute top-1 left-1 bg-orange-950 text-orange-300 text-[9px] px-1 rounded">
                  &ge; 0.45 RMS
                </span>
              </div>
              <div>
                <p className="font-semibold text-stone-200 text-[11px]">MOUTH 3</p>
                <p className="text-[9px] text-stone-400">Wide open vowel</p>
              </div>
              <label className="w-full py-1 px-2 rounded bg-stone-800 hover:bg-stone-700 text-stone-300 text-[10px] cursor-pointer flex items-center justify-center gap-1">
                <Upload className="w-3 h-3" />
                <span>Upload</span>
                <input
                  type="file"
                  accept="image/*"
                  onChange={(e) => handleFileUpload("mouth3", e)}
                  className="hidden"
                />
              </label>
            </div>
          </div>

          <div className="flex items-center justify-between pt-1 text-xs">
            <span className="text-stone-400 text-[11px]">
              All overlay files are aligned 1:1 to base size (no offset calculations needed).
            </span>
            <button
              onClick={onResetAllLayers}
              className="text-stone-400 hover:text-amber-300 flex items-center gap-1 text-[11px] underline cursor-pointer"
            >
              <RotateCcw className="w-3 h-3" /> Reset to Photo Defaults
            </button>
          </div>
        </div>
      )}

      {/* TAB 2: Live Test Controls */}
      {activeTab === "pipeline" && (
        <div className="space-y-4 text-xs">
          {/* Active Mouth State Display */}
          <div className="flex items-center justify-between bg-stone-950 p-3 rounded-xl border border-stone-800">
            <div className="flex items-center gap-2">
              <span className="text-stone-400">Active Mouth Sprite:</span>
              <span className={`px-2 py-0.5 rounded font-mono font-bold text-[11px] ${currentMouthInfo.bg} ${currentMouthInfo.color}`}>
                {currentMouthInfo.name}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-stone-400">RMS Level:</span>
              <span className="font-mono text-amber-300">{(mouthLevel * 100).toFixed(0)}%</span>
            </div>
          </div>

          {/* Audio Amplitude Simulator Slider */}
          <div className="space-y-1.5">
            <div className="flex justify-between text-[11px] text-stone-400">
              <span>Test Audio Amplitude (Simulate TTS Speech)</span>
              <div className="flex gap-2">
                <button
                  onClick={() => onSimulateMouthLevel(0.0)}
                  className="px-2 py-0.5 bg-stone-800 hover:bg-stone-700 rounded text-[10px]"
                >
                  Rest (Mouth 1)
                </button>
                <button
                  onClick={() => onSimulateMouthLevel(0.3)}
                  className="px-2 py-0.5 bg-stone-800 hover:bg-stone-700 rounded text-[10px]"
                >
                  Mid (Mouth 2)
                </button>
                <button
                  onClick={() => onSimulateMouthLevel(0.8)}
                  className="px-2 py-0.5 bg-stone-800 hover:bg-stone-700 rounded text-[10px]"
                >
                  Loud (Mouth 3)
                </button>
              </div>
            </div>
            <input
              type="range"
              min="0"
              max="1"
              step="0.02"
              value={mouthLevel}
              onChange={(e) => onSimulateMouthLevel(parseFloat(e.target.value))}
              className="w-full accent-amber-500 cursor-pointer"
            />
            <div className="flex justify-between text-[9px] font-mono text-stone-500">
              <span>0.0 (Closed)</span>
              <span>0.15 (Threshold Mouth 2)</span>
              <span>0.45 (Threshold Mouth 3)</span>
              <span>1.0 (Max Open)</span>
            </div>
          </div>

          {/* Toggles */}
          <div className="grid grid-cols-2 gap-3">
            <button
              onClick={() => onToggleForceBlink(!isForceBlinking)}
              className={`p-2.5 rounded-xl border flex items-center justify-between transition-all cursor-pointer ${
                isForceBlinking
                  ? "bg-sky-950/80 border-sky-600 text-sky-200"
                  : "bg-stone-950 border-stone-800 text-stone-400 hover:border-stone-700"
              }`}
            >
              <div className="flex items-center gap-2">
                <Eye className="w-4 h-4 text-sky-400" />
                <span className="font-semibold text-[11px]">Force Eyes Closed Overlay</span>
              </div>
              <span className="text-[10px] font-mono">{isForceBlinking ? "ON" : "OFF"}</span>
            </button>

            <button
              onClick={() => onToggleShowGuides(!showGuides)}
              className={`p-2.5 rounded-xl border flex items-center justify-between transition-all cursor-pointer ${
                showGuides
                  ? "bg-amber-950/80 border-amber-600 text-amber-200"
                  : "bg-stone-950 border-stone-800 text-stone-400 hover:border-stone-700"
              }`}
            >
              <div className="flex items-center gap-2">
                <Sliders className="w-4 h-4 text-amber-400" />
                <span className="font-semibold text-[11px]">Show Layer Alignment Guides</span>
              </div>
              <span className="text-[10px] font-mono">{showGuides ? "ON" : "OFF"}</span>
            </button>
          </div>
        </div>
      )}

      {/* TAB 3: Usage Notes Specification */}
      {activeTab === "docs" && (
        <div className="space-y-3 bg-stone-950 p-3.5 rounded-xl border border-stone-800 text-xs">
          <div className="flex items-center gap-2 text-amber-300 font-cinzel font-bold text-xs">
            <Info className="w-4 h-4" />
            <span>RENDER PIPELINE RULES</span>
          </div>
          <ul className="space-y-2 text-stone-300 list-disc list-inside text-[11px] leading-relaxed">
            <li>
              <strong>Draw base image first:</strong> The base canvas presents the neutral expression with open eyes and closed lips.
            </li>
            <li>
              <strong>For blinking:</strong> Draw <code className="text-sky-300 font-mono bg-stone-900 px-1 py-0.5 rounded">EYES CLOSED OVERLAY</code> on top of the base image during the 150ms blink window.
            </li>
            <li>
              <strong>For talking:</strong> Draw one of the mouth overlays on top of the base (choose based on audio amplitude):
              <div className="pl-4 pt-1 space-y-1 text-stone-400 font-mono text-[10px]">
                <div>&bull; RMS &lt; 0.15 &rarr; MOUTH 1 (Closed)</div>
                <div>&bull; 0.15 &le; RMS &lt; 0.45 &rarr; MOUTH 2 (Slightly Open)</div>
                <div>&bull; RMS &ge; 0.45 &rarr; MOUTH 3 (Open)</div>
              </div>
            </li>
            <li>
              <strong>1:1 Dimensional Alignment:</strong> All overlay assets have a transparent background and share identical framing dimensions, eliminating manual coordinate offsets.
            </li>
          </ul>
        </div>
      )}
    </div>
  );
};
