import { useState, useEffect, useRef, useCallback } from "react";
import { CameraConfig, CameraTriggerStatus, VisionLogEntry, CameraDeviceInfo, PortraitState } from "../types";

interface UseCameraStreamOptions {
  config: CameraConfig;
  onTrigger: (source: "camera") => void;
  currentState: PortraitState;
}

export function useCameraStream({ config, onTrigger, currentState }: UseCameraStreamOptions) {
  const [stream, setStream] = useState<MediaStream | null>(null);
  const [status, setStatus] = useState<CameraTriggerStatus>({
    active: false,
    mode: config.enabled ? "motion_detection" : "disabled",
    personDetected: false,
    motionScore: 0,
    lastTriggerAt: null,
  });
  const [motionLevel, setMotionLevel] = useState<number>(0);
  const [cameraError, setCameraError] = useState<string | null>(null);
  const [deviceInfo, setDeviceInfo] = useState<CameraDeviceInfo | null>(null);
  const [logs, setLogs] = useState<VisionLogEntry[]>([]);
  const [isMirrored, setIsMirrored] = useState<boolean>(true);
  const [showCornerFeed, setShowCornerFeed] = useState<boolean>(true);
  const [cornerFeedSize, setCornerFeedSize] = useState<"compact" | "normal" | "minimized">("normal");

  const hiddenVideoRef = useRef<HTMLVideoElement | null>(null);
  const hiddenCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const lastFrameDataRef = useRef<Uint8ClampedArray | null>(null);
  const lastLogHeartbeatRef = useRef<number>(0);
  const lastDetectionStateRef = useRef<boolean>(false);
  const triggerDebounceRef = useRef<number>(0);

  // Helper to append a vision log to state and browser console
  const addLog = useCallback(
    (
      level: "info" | "success" | "warn" | "error" | "scan",
      message: string,
      score?: number,
      threshold?: number
    ) => {
      const timeStr = new Date().toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      });

      const newEntry: VisionLogEntry = {
        id: Math.random().toString(36).substring(2, 9),
        timestamp: timeStr,
        level,
        message,
        score,
        threshold,
      };

      setLogs((prev) => [newEntry, ...prev.slice(0, 49)]);

      // Print color-coded console logs for Pi 5 & browser debugging
      switch (level) {
        case "success":
          console.log(
            `%c[Pi 5 Vision] 🟢 ${message}`,
            "background: #064e3b; color: #6ee7b7; font-weight: bold; padding: 3px 8px; border-radius: 4px;"
          );
          break;
        case "warn":
          console.warn(
            `%c[Pi 5 Vision] ⚠️ ${message}`,
            "background: #451a03; color: #fde047; font-weight: bold; padding: 2px 6px; border-radius: 4px;"
          );
          break;
        case "error":
          console.error(
            `%c[Pi 5 Vision] ❌ ${message}`,
            "background: #7f1d1d; color: #fca5a5; font-weight: bold; padding: 3px 8px; border-radius: 4px;"
          );
          break;
        case "scan":
          console.log(
            `%c[Pi 5 Vision] 🔍 ${message}`,
            "color: #fbbf24; font-size: 11px; font-family: monospace;"
          );
          break;
        case "info":
        default:
          console.log(
            `%c[Pi 5 Camera] 🎥 ${message}`,
            "background: #1e293b; color: #38bdf8; font-weight: bold; padding: 2px 6px; border-radius: 4px;"
          );
          break;
      }
    },
    []
  );

  // Initialize hidden elements for background optical calculation
  useEffect(() => {
    const video = document.createElement("video");
    video.muted = true;
    video.playsInline = true;
    video.autoplay = true;
    video.style.position = "fixed";
    video.style.top = "-9999px";
    video.style.left = "-9999px";
    video.style.opacity = "0";
    video.style.pointerEvents = "none";
    document.body.appendChild(video);
    hiddenVideoRef.current = video;

    const canvas = document.createElement("canvas");
    canvas.width = 64;
    canvas.height = 48;
    canvas.style.display = "none";
    document.body.appendChild(canvas);
    hiddenCanvasRef.current = canvas;

    return () => {
      if (document.body.contains(video)) document.body.removeChild(video);
      if (document.body.contains(canvas)) document.body.removeChild(canvas);
    };
  }, []);

  // Start or Stop Camera Stream
  const initCamera = useCallback(async () => {
    if (!config.enabled) {
      if (stream) {
        stream.getTracks().forEach((t) => t.stop());
        setStream(null);
      }
      setStatus((prev) => ({ ...prev, active: false, mode: "disabled" }));
      addLog("info", "Camera subsystem disabled in configuration.");
      return;
    }

    try {
      addLog("info", "Requesting camera stream for person detection (Pi 5 / USB / Integrated)...");

      const mediaStream = await navigator.mediaDevices.getUserMedia({
        video: {
          width: { ideal: 640 },
          height: { ideal: 480 },
          facingMode: "user",
        },
        audio: false,
      });

      setStream(mediaStream);
      setCameraError(null);

      if (hiddenVideoRef.current) {
        hiddenVideoRef.current.srcObject = mediaStream;
        await hiddenVideoRef.current.play().catch(() => {});
      }

      const videoTrack = mediaStream.getVideoTracks()[0];
      const settings = videoTrack ? videoTrack.getSettings() : {};
      const devInfo: CameraDeviceInfo = {
        label: videoTrack?.label || "Pi Camera / Video Device",
        width: settings.width || 640,
        height: settings.height || 480,
        fps: settings.frameRate || 30,
        facingMode: settings.facingMode || "user",
      };

      setDeviceInfo(devInfo);
      setStatus((prev) => ({
        ...prev,
        active: true,
        mode: "motion_detection",
      }));

      addLog(
        "info",
        `Camera stream connected: "${devInfo.label}" (${devInfo.width}x${devInfo.height} @ ${Math.round(
          devInfo.fps || 30
        )}fps)`
      );
    } catch (err: any) {
      const errMsg = err?.message || String(err);
      console.warn("Camera init error:", err);
      setCameraError(`Camera unavailable: ${errMsg}`);
      setStatus((prev) => ({
        ...prev,
        active: false,
        mode: config.voice_only_fallback ? "standby" : "disabled",
      }));

      addLog(
        "error",
        `Camera access failed (${errMsg}). If running on Raspberry Pi 5, ensure libcamera / v4l2 device node is accessible (e.g. /dev/video0) or browser permissions are granted.`
      );
    }
  }, [config.enabled, config.voice_only_fallback, addLog, stream]);

  // Trigger init on mount or config toggle
  useEffect(() => {
    initCamera();

    return () => {
      if (stream) {
        stream.getTracks().forEach((t) => t.stop());
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [config.enabled]);

  // Motion Detection Processing Loop
  useEffect(() => {
    if (!stream || !config.enabled) return;

    const interval = setInterval(() => {
      const video = hiddenVideoRef.current;
      const canvas = hiddenCanvasRef.current;
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
          const rDiff = Math.abs(data[i] - lastData[i]);
          const gDiff = Math.abs(data[i + 1] - lastData[i + 1]);
          const bDiff = Math.abs(data[i + 2] - lastData[i + 2]);
          const pixelDiff = (rDiff + gDiff + bDiff) / 3;

          if (pixelDiff > 22) {
            diffSum += pixelDiff;
          }
        }

        const normalizedScore = Math.min(1.0, diffSum / (totalPixels * 30));
        setMotionLevel(normalizedScore);

        const threshold = config.hailo_threshold || 0.45;
        const isTriggered = normalizedScore >= threshold;
        const now = Date.now();

        setStatus((prev) => ({
          ...prev,
          motionScore: normalizedScore,
          personDetected: isTriggered,
        }));

        // Log transition from NO PERSON -> PERSON DETECTED
        if (isTriggered && !lastDetectionStateRef.current) {
          addLog(
            "success",
            `PERSON DETECTED! Motion/Confidence: ${(normalizedScore * 100).toFixed(0)}% (Threshold: ${(
              threshold * 100
            ).toFixed(0)}%) - Optical Wake Triggered!`,
            normalizedScore,
            threshold
          );
        } else if (!isTriggered && lastDetectionStateRef.current) {
          addLog(
            "scan",
            `Person left frame. Returning to scan mode (Activity: ${(normalizedScore * 100).toFixed(0)}%)`,
            normalizedScore,
            threshold
          );
        }

        lastDetectionStateRef.current = isTriggered;

        // Periodic heartbeat log in console every 3 seconds while in IDLE so developer knows it's actively scanning
        if (currentState === PortraitState.IDLE) {
          if (now - lastLogHeartbeatRef.current > 3000) {
            lastLogHeartbeatRef.current = now;
            if (isTriggered) {
              addLog(
                "success",
                `Person in view - Optical activity: ${(normalizedScore * 100).toFixed(0)}% (Thresh: ${(
                  threshold * 100
                ).toFixed(0)}%)`,
                normalizedScore,
                threshold
              );
            } else {
              addLog(
                "scan",
                `Scanning frame... Current optical level: ${(normalizedScore * 100).toFixed(0)}% | Threshold: ${(
                  threshold * 100
                ).toFixed(0)}%`,
                normalizedScore,
                threshold
              );
            }
          }
        }

        // Trigger Wake State if person detected, state is IDLE, and not in cooldown debounce
        if (isTriggered && currentState === PortraitState.IDLE) {
          if (now - triggerDebounceRef.current > 2000) {
            triggerDebounceRef.current = now;
            onTrigger("camera");
            setStatus((prev) => ({ ...prev, lastTriggerAt: now }));
          }
        }
      }

      lastFrameDataRef.current = new Uint8ClampedArray(data);
    }, 120);

    return () => clearInterval(interval);
  }, [stream, config.enabled, config.hailo_threshold, currentState, onTrigger, addLog]);

  const clearLogs = useCallback(() => {
    setLogs([]);
  }, []);

  const manualTrigger = useCallback(() => {
    addLog("success", "Manual Test Trigger fired from Vision Console!");
    onTrigger("camera");
  }, [addLog, onTrigger]);

  return {
    stream,
    status,
    motionLevel,
    cameraError,
    deviceInfo,
    logs,
    isMirrored,
    setIsMirrored,
    showCornerFeed,
    setShowCornerFeed,
    cornerFeedSize,
    setCornerFeedSize,
    initCamera,
    clearLogs,
    manualTrigger,
    addLog,
  };
}
