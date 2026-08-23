import React, { useEffect, useRef, useState } from "react";
import { CameraConfig, CameraTriggerStatus, VisionLogEntry, CameraDeviceInfo } from "../types";
import {
  Camera,
  CameraOff,
  Eye,
  Activity,
  ShieldCheck,
  Zap,
  Terminal,
  HelpCircle,
  ChevronDown,
  ChevronUp,
  RefreshCw,
  Sliders,
  CheckCircle2,
} from "lucide-react";

interface CameraTriggerProps {
  config: CameraConfig;
  status: CameraTriggerStatus;
  motionLevel: number;
  stream: MediaStream | null;
  cameraError: string | null;
  deviceInfo: CameraDeviceInfo | null;
  logs: VisionLogEntry[];
  canTrigger: boolean;
  onManualTrigger: () => void;
  onReconnect: () => void;
  onChangeThreshold?: (thresh: number) => void;
}

export const CameraTrigger: React.FC<CameraTriggerProps> = ({
  config,
  status,
  motionLevel,
  stream,
  cameraError,
  deviceInfo,
  logs,
  canTrigger,
  onManualTrigger,
  onReconnect,
  onChangeThreshold,
}) => {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [showDebugFeed, setShowDebugFeed] = useState<boolean>(false);
  const [showPiGuide, setShowPiGuide] = useState<boolean>(false);

  // Bind the shared video stream to this preview element
  useEffect(() => {
    if (videoRef.current && stream) {
      videoRef.current.srcObject = stream;
      videoRef.current.play().catch(() => {});
    }
  }, [stream]);

  const streamActive = status.active && !!stream;
  const isTriggered = status.personDetected;
  const threshold = config.hailo_threshold || 0.45;

  return (
    <div className="bg-stone-900/90 border border-stone-800 rounded-xl p-4 flex flex-col gap-3 shadow-lg">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div
            className={`w-7 h-7 rounded-lg flex items-center justify-center border ${
              isTriggered
                ? "bg-emerald-950/80 border-emerald-500 text-emerald-300 animate-pulse"
                : streamActive
                ? "bg-amber-950/60 border-amber-500/50 text-amber-300"
                : "bg-stone-800 border-stone-700 text-stone-500"
            }`}
          >
            <Camera className="w-4 h-4" />
          </div>
          <div>
            <span className="font-cinzel text-xs font-bold tracking-wider text-stone-200 block">
              OPTICAL TRIGGER SENSOR
            </span>
            <span className="text-[10px] text-stone-400 font-mono">
              {deviceInfo ? `${deviceInfo.label.substring(0, 24)}...` : "Vision Module"}
            </span>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <span
            className={`text-[11px] px-2.5 py-0.5 rounded-full font-medium flex items-center gap-1.5 ${
              isTriggered
                ? "bg-emerald-950 text-emerald-300 border border-emerald-700"
                : streamActive
                ? "bg-amber-950 text-amber-300 border border-amber-800/60"
                : "bg-stone-800 text-stone-400"
            }`}
          >
            <span
              className={`w-1.5 h-1.5 rounded-full ${
                isTriggered ? "bg-emerald-400 animate-ping" : streamActive ? "bg-amber-400" : "bg-red-400"
              }`}
            />
            {isTriggered ? "Person Detected" : streamActive ? "Scanning" : "Offline"}
          </span>

          <button
            onClick={() => setShowDebugFeed(!showDebugFeed)}
            className="text-xs text-amber-400 hover:text-amber-300 underline cursor-pointer"
          >
            {showDebugFeed ? "Hide" : "Feed"}
          </button>
        </div>
      </div>

      {cameraError && (
        <div className="text-xs text-amber-300/90 bg-amber-950/40 p-2.5 rounded-lg border border-amber-800/50 flex flex-col gap-1.5">
          <div className="flex items-start justify-between gap-2">
            <span>{cameraError}</span>
            <button
              onClick={onReconnect}
              className="text-[10px] bg-amber-800 hover:bg-amber-700 text-stone-100 px-2 py-0.5 rounded shrink-0 flex items-center gap-1 cursor-pointer"
            >
              <RefreshCw className="w-2.5 h-2.5" /> Retry
            </button>
          </div>
          <span className="text-[10px] text-amber-400/80">
            Click "Pi 5 Setup Guide" below to check Linux camera device permissions.
          </span>
        </div>
      )}

      {/* Motion / Optical Activity Gauge Bar */}
      <div className="flex flex-col gap-1.5 bg-stone-950/60 p-2.5 rounded-lg border border-stone-800/80">
        <div className="flex justify-between items-center text-xs">
          <span className="text-stone-400 flex items-center gap-1 text-[11px]">
            <Activity className="w-3 h-3 text-amber-400" />
            Motion / Person Activity:
          </span>
          <span className="font-mono text-xs font-bold">
            <span className={isTriggered ? "text-emerald-400" : "text-amber-300"}>
              {(motionLevel * 100).toFixed(0)}%
            </span>{" "}
            <span className="text-stone-500 font-normal">/ Req: {(threshold * 100).toFixed(0)}%</span>
          </span>
        </div>

        <div className="w-full bg-stone-800 h-2 rounded-full overflow-hidden relative">
          <div
            className="absolute top-0 bottom-0 w-0.5 bg-amber-400 z-10"
            style={{ left: `${Math.min(100, threshold * 100)}%` }}
            title={`Threshold: ${(threshold * 100).toFixed(0)}%`}
          />
          <div
            className={`h-full transition-all duration-100 ${
              isTriggered ? "bg-emerald-400" : "bg-amber-500"
            }`}
            style={{ width: `${Math.min(100, motionLevel * 100)}%` }}
          />
        </div>

        {/* Quick Sensitivity slider */}
        {onChangeThreshold && (
          <div className="flex items-center gap-2 mt-1">
            <span className="text-[10px] text-stone-500 shrink-0">Threshold:</span>
            <input
              type="range"
              min="0.10"
              max="0.85"
              step="0.05"
              value={threshold}
              onChange={(e) => onChangeThreshold(parseFloat(e.target.value))}
              className="w-full h-1 bg-stone-700 rounded-lg appearance-none cursor-pointer accent-amber-500"
            />
            <span className="text-[10px] font-mono text-amber-300 shrink-0">
              {(threshold * 100).toFixed(0)}%
            </span>
          </div>
        )}
      </div>

      {/* Expandable Video Feed */}
      {showDebugFeed && (
        <div className="relative rounded-lg overflow-hidden border border-stone-700 aspect-video max-h-40 bg-black flex items-center justify-center">
          {streamActive ? (
            <video
              ref={videoRef}
              playsInline
              muted
              autoPlay
              className="w-full h-full object-cover"
            />
          ) : (
            <div className="text-stone-500 text-xs flex flex-col items-center">
              <CameraOff className="w-6 h-6 mb-1" />
              <span>Camera Stream Inactive</span>
            </div>
          )}
          <div className="absolute bottom-1.5 left-2 text-[10px] bg-black/75 px-1.5 py-0.5 rounded text-stone-300 font-mono">
            {isTriggered ? "🟢 PERSON DETECTED" : "🟡 SCANNING"} &middot; {deviceInfo ? `${deviceInfo.width}x${deviceInfo.height}` : "640x480"}
          </div>
        </div>
      )}

      {/* Manual Trigger & Pi 5 Diagnostic Guide Buttons */}
      <div className="flex items-center justify-between gap-2 pt-1">
        <button
          onClick={onManualTrigger}
          disabled={!canTrigger}
          className={`px-3 py-1.5 rounded-lg text-xs font-bold font-cinzel flex items-center gap-1.5 transition-all ${
            canTrigger
              ? "bg-amber-600 hover:bg-amber-500 text-stone-950 cursor-pointer shadow"
              : "bg-stone-800 text-stone-500 cursor-not-allowed"
          }`}
          title="Manually simulate seeing a person walk in front of the camera"
        >
          <Zap className="w-3 h-3 fill-current" />
          Test Wake Sensor
        </button>

        <button
          onClick={() => setShowPiGuide(!showPiGuide)}
          className="text-xs text-stone-400 hover:text-amber-300 flex items-center gap-1 cursor-pointer"
        >
          <HelpCircle className="w-3 h-3 text-amber-400" />
          <span>Pi 5 Camera Guide</span>
          {showPiGuide ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
        </button>
      </div>

      {/* Raspberry Pi 5 Camera Troubleshooting Help Box */}
      {showPiGuide && (
        <div className="bg-stone-950 border border-stone-800 p-3 rounded-lg flex flex-col gap-2 text-[11px] text-stone-300 select-text">
          <div className="flex items-center gap-1.5 font-bold text-amber-300 border-b border-stone-800 pb-1 font-cinzel">
            <Terminal className="w-3.5 h-3.5" /> Raspberry Pi 5 Camera Checklist
          </div>
          <p className="text-stone-400 text-[10px]">
            If running Chromium on Raspberry Pi OS bookworm, verify these terminal checks:
          </p>
          <div className="flex flex-col gap-1 font-mono text-[10px] bg-stone-900/90 p-2 rounded border border-stone-800">
            <span className="text-amber-200 font-semibold">1. List Video Devices:</span>
            <code className="text-emerald-300 bg-black/60 px-1 py-0.5 rounded">v4l2-ctl --list-devices</code>
            <span className="text-amber-200 font-semibold mt-1">2. Test Pi Camera Module (CSI):</span>
            <code className="text-emerald-300 bg-black/60 px-1 py-0.5 rounded">rpicam-hello -t 0</code>
            <span className="text-amber-200 font-semibold mt-1">3. Grant Video Permissions:</span>
            <code className="text-emerald-300 bg-black/60 px-1 py-0.5 rounded">sudo usermod -a -G video $USER</code>
            <span className="text-amber-200 font-semibold mt-1">4. Launch Chromium in Kiosk:</span>
            <code className="text-emerald-300 bg-black/60 px-1 py-0.5 rounded">chromium-browser --use-fake-ui-for-media-stream http://localhost:3000</code>
          </div>
        </div>
      )}
    </div>
  );
};
