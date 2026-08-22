import React, { useEffect, useRef, useState } from "react";
import { CameraConfig, CameraTriggerStatus } from "../types";
import { Camera, CameraOff, Eye, Activity, ShieldCheck } from "lucide-react";

interface CameraTriggerProps {
  config: CameraConfig;
  onTrigger: (source: "camera") => void;
  status: CameraTriggerStatus;
  setStatus: React.Dispatch<React.SetStateAction<CameraTriggerStatus>>;
  canTrigger: boolean;
}

export const CameraTrigger: React.FC<CameraTriggerProps> = ({
  config,
  onTrigger,
  status,
  setStatus,
  canTrigger,
}) => {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const lastFrameDataRef = useRef<Uint8ClampedArray | null>(null);
  const [streamActive, setStreamActive] = useState<boolean>(false);
  const [cameraError, setCameraError] = useState<string | null>(null);
  const [showDebug, setShowDebug] = useState<boolean>(false);
  const [motionLevel, setMotionLevel] = useState<number>(0);

  // Start / Stop Camera Stream
  useEffect(() => {
    if (!config.enabled) {
      if (videoRef.current && videoRef.current.srcObject) {
        const stream = videoRef.current.srcObject as MediaStream;
        stream.getTracks().forEach((track) => track.stop());
        videoRef.current.srcObject = null;
      }
      setStreamActive(false);
      setStatus((prev) => ({ ...prev, active: false, mode: "disabled" }));
      return;
    }

    let isMounted = true;
    navigator.mediaDevices
      ?.getUserMedia({
        video: { width: { ideal: 320 }, height: { ideal: 240 }, facingMode: "user" },
        audio: false,
      })
      .then((stream) => {
        if (!isMounted) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          videoRef.current.play().catch(() => {});
        }
        setStreamActive(true);
        setCameraError(null);
        setStatus((prev) => ({
          ...prev,
          active: true,
          mode: "motion_detection",
        }));
      })
      .catch((err) => {
        console.warn("Camera access not available or denied:", err);
        if (isMounted) {
          setCameraError("Camera unavailable or permission denied. Voice & Demo wake active.");
          setStatus((prev) => ({
            ...prev,
            active: false,
            mode: config.voice_only_fallback ? "standby" : "disabled",
          }));
        }
      });

    return () => {
      isMounted = false;
      if (videoRef.current && videoRef.current.srcObject) {
        const stream = videoRef.current.srcObject as MediaStream;
        stream.getTracks().forEach((t) => t.stop());
      }
    };
  }, [config.enabled, config.voice_only_fallback, setStatus]);

  // Motion Detection Processing Loop
  useEffect(() => {
    if (!streamActive || !config.enabled) return;

    const interval = setInterval(() => {
      const video = videoRef.current;
      const canvas = canvasRef.current;
      if (!video || !canvas || video.readyState < 2) return;

      const ctx = canvas.getContext("2d", { willReadFrequently: true });
      if (!ctx) return;

      ctx.drawImage(video, 0, 0, 64, 48);
      const frame = ctx.getImageData(0, 0, 64, 48);
      const data = frame.data;

      if (lastFrameDataRef.current) {
        let diffSum = 0;
        const totalPixels = 64 * 48;
        const lastData = lastFrameDataRef.current;

        for (let i = 0; i < data.length; i += 4) {
          // Grayscale luminance difference
          const rDiff = Math.abs(data[i] - lastData[i]);
          const gDiff = Math.abs(data[i + 1] - lastData[i + 1]);
          const bDiff = Math.abs(data[i + 2] - lastData[i + 2]);
          const pixelDiff = (rDiff + gDiff + bDiff) / 3;

          if (pixelDiff > 25) {
            diffSum += pixelDiff;
          }
        }

        const normalizedScore = Math.min(1.0, diffSum / (totalPixels * 35));
        setMotionLevel(normalizedScore);

        const threshold = config.hailo_threshold || 0.45;
        const isTriggered = normalizedScore >= threshold;

        setStatus((prev) => ({
          ...prev,
          motionScore: normalizedScore,
          personDetected: isTriggered,
        }));

        // Fire trigger if motion threshold passed and not currently in cooldown/conversation
        if (isTriggered && canTrigger) {
          onTrigger("camera");
          setStatus((prev) => ({ ...prev, lastTriggerAt: Date.now() }));
        }
      }

      lastFrameDataRef.current = new Uint8ClampedArray(data);
    }, 150);

    return () => clearInterval(interval);
  }, [streamActive, config.enabled, config.hailo_threshold, canTrigger, onTrigger, setStatus]);

  return (
    <div className="bg-stone-900/90 border border-stone-800 rounded-xl p-4 flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Camera className={`w-4 h-4 ${streamActive ? "text-emerald-400" : "text-stone-500"}`} />
          <span className="font-cinzel text-xs font-bold tracking-wider text-stone-200">
            OPTICAL TRIGGER SENSOR
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span
            className={`text-xs px-2 py-0.5 rounded-full font-medium ${
              streamActive
                ? "bg-emerald-950 text-emerald-300 border border-emerald-800/60"
                : "bg-stone-800 text-stone-400"
            }`}
          >
            {streamActive ? "Active Monitor" : "Offline"}
          </span>
          <button
            onClick={() => setShowDebug(!showDebug)}
            className="text-xs text-amber-400 hover:text-amber-300 underline cursor-pointer"
          >
            {showDebug ? "Hide Feed" : "View Feed"}
          </button>
        </div>
      </div>

      {cameraError && (
        <p className="text-xs text-amber-300/80 bg-amber-950/40 p-2 rounded border border-amber-800/50">
          {cameraError}
        </p>
      )}

      {/* Motion Gauge Bar */}
      <div className="flex flex-col gap-1">
        <div className="flex justify-between text-xs text-stone-400">
          <span>Motion / Optical Activity</span>
          <span className="font-mono">
            {(motionLevel * 100).toFixed(0)}% / Thresh: {(config.hailo_threshold * 100).toFixed(0)}%
          </span>
        </div>
        <div className="w-full bg-stone-800 h-2 rounded-full overflow-hidden relative">
          {/* Threshold marker */}
          <div
            className="absolute top-0 bottom-0 w-0.5 bg-amber-400 z-10"
            style={{ left: `${config.hailo_threshold * 100}%` }}
            title="Trigger Threshold"
          />
          <div
            className={`h-full transition-all duration-150 ${
              motionLevel >= config.hailo_threshold ? "bg-amber-400" : "bg-emerald-500"
            }`}
            style={{ width: `${Math.min(100, motionLevel * 100)}%` }}
          />
        </div>
      </div>

      {/* Hidden Video / Canvas for motion processing + optional live preview */}
      <div className={`${showDebug ? "block" : "hidden"} mt-2 relative rounded-lg overflow-hidden border border-stone-700 aspect-video max-h-36 bg-black flex items-center justify-center`}>
        <video
          ref={videoRef}
          playsInline
          muted
          autoPlay
          className="w-full h-full object-cover"
        />
        <canvas ref={canvasRef} width={64} height={48} className="hidden" />
        <div className="absolute bottom-1 left-2 text-[10px] bg-black/70 px-1.5 py-0.5 rounded text-stone-300">
          Person Detection & Motion Grid
        </div>
      </div>
    </div>
  );
};
