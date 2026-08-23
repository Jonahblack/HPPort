import React, { useEffect, useRef, useState } from "react";
import { CameraTriggerStatus, VisionLogEntry, CameraDeviceInfo, PortraitState } from "../types";
import {
  Camera,
  CameraOff,
  Maximize2,
  Minimize2,
  Terminal,
  RefreshCw,
  Eye,
  FlipHorizontal,
  Zap,
  ChevronDown,
  ChevronUp,
  Sliders,
  CheckCircle2,
  AlertTriangle,
  Info,
} from "lucide-react";

interface CameraCornerFeedProps {
  stream: MediaStream | null;
  status: CameraTriggerStatus;
  motionLevel: number;
  threshold: number;
  cameraError: string | null;
  deviceInfo: CameraDeviceInfo | null;
  logs: VisionLogEntry[];
  currentState: PortraitState;
  isMirrored: boolean;
  onToggleMirror: () => void;
  size: "compact" | "normal" | "minimized";
  onChangeSize: (size: "compact" | "normal" | "minimized") => void;
  onManualTrigger: () => void;
  onReconnect: () => void;
  onClearLogs: () => void;
  onChangeThreshold?: (newThreshold: number) => void;
}

export const CameraCornerFeed: React.FC<CameraCornerFeedProps> = ({
  stream,
  status,
  motionLevel,
  threshold,
  cameraError,
  deviceInfo,
  logs,
  currentState,
  isMirrored,
  onToggleMirror,
  size,
  onChangeSize,
  onManualTrigger,
  onReconnect,
  onClearLogs,
  onChangeThreshold,
}) => {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [showLogDrawer, setShowLogDrawer] = useState<boolean>(false);
  const [showSensitivityAdjust, setShowSensitivityAdjust] = useState<boolean>(false);

  // Attach stream to video element
  useEffect(() => {
    if (videoRef.current && stream) {
      videoRef.current.srcObject = stream;
      videoRef.current.play().catch(() => {});
    }
  }, [stream]);

  const isPersonDetected = status.personDetected;
  const isIdle = currentState === PortraitState.IDLE;

  if (size === "minimized") {
    return (
      <div
        id="camera-corner-minimized"
        className="absolute bottom-3 right-3 z-30 flex items-center gap-2 bg-stone-900/90 hover:bg-stone-800 backdrop-blur-md px-3 py-1.5 rounded-xl border border-amber-500/40 shadow-xl transition-all cursor-pointer group"
        onClick={(e) => {
          e.stopPropagation();
          onChangeSize("normal");
        }}
        title="Click to expand live camera debug view"
      >
        <div className="relative">
          <Camera className={`w-4 h-4 ${stream ? (isPersonDetected ? "text-emerald-400" : "text-amber-400") : "text-red-400"}`} />
          {isPersonDetected && (
            <span className="absolute -top-1 -right-1 w-2 h-2 rounded-full bg-emerald-400 animate-ping" />
          )}
        </div>
        <div className="flex flex-col">
          <span className="text-[10px] font-cinzel font-bold text-amber-200 flex items-center gap-1">
            Pi Camera Feed
            <span
              className={`w-1.5 h-1.5 rounded-full ${
                isPersonDetected ? "bg-emerald-400" : stream ? "bg-amber-400" : "bg-red-400"
              }`}
            />
          </span>
          <span className="text-[9px] text-stone-400 font-mono">
            {isPersonDetected ? "Person In View" : `${(motionLevel * 100).toFixed(0)}% act`}
          </span>
        </div>
        <Maximize2 className="w-3.5 h-3.5 text-stone-400 group-hover:text-amber-300 ml-1" />
      </div>
    );
  }

  const isCompact = size === "compact";

  return (
    <div
      id="camera-corner-feed-panel"
      onClick={(e) => e.stopPropagation()}
      className={`absolute bottom-3 right-3 z-30 flex flex-col rounded-xl overflow-hidden border shadow-2xl backdrop-blur-md transition-all duration-200 ${

        isPersonDetected
          ? "border-emerald-500/70 shadow-emerald-950/50 bg-stone-950/95"
          : "border-stone-700/80 shadow-black/80 bg-stone-950/90"
      } ${isCompact ? "w-56 sm:w-64" : "w-64 sm:w-76"}`}
    >
      {/* Top Title & Controls Header */}
      <div className="px-2.5 py-1.5 bg-stone-900/90 border-b border-stone-800 flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <span className="relative flex h-2 w-2">
            {isPersonDetected ? (
              <>
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
              </>
            ) : stream ? (
              <span className="relative inline-flex rounded-full h-2 w-2 bg-amber-400 animate-pulse"></span>
            ) : (
              <span className="relative inline-flex rounded-full h-2 w-2 bg-red-500"></span>
            )}
          </span>
          <span className="text-[11px] font-cinzel font-bold text-amber-200 tracking-wide flex items-center gap-1">
            <Camera className="w-3 h-3 text-amber-400" />
            PI 5 CAMERA FEED
          </span>
        </div>

        <div className="flex items-center gap-1 text-stone-400">
          <button
            onClick={() => setShowLogDrawer(!showLogDrawer)}
            className={`p-1 rounded hover:bg-stone-800 transition-colors cursor-pointer ${
              showLogDrawer ? "text-amber-300 bg-amber-950/50" : "text-stone-400"
            }`}
            title="Toggle Console Log Overlay"
          >
            <Terminal className="w-3 h-3" />
          </button>
          <button
            onClick={onToggleMirror}
            className={`p-1 rounded hover:bg-stone-800 transition-colors cursor-pointer ${
              isMirrored ? "text-amber-300" : "text-stone-500"
            }`}
            title="Flip / Mirror Video Feed"
          >
            <FlipHorizontal className="w-3 h-3" />
          </button>
          <button
            onClick={() => onChangeSize(isCompact ? "normal" : "compact")}
            className="p-1 rounded hover:bg-stone-800 text-stone-400 hover:text-stone-200 transition-colors cursor-pointer"
            title={isCompact ? "Expand Feed" : "Compact Feed"}
          >
            {isCompact ? <Maximize2 className="w-3 h-3" /> : <Minimize2 className="w-3 h-3" />}
          </button>
          <button
            onClick={() => onChangeSize("minimized")}
            className="p-1 rounded hover:bg-stone-800 text-stone-400 hover:text-amber-300 transition-colors cursor-pointer"
            title="Minimize to pill"
          >
            <ChevronDown className="w-3 h-3" />
          </button>
        </div>
      </div>

      {/* Main Video Viewport */}
      <div className="relative aspect-[4/3] bg-black overflow-hidden flex items-center justify-center group">
        {stream ? (
          <video
            ref={videoRef}
            playsInline
            muted
            autoPlay
            className={`w-full h-full object-cover ${isMirrored ? "scale-x-[-1]" : ""}`}
          />
        ) : (
          <div className="flex flex-col items-center justify-center p-4 text-center">
            <CameraOff className="w-8 h-8 text-stone-600 mb-1" />
            <span className="text-xs text-stone-400 font-medium">No Camera Feed</span>
            <span className="text-[10px] text-stone-500 mt-0.5">Check Pi 5 /dev/video0 or USB permissions</span>
            <button
              onClick={onReconnect}
              className="mt-2 text-[10px] bg-amber-900/40 hover:bg-amber-800/60 text-amber-200 px-2 py-1 rounded border border-amber-700/60 flex items-center gap-1 cursor-pointer"
            >
              <RefreshCw className="w-2.5 h-2.5" /> Reconnect
            </button>
          </div>
        )}

        {/* Person Detection Bounding Frame / HUD Reticle */}
        {stream && (
          <div className="absolute inset-0 pointer-events-none p-2.5 flex flex-col justify-between">
            {/* Top Reticle Corners */}
            <div className="flex justify-between items-start">
              <div
                className={`w-4 h-4 border-t-2 border-l-2 transition-colors duration-150 ${
                  isPersonDetected ? "border-emerald-400 scale-105" : "border-amber-400/60"
                }`}
              />
              <div
                className={`w-4 h-4 border-t-2 border-r-2 transition-colors duration-150 ${
                  isPersonDetected ? "border-emerald-400 scale-105" : "border-amber-400/60"
                }`}
              />
            </div>

            {/* Center Status Tag */}
            <div className="self-center">
              {isPersonDetected ? (
                <div className="bg-emerald-950/90 border border-emerald-500 text-emerald-200 px-2 py-0.5 rounded-full text-[10px] font-bold tracking-wider uppercase shadow-lg flex items-center gap-1 animate-pulse">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
                  PERSON DETECTED ({(motionLevel * 100).toFixed(0)}%)
                </div>
              ) : isIdle ? (
                <div className="bg-stone-950/80 border border-stone-700 text-amber-300/90 px-2 py-0.5 rounded-full text-[9px] font-mono flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-ping"></span>
                  SCANNING FOR VISITORS
                </div>
              ) : (
                <div className="bg-stone-950/80 border border-stone-700 text-stone-300 px-2 py-0.5 rounded-full text-[9px] font-mono">
                  ACTIVE: {currentState}
                </div>
              )}
            </div>

            {/* Bottom Reticle Corners */}
            <div className="flex justify-between items-end">
              <div
                className={`w-4 h-4 border-b-2 border-l-2 transition-colors duration-150 ${
                  isPersonDetected ? "border-emerald-400 scale-105" : "border-amber-400/60"
                }`}
              />
              <div
                className={`w-4 h-4 border-b-2 border-r-2 transition-colors duration-150 ${
                  isPersonDetected ? "border-emerald-400 scale-105" : "border-amber-400/60"
                }`}
              />
            </div>
          </div>
        )}

        {/* Live Device Info Badge */}
        {stream && (
          <div className="absolute top-1.5 left-1.5 pointer-events-none">
            <span className="bg-black/80 backdrop-blur-sm text-stone-300 text-[9px] px-1.5 py-0.5 rounded font-mono border border-stone-800">
              {deviceInfo ? `${deviceInfo.width}x${deviceInfo.height}` : "640x480"}
            </span>
          </div>
        )}
      </div>

      {/* Optical Activity & Threshold Gauge Bar */}
      <div className="px-2.5 py-1.5 bg-stone-900/95 flex flex-col gap-1 border-t border-stone-800/80">
        <div className="flex items-center justify-between text-[10px] font-mono">
          <span className="text-stone-400 flex items-center gap-1">
            <Eye className="w-3 h-3 text-amber-400" />
            Activity Level:
          </span>
          <span
            className={`font-bold ${
              isPersonDetected ? "text-emerald-400" : "text-amber-300"
            }`}
          >
            {(motionLevel * 100).toFixed(0)}%{" "}
            <span className="text-stone-500 font-normal">/ {(threshold * 100).toFixed(0)}% req</span>
          </span>
        </div>

        {/* Progress bar with threshold marker */}
        <div className="w-full bg-stone-800 h-1.5 rounded-full overflow-hidden relative">
          <div
            className="absolute top-0 bottom-0 w-0.5 bg-amber-400 z-10"
            style={{ left: `${Math.min(100, threshold * 100)}%` }}
            title={`Threshold: ${(threshold * 100).toFixed(0)}%`}
          />
          <div
            className={`h-full transition-all duration-100 ${
              motionLevel >= threshold ? "bg-emerald-400" : "bg-amber-500"
            }`}
            style={{ width: `${Math.min(100, motionLevel * 100)}%` }}
          />
        </div>
      </div>

      {/* Action Footer: Quick Test & Threshold adjustment */}
      <div className="px-2 py-1.5 bg-stone-950 border-t border-stone-800/80 flex items-center justify-between gap-1">
        <button
          onClick={onManualTrigger}
          className="text-[10px] bg-amber-600 hover:bg-amber-500 text-stone-950 font-bold px-2 py-1 rounded flex items-center gap-1 transition-all cursor-pointer font-cinzel"
          title="Simulate seeing a person right now"
        >
          <Zap className="w-2.5 h-2.5 fill-current" />
          Test Wake
        </button>

        <div className="flex items-center gap-1">
          <button
            onClick={() => setShowSensitivityAdjust(!showSensitivityAdjust)}
            className={`p-1 rounded text-[10px] flex items-center gap-1 border transition-colors cursor-pointer ${
              showSensitivityAdjust
                ? "bg-amber-950 text-amber-200 border-amber-700"
                : "bg-stone-900 hover:bg-stone-800 text-stone-400 border-stone-800"
            }`}
            title="Adjust vision sensitivity"
          >
            <Sliders className="w-2.5 h-2.5" />
            <span className="text-[9px]">Sens</span>
          </button>

          <button
            onClick={() => setShowLogDrawer(!showLogDrawer)}
            className={`px-1.5 py-1 rounded text-[9px] font-mono flex items-center gap-1 border transition-colors cursor-pointer ${
              showLogDrawer
                ? "bg-amber-950 text-amber-200 border-amber-700"
                : "bg-stone-900 hover:bg-stone-800 text-stone-400 border-stone-800"
            }`}
          >
            <Terminal className="w-2.5 h-2.5 text-amber-400" />
            Logs ({logs.length})
          </button>
        </div>
      </div>

      {/* Quick Sensitivity Adjust Slider Panel */}
      {showSensitivityAdjust && onChangeThreshold && (
        <div className="px-2.5 py-2 bg-stone-900 border-t border-stone-800 flex flex-col gap-1.5 animate-fadeIn">
          <div className="flex justify-between text-[10px] text-stone-300">
            <span>Detection Sensitivity:</span>
            <span className="font-mono text-amber-300 font-bold">{(threshold * 100).toFixed(0)}%</span>
          </div>
          <input
            type="range"
            min="0.10"
            max="0.90"
            step="0.05"
            value={threshold}
            onChange={(e) => onChangeThreshold(parseFloat(e.target.value))}
            className="w-full h-1 bg-stone-700 rounded-lg appearance-none cursor-pointer accent-amber-500"
          />
          <div className="flex justify-between text-[8px] text-stone-500">
            <span>High Sens (10%)</span>
            <span>Default (45%)</span>
            <span>Low Sens (90%)</span>
          </div>
        </div>
      )}

      {/* Slide-Up Diagnostic Console / Vision Log Drawer */}
      {showLogDrawer && (
        <div className="max-h-48 overflow-y-auto bg-stone-950 border-t border-stone-800 p-2 font-mono text-[10px] flex flex-col gap-1 select-text">
          <div className="flex items-center justify-between pb-1 border-b border-stone-800 text-stone-400">
            <span className="text-[9px] uppercase tracking-wider text-amber-300 font-bold flex items-center gap-1">
              <Terminal className="w-2.5 h-2.5" /> Pi 5 Vision Console Log
            </span>
            <div className="flex items-center gap-2">
              <button
                onClick={onClearLogs}
                className="text-[9px] text-stone-500 hover:text-stone-300 underline cursor-pointer"
              >
                Clear
              </button>
              <button
                onClick={() => setShowLogDrawer(false)}
                className="text-stone-500 hover:text-stone-300 cursor-pointer"
              >
                &times;
              </button>
            </div>
          </div>

          {logs.length === 0 ? (
            <span className="text-stone-600 italic py-2 text-center text-[9px]">
              Waiting for vision sensor events...
            </span>
          ) : (
            logs.map((log) => (
              <div
                key={log.id}
                className={`p-1 rounded text-[9px] leading-tight flex items-start gap-1.5 ${
                  log.level === "success"
                    ? "bg-emerald-950/60 text-emerald-300 border border-emerald-900/60"
                    : log.level === "warn"
                    ? "bg-amber-950/60 text-amber-200 border border-amber-900/60"
                    : log.level === "error"
                    ? "bg-red-950/60 text-red-300 border border-red-900/60"
                    : log.level === "scan"
                    ? "text-stone-400 bg-stone-900/40"
                    : "text-sky-300 bg-sky-950/40"
                }`}
              >
                <span className="text-stone-500 shrink-0 select-none">[{log.timestamp}]</span>
                <span className="flex-1 break-words">{log.message}</span>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
};
