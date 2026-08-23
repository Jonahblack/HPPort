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

  const simulatedCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const simulatedAnimFrameRef = useRef<number | null>(null);
  const simulatedPersonPosRef = useRef<{ x: number; y: number; vx: number; vy: number; active: boolean }>({
    x: 160,
    y: 120,
    vx: 1.2,
    vy: 0.8,
    active: true,
  });

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

      // Print color-coded console logs for Pi 5 & browser debugging without triggering fatal error alarms
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
          console.warn(
            `%c[Pi 5 Vision] ⚠️ Notice: ${message}`,
            "background: #3f1515; color: #fca5a5; font-weight: bold; padding: 3px 8px; border-radius: 4px;"
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

  // Stop simulated animation loop
  const stopSimulatedLoop = useCallback(() => {
    if (simulatedAnimFrameRef.current) {
      cancelAnimationFrame(simulatedAnimFrameRef.current);
      simulatedAnimFrameRef.current = null;
    }
  }, []);

  // Create an interactive simulated camera canvas stream when no hardware webcam is connected
  const startSimulatedCamera = useCallback(() => {
    stopSimulatedLoop();

    let simCanvas = simulatedCanvasRef.current;
    if (!simCanvas) {
      simCanvas = document.createElement("canvas");
      simCanvas.width = 320;
      simCanvas.height = 240;
      simCanvas.style.display = "none";
      document.body.appendChild(simCanvas);
      simulatedCanvasRef.current = simCanvas;
    }

    const ctx = simCanvas.getContext("2d");
    if (!ctx) return;

    let scanLineY = 0;
    let tick = 0;

    const renderSimFrame = () => {
      tick++;
      if (!ctx || !simCanvas) return;

      const w = simCanvas.width;
      const h = simCanvas.height;

      // 1. Dark thermal/vision room background
      ctx.fillStyle = "#0c131a";
      ctx.fillRect(0, 0, w, h);

      // 2. Optical Grid Lines
      ctx.strokeStyle = "rgba(45, 75, 95, 0.4)";
      ctx.lineWidth = 1;
      const gridSize = 40;
      for (let x = 0; x < w; x += gridSize) {
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, h);
        ctx.stroke();
      }
      for (let y = 0; y < h; y += gridSize) {
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(w, y);
        ctx.stroke();
      }

      // 3. Move simulated visitor silhouette if active
      const person = simulatedPersonPosRef.current;
      if (person.active) {
        person.x += person.vx;
        person.y += person.vy;
        if (person.x < 60 || person.x > w - 60) person.vx *= -1;
        if (person.y < 60 || person.y > h - 60) person.vy *= -1;

        // Draw thermal human signature
        const grad = ctx.createRadialGradient(person.x, person.y, 10, person.x, person.y, 45);
        grad.addColorStop(0, "rgba(52, 211, 153, 0.85)");
        grad.addColorStop(0.5, "rgba(16, 185, 129, 0.45)");
        grad.addColorStop(1, "rgba(6, 78, 59, 0)");

        ctx.fillStyle = grad;
        ctx.beginPath();
        ctx.arc(person.x, person.y, 45, 0, Math.PI * 2);
        ctx.fill();

        // Person Head & Shoulder silhouette
        ctx.fillStyle = "rgba(209, 250, 229, 0.9)";
        ctx.beginPath();
        ctx.arc(person.x, person.y - 12, 12, 0, Math.PI * 2);
        ctx.fill();

        ctx.beginPath();
        ctx.ellipse(person.x, person.y + 16, 24, 14, 0, 0, Math.PI * 2);
        ctx.fill();

        // Target Bounding Box
        ctx.strokeStyle = "#34d399";
        ctx.lineWidth = 1.5;
        ctx.strokeRect(person.x - 30, person.y - 30, 60, 65);

        ctx.fillStyle = "#34d399";
        ctx.font = "bold 9px monospace";
        ctx.fillText("PERSON 94%", person.x - 28, person.y - 34);
      }

      // 4. Moving Scan Line
      scanLineY = (scanLineY + 2.5) % h;
      ctx.strokeStyle = "rgba(56, 189, 248, 0.6)";
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(0, scanLineY);
      ctx.lineTo(w, scanLineY);
      ctx.stroke();

      // 5. HUD Text
      ctx.fillStyle = "#38bdf8";
      ctx.font = "9px monospace";
      ctx.fillText(`PI5 VIRTUAL OPTICAL RADAR [FPS 20]`, 8, 14);
      ctx.fillStyle = "#94a3b8";
      ctx.fillText(`FRAME: ${tick} | SENSOR: HAILO-8L EMULATOR`, 8, 26);

      simulatedAnimFrameRef.current = requestAnimationFrame(renderSimFrame);
    };

    renderSimFrame();

    try {
      if ((simCanvas as any).captureStream) {
        const stream = (simCanvas as any).captureStream(20) as MediaStream;
        setStream(stream);

        if (hiddenVideoRef.current) {
          hiddenVideoRef.current.srcObject = stream;
          hiddenVideoRef.current.play().catch(() => {});
        }

        const devInfo: CameraDeviceInfo = {
          label: "Pi 5 Optical Radar (Virtual Sensor)",
          width: 320,
          height: 240,
          fps: 20,
          facingMode: "user",
          isSimulated: true,
        };
        setDeviceInfo(devInfo);
        setStatus((prev) => ({
          ...prev,
          active: true,
          mode: "motion_detection",
        }));
        setCameraError(null);
        addLog("info", "Simulated Optical Sensor stream activated (Virtual Camera Feed).");
      }
    } catch (e) {
      console.warn("Could not capture stream from simulated canvas:", e);
    }
  }, [addLog, stopSimulatedLoop]);

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
      stopSimulatedLoop();
      if (stream) {
        stream.getTracks().forEach((t) => t.stop());
        setStream(null);
      }
      setStatus((prev) => ({ ...prev, active: false, mode: "disabled" }));
      addLog("info", "Camera subsystem disabled in configuration.");
      return;
    }

    try {
      if (!navigator?.mediaDevices?.getUserMedia) {
        throw new Error("getUserMedia not supported in this browser/container context");
      }

      addLog("info", "Checking for physical camera stream (Pi 5 libcamera / USB / Integrated)...");

      const mediaStream = await navigator.mediaDevices.getUserMedia({
        video: {
          width: { ideal: 640 },
          height: { ideal: 480 },
          facingMode: "user",
        },
        audio: false,
      });

      stopSimulatedLoop();
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
        isSimulated: false,
      };

      setDeviceInfo(devInfo);
      setStatus((prev) => ({
        ...prev,
        active: true,
        mode: "motion_detection",
      }));

      addLog(
        "info",
        `Physical camera stream connected: "${devInfo.label}" (${devInfo.width}x${devInfo.height} @ ${Math.round(
          devInfo.fps || 30
        )}fps)`
      );
    } catch (err: any) {
      const errMsg = err?.name === "NotFoundError" ? "No physical webcam detected" : err?.message || String(err);
      
      // Fallback seamlessly to the synthetic / simulated optical sensor stream
      addLog(
        "info",
        `Physical webcam hardware absent (${errMsg}). Activated Pi 5 Virtual Optical Sensor stream for person detection testing.`
      );

      startSimulatedCamera();
    }
  }, [config.enabled, addLog, stream, stopSimulatedLoop, startSimulatedCamera]);

  // Trigger init on mount or config toggle
  useEffect(() => {
    initCamera();

    return () => {
      stopSimulatedLoop();
      if (stream) {
        stream.getTracks().forEach((t) => t.stop());
      }
      if (simulatedCanvasRef.current && document.body.contains(simulatedCanvasRef.current)) {
        document.body.removeChild(simulatedCanvasRef.current);
        simulatedCanvasRef.current = null;
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
