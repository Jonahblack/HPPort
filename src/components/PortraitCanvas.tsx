import React, { useEffect, useRef, useState } from "react";
import { PortraitState, RenderConfig, PersonaType, AssetLayerSet } from "../types";

interface PortraitCanvasProps {
  state: PortraitState;
  mouthLevel: number;
  statusText: string;
  cameraMode: string;
  cameraAvailable: boolean;
  config: RenderConfig;
  personaType: PersonaType;
  customLayers?: AssetLayerSet;
  isForceBlinking?: boolean;
  showGuides?: boolean;
  onCanvasClick?: () => void;
}

export const PortraitCanvas: React.FC<PortraitCanvasProps> = ({
  state,
  mouthLevel,
  statusText,
  cameraMode,
  cameraAvailable,
  config,
  personaType,
  customLayers,
  isForceBlinking = false,
  showGuides = false,
  onCanvasClick,
}) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [cursorPos, setCursorPos] = useState<{ x: number; y: number } | null>(null);

  // Cached image elements for uploaded custom layers
  const loadedImagesRef = useRef<Record<string, HTMLImageElement>>({});

  // Preload custom images when customLayers changes
  useEffect(() => {
    if (!customLayers) return;
    const layers: (keyof AssetLayerSet)[] = ["base", "eyesClosed", "mouth1", "mouth2", "mouth3"];
    layers.forEach((layer) => {
      const src = customLayers[layer];
      if (src) {
        const img = new Image();
        img.src = src;
        img.onload = () => {
          loadedImagesRef.current[layer] = img;
        };
      } else {
        delete loadedImagesRef.current[layer];
      }
    });
  }, [customLayers]);

  // Eye and animation state refs
  const animStateRef = useRef({
    eyeOffset: 0,
    eyeVelocity: 0,
    nextBlinkAt: performance.now() + 2500,
    blinkUntil: 0,
    ambientPulse: 0,
    breathOffset: 0,
    targetEyeX: 0,
    targetEyeY: 0,
  });

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let animationFrameId: number;

    const render = () => {
      const now = performance.now();
      const anim = animStateRef.current;

      // Handle Blinking loop (2-5 sec interval, 150ms duration)
      if (now >= anim.nextBlinkAt) {
        anim.blinkUntil = now + 150;
        anim.nextBlinkAt = now + 2000 + Math.random() * 3000;
      }
      const isBlinking = isForceBlinking || now <= anim.blinkUntil;

      // Eye Drift Physics
      const baseEye = Math.sin(now * 0.0012) * 4.0;
      let targetX = baseEye;
      let targetY = Math.cos(now * 0.0008) * 2.0;

      if (cursorPos && canvas) {
        const rect = canvas.getBoundingClientRect();
        const normX = (cursorPos.x - rect.left) / rect.width - 0.5;
        const normY = (cursorPos.y - rect.top) / rect.height - 0.5;
        targetX += normX * 8.0;
        targetY += normY * 5.0;
      }

      anim.eyeVelocity += (targetX - anim.eyeOffset) * 0.08;
      anim.eyeVelocity *= 0.85;
      anim.eyeOffset += anim.eyeVelocity;

      // Breathing subtle idle motion
      anim.breathOffset = Math.sin(now * 0.0018) * 2.5;
      anim.ambientPulse = (Math.sin(now * 0.003) + 1) * 0.5;

      const width = canvas.width;
      const height = canvas.height;

      ctx.clearRect(0, 0, width, height);

      // 1. Background (Dark Manor Wall)
      ctx.fillStyle = `rgb(${config.background_color.join(",")})`;
      ctx.fillRect(0, 0, width, height);

      // Radial vignette
      const wallGrad = ctx.createRadialGradient(
        width / 2,
        height / 2,
        100,
        width / 2,
        height / 2,
        width * 0.7
      );
      wallGrad.addColorStop(0, "rgba(42, 35, 30, 0.4)");
      wallGrad.addColorStop(1, "rgba(8, 7, 10, 0.95)");
      ctx.fillStyle = wallGrad;
      ctx.fillRect(0, 0, width, height);

      // 2. Picture Frame / Outer Canvas Bevel
      const framePaddingX = width * 0.05;
      const framePaddingY = height * 0.05;
      const frameW = width - framePaddingX * 2;
      const frameH = height - framePaddingY * 2;
      const frameRadius = 20;

      ctx.beginPath();
      ctx.roundRect(framePaddingX, framePaddingY, frameW, frameH, frameRadius);
      ctx.fillStyle = "#26201b";
      ctx.fill();

      // Ornate frame rim
      ctx.lineWidth = 12;
      ctx.strokeStyle = `rgb(${config.accent_color.join(",")})`;
      ctx.stroke();

      // Inner lining
      ctx.lineWidth = 2;
      ctx.strokeStyle = "rgba(254, 215, 170, 0.35)";
      ctx.stroke();

      // Inner Canvas Viewport
      const innerX = framePaddingX + 14;
      const innerY = framePaddingY + 14;
      const innerW = frameW - 28;
      const innerH = frameH - 28;

      ctx.save();
      ctx.beginPath();
      ctx.roundRect(innerX, innerY, innerW, innerH, frameRadius - 4);
      ctx.clip();

      const centerX = width / 2;
      const centerY = height / 2 + anim.breathOffset;

      // ================= PHOTOGRAPHIC PORTRAIT / OVERLAY RENDERING =================
      if (personaType === "photo_portrait" || loadedImagesRef.current["base"]) {
        const loaded = loadedImagesRef.current;

        // STEP 1: Draw BASE IMAGE
        if (loaded["base"]) {
          ctx.drawImage(loaded["base"], innerX, innerY, innerW, innerH);
        } else {
          // --- PHOTOREALISTIC BASE RENDER MATCHING USER'S PHOTO ---
          // Wooden cupboard background
          const woodGrad = ctx.createLinearGradient(innerX, innerY, innerX, innerY + innerH);
          woodGrad.addColorStop(0, "#9c633a");
          woodGrad.addColorStop(0.5, "#804c26");
          woodGrad.addColorStop(1, "#5c3314");
          ctx.fillStyle = woodGrad;
          ctx.fillRect(innerX, innerY, innerW, innerH);

          // Wood panel vertical seams
          ctx.strokeStyle = "rgba(60, 30, 10, 0.6)";
          ctx.lineWidth = 3;
          ctx.beginPath();
          ctx.moveTo(centerX - 180, innerY);
          ctx.lineTo(centerX - 180, innerY + innerH);
          ctx.moveTo(centerX + 180, innerY);
          ctx.lineTo(centerX + 180, innerY + innerH);
          ctx.stroke();

          // Dark grey polo shirt & shoulders
          ctx.beginPath();
          ctx.moveTo(centerX - 230, innerY + innerH);
          ctx.lineTo(centerX - 190, centerY + 140);
          ctx.quadraticCurveTo(centerX - 120, centerY + 85, centerX - 55, centerY + 95);
          ctx.lineTo(centerX + 55, centerY + 95);
          ctx.quadraticCurveTo(centerX + 120, centerY + 85, centerX + 190, centerY + 140);
          ctx.lineTo(centerX + 230, innerY + innerH);
          ctx.closePath();
          ctx.fillStyle = "#2c333a";
          ctx.fill();

          // Polo collar flaps
          ctx.beginPath();
          ctx.moveTo(centerX - 55, centerY + 95);
          ctx.lineTo(centerX - 10, centerY + 145);
          ctx.lineTo(centerX - 40, centerY + 160);
          ctx.closePath();
          ctx.fillStyle = "#3e4750";
          ctx.fill();

          ctx.beginPath();
          ctx.moveTo(centerX + 55, centerY + 95);
          ctx.lineTo(centerX + 10, centerY + 145);
          ctx.lineTo(centerX + 40, centerY + 160);
          ctx.closePath();
          ctx.fillStyle = "#3e4750";
          ctx.fill();

          // Neck
          ctx.fillStyle = "#cf9e7e";
          ctx.fillRect(centerX - 42, centerY + 40, 84, 65);

          // Head Back Hair & Ears
          ctx.beginPath();
          ctx.ellipse(centerX, centerY - 70, 110, 130, 0, 0, Math.PI * 2);
          ctx.fillStyle = "#4a3324";
          ctx.fill();

          // Ears
          ctx.beginPath();
          ctx.ellipse(centerX - 98, centerY - 20, 18, 32, -0.1, 0, Math.PI * 2);
          ctx.ellipse(centerX + 98, centerY - 20, 18, 32, 0.1, 0, Math.PI * 2);
          ctx.fillStyle = "#d8a485";
          ctx.fill();

          // Face Oval
          ctx.beginPath();
          ctx.ellipse(centerX, centerY - 25, 92, 115, 0, 0, Math.PI * 2);
          const skinGrad = ctx.createRadialGradient(
            centerX,
            centerY - 50,
            20,
            centerX,
            centerY - 20,
            120
          );
          skinGrad.addColorStop(0, "#f3cbb3");
          skinGrad.addColorStop(0.7, "#e4b193");
          skinGrad.addColorStop(1, "#c58a69");
          ctx.fillStyle = skinGrad;
          ctx.fill();

          // Hair Front / Parting
          ctx.beginPath();
          ctx.moveTo(centerX - 92, centerY - 70);
          ctx.quadraticCurveTo(centerX - 60, centerY - 140, centerX + 10, centerY - 145);
          ctx.quadraticCurveTo(centerX + 70, centerY - 135, centerX + 92, centerY - 65);
          ctx.quadraticCurveTo(centerX + 60, centerY - 105, centerX - 10, centerY - 105);
          ctx.quadraticCurveTo(centerX - 50, centerY - 105, centerX - 92, centerY - 70);
          ctx.closePath();
          ctx.fillStyle = "#432d20";
          ctx.fill();

          // Forehead shading
          ctx.beginPath();
          ctx.ellipse(centerX, centerY - 75, 55, 20, 0, 0, Math.PI * 2);
          ctx.fillStyle = "rgba(255, 255, 255, 0.15)";
          ctx.fill();

          // Eyebrows
          ctx.strokeStyle = "#432d20";
          ctx.lineWidth = 5;
          ctx.beginPath();
          ctx.moveTo(centerX - 68, centerY - 46);
          ctx.quadraticCurveTo(centerX - 42, centerY - 54, centerX - 16, centerY - 46);
          ctx.moveTo(centerX + 16, centerY - 46);
          ctx.quadraticCurveTo(centerX + 42, centerY - 54, centerX + 68, centerY - 46);
          ctx.stroke();

          // Eyes (Open - Neutral)
          const eyeY = centerY - 28;
          const leftEyeX = centerX - 42;
          const rightEyeX = centerX + 42;

          const drawOpenEye = (ex: number) => {
            ctx.beginPath();
            ctx.ellipse(ex, eyeY, 18, 11, 0, 0, Math.PI * 2);
            ctx.fillStyle = "#fbfbfb";
            ctx.fill();
            ctx.strokeStyle = "#5a3a2a";
            ctx.lineWidth = 1.5;
            ctx.stroke();

            // Iris
            ctx.save();
            ctx.beginPath();
            ctx.ellipse(ex, eyeY, 17, 10, 0, 0, Math.PI * 2);
            ctx.clip();

            const pX = ex + anim.eyeOffset * 0.8;
            const pY = eyeY + targetY * 0.5;

            ctx.beginPath();
            ctx.arc(pX, pY, 7.5, 0, Math.PI * 2);
            ctx.fillStyle = "#4a6274";
            ctx.fill();

            // Pupil
            ctx.beginPath();
            ctx.arc(pX, pY, 3.8, 0, Math.PI * 2);
            ctx.fillStyle = "#0f172a";
            ctx.fill();

            // Catchlight
            ctx.beginPath();
            ctx.arc(pX - 2, pY - 2, 1.8, 0, Math.PI * 2);
            ctx.fillStyle = "#ffffff";
            ctx.fill();
            ctx.restore();
          };

          drawOpenEye(leftEyeX);
          drawOpenEye(rightEyeX);

          // Nose Bridge & Tip
          ctx.beginPath();
          ctx.moveTo(centerX, eyeY - 6);
          ctx.lineTo(centerX + 7, centerY + 14);
          ctx.lineTo(centerX - 7, centerY + 14);
          ctx.closePath();
          ctx.fillStyle = "#d39a7b";
          ctx.fill();

          ctx.beginPath();
          ctx.arc(centerX, centerY + 14, 8, 0, Math.PI * 2);
          ctx.fillStyle = "#e2aa8c";
          ctx.fill();

          // Glasses Frame (Black Rectangular)
          ctx.strokeStyle = "#171717";
          ctx.lineWidth = 4;
          ctx.beginPath();
          ctx.roundRect(centerX - 68, eyeY - 17, 52, 34, 6);
          ctx.roundRect(centerX + 16, eyeY - 17, 52, 34, 6);
          ctx.stroke();

          // Glasses Bridge & Temples
          ctx.beginPath();
          ctx.moveTo(centerX - 16, eyeY - 4);
          ctx.lineTo(centerX + 16, eyeY - 4);
          ctx.moveTo(centerX - 68, eyeY - 6);
          ctx.lineTo(centerX - 92, eyeY - 8);
          ctx.moveTo(centerX + 68, eyeY - 6);
          ctx.lineTo(centerX + 92, eyeY - 8);
          ctx.stroke();

          // Glass Glare
          ctx.strokeStyle = "rgba(255, 255, 255, 0.4)";
          ctx.lineWidth = 2;
          ctx.beginPath();
          ctx.moveTo(centerX - 58, eyeY - 12);
          ctx.lineTo(centerX - 30, eyeY + 10);
          ctx.moveTo(centerX + 26, eyeY - 12);
          ctx.lineTo(centerX + 54, eyeY + 10);
          ctx.stroke();

          // Base Neutral Mustache & Beard
          ctx.fillStyle = "#634733";
          ctx.beginPath();
          ctx.ellipse(centerX, centerY + 28, 30, 10, 0, 0, Math.PI * 2);
          ctx.fill();

          // Chin beard
          ctx.beginPath();
          ctx.ellipse(centerX, centerY + 65, 45, 30, 0, 0, Math.PI * 2);
          ctx.fill();

          // Neutral Closed Mouth line
          ctx.strokeStyle = "#4d291e";
          ctx.lineWidth = 2.5;
          ctx.beginPath();
          ctx.moveTo(centerX - 18, centerY + 38);
          ctx.lineTo(centerX + 18, centerY + 38);
          ctx.stroke();
        }

        // STEP 2: For Blinking & Closed Eyes -> Draw EYES CLOSED OVERLAY
        if (isBlinking) {
          if (loaded["eyesClosed"]) {
            ctx.drawImage(loaded["eyesClosed"], innerX, innerY, innerW, innerH);
          } else {
            // EYES CLOSED OVERLAY (Eyelids + Glasses on top of base)
            const eyeY = centerY - 28;
            const leftEyeX = centerX - 42;
            const rightEyeX = centerX + 42;

            ctx.fillStyle = "#e2aa8c";
            ctx.beginPath();
            ctx.ellipse(leftEyeX, eyeY, 20, 13, 0, 0, Math.PI * 2);
            ctx.ellipse(rightEyeX, eyeY, 20, 13, 0, 0, Math.PI * 2);
            ctx.fill();

            // Closed eyelash crease line
            ctx.strokeStyle = "#5a3a2a";
            ctx.lineWidth = 3;
            ctx.beginPath();
            ctx.arc(leftEyeX, eyeY - 1, 14, 0.1, Math.PI - 0.1);
            ctx.arc(rightEyeX, eyeY - 1, 14, 0.1, Math.PI - 0.1);
            ctx.stroke();

            // Glasses over closed eyes
            ctx.strokeStyle = "#171717";
            ctx.lineWidth = 4;
            ctx.beginPath();
            ctx.roundRect(centerX - 68, eyeY - 17, 52, 34, 6);
            ctx.roundRect(centerX + 16, eyeY - 17, 52, 34, 6);
            ctx.moveTo(centerX - 16, eyeY - 4);
            ctx.lineTo(centerX + 16, eyeY - 4);
            ctx.stroke();
          }
        }

        // STEP 3: For Talking -> Draw one of the 3 mouth overlays on top of base
        const mouthCenterY = centerY + 38;
        if (mouthLevel < 0.15) {
          // MOUTH 1 OVERLAY (Closed)
          if (loaded["mouth1"]) {
            ctx.drawImage(loaded["mouth1"], innerX, innerY, innerW, innerH);
          } else {
            // Closed rest mouth + mustache + beard
            ctx.fillStyle = "#634733";
            ctx.beginPath();
            ctx.ellipse(centerX, centerY + 28, 30, 10, 0, 0, Math.PI * 2);
            ctx.ellipse(centerX, centerY + 65, 45, 30, 0, 0, Math.PI * 2);
            ctx.fill();

            ctx.fillStyle = "#a85c4a";
            ctx.beginPath();
            ctx.ellipse(centerX, mouthCenterY, 18, 5, 0, 0, Math.PI * 2);
            ctx.fill();
            ctx.strokeStyle = "#4d291e";
            ctx.lineWidth = 2.5;
            ctx.beginPath();
            ctx.moveTo(centerX - 16, mouthCenterY);
            ctx.lineTo(centerX + 16, mouthCenterY);
            ctx.stroke();
          }
        } else if (mouthLevel < 0.45) {
          // MOUTH 2 OVERLAY (Slightly Open)
          if (loaded["mouth2"]) {
            ctx.drawImage(loaded["mouth2"], innerX, innerY, innerW, innerH);
          } else {
            // Mustache & beard
            ctx.fillStyle = "#634733";
            ctx.beginPath();
            ctx.ellipse(centerX, centerY + 28, 30, 10, 0, 0, Math.PI * 2);
            ctx.ellipse(centerX, centerY + 65, 45, 30, 0, 0, Math.PI * 2);
            ctx.fill();

            // Slightly open mouth cavity
            ctx.fillStyle = "#4a1515";
            ctx.beginPath();
            ctx.ellipse(centerX, mouthCenterY, 18, 9, 0, 0, Math.PI * 2);
            ctx.fill();

            // Upper teeth
            ctx.fillStyle = "#fafafa";
            ctx.fillRect(centerX - 10, mouthCenterY - 7, 20, 5);

            // Lip outline
            ctx.strokeStyle = "#8b4538";
            ctx.lineWidth = 2;
            ctx.beginPath();
            ctx.ellipse(centerX, mouthCenterY, 19, 10, 0, 0, Math.PI * 2);
            ctx.stroke();
          }
        } else {
          // MOUTH 3 OVERLAY (Open)
          if (loaded["mouth3"]) {
            ctx.drawImage(loaded["mouth3"], innerX, innerY, innerW, innerH);
          } else {
            // Mustache & beard
            ctx.fillStyle = "#634733";
            ctx.beginPath();
            ctx.ellipse(centerX, centerY + 26, 32, 10, 0, 0, Math.PI * 2);
            ctx.ellipse(centerX, centerY + 68, 48, 32, 0, 0, Math.PI * 2);
            ctx.fill();

            // Deep mouth cavity
            ctx.fillStyle = "#2d0b0b";
            ctx.beginPath();
            ctx.ellipse(centerX, mouthCenterY + 2, 20, 16, 0, 0, Math.PI * 2);
            ctx.fill();

            // Upper teeth
            ctx.fillStyle = "#fafafa";
            ctx.fillRect(centerX - 12, mouthCenterY - 10, 24, 7);

            // Tongue
            ctx.fillStyle = "#b94a5a";
            ctx.beginPath();
            ctx.ellipse(centerX, mouthCenterY + 11, 11, 6, 0, 0, Math.PI * 2);
            ctx.fill();

            // Lip outline
            ctx.strokeStyle = "#8b4538";
            ctx.lineWidth = 2.5;
            ctx.beginPath();
            ctx.ellipse(centerX, mouthCenterY + 2, 21, 17, 0, 0, Math.PI * 2);
            ctx.stroke();
          }
        }

        // Overlay Alignment Guide Boxes (when toggled in inspector)
        if (showGuides) {
          ctx.setLineDash([4, 4]);
          // Eye overlay region guide
          ctx.strokeStyle = "rgba(56, 189, 248, 0.8)";
          ctx.lineWidth = 1.5;
          ctx.strokeRect(centerX - 80, centerY - 60, 160, 55);
          ctx.fillStyle = "rgba(56, 189, 248, 0.9)";
          ctx.font = "10px monospace";
          ctx.fillText("EYES CLOSED OVERLAY ZONE", centerX - 75, centerY - 65);

          // Mouth overlay region guide
          ctx.strokeStyle = "rgba(245, 158, 11, 0.8)";
          ctx.strokeRect(centerX - 60, centerY + 10, 120, 80);
          ctx.fillStyle = "rgba(245, 158, 11, 0.9)";
          ctx.fillText("MOUTH 1 / 2 / 3 OVERLAY ZONE", centerX - 55, centerY + 100);
          ctx.setLineDash([]);
        }
      } else if (personaType === "talking_fish") {
        // --- TALKING FISH ("Wilhelm") ---
        ctx.beginPath();
        ctx.ellipse(centerX, centerY, 190, 110, 0, 0, Math.PI * 2);
        ctx.fillStyle = "#78350f";
        ctx.fill();
        ctx.strokeStyle = "#451a03";
        ctx.lineWidth = 8;
        ctx.stroke();

        ctx.beginPath();
        ctx.ellipse(centerX, centerY - 5, 140, 60, 0, 0, Math.PI * 2);
        ctx.fillStyle = "#84cc16";
        ctx.fill();
        ctx.strokeStyle = "#14532d";
        ctx.lineWidth = 4;
        ctx.stroke();

        const fishEyeX = centerX + 85;
        const fishEyeY = centerY - 22;
        if (isBlinking) {
          ctx.beginPath();
          ctx.moveTo(fishEyeX - 14, fishEyeY);
          ctx.lineTo(fishEyeX + 14, fishEyeY);
          ctx.strokeStyle = "#1c1917";
          ctx.lineWidth = 4;
          ctx.stroke();
        } else {
          ctx.beginPath();
          ctx.arc(fishEyeX, fishEyeY, 14, 0, Math.PI * 2);
          ctx.fillStyle = "#ffffff";
          ctx.fill();
          ctx.beginPath();
          ctx.arc(fishEyeX + anim.eyeOffset * 0.6, fishEyeY + targetY * 0.4, 6, 0, Math.PI * 2);
          ctx.fillStyle = "#0f172a";
          ctx.fill();
        }

        const fishMouthY = centerY + 10;
        const mouthOpenHeight = 4 + mouthLevel * 28;
        ctx.beginPath();
        ctx.ellipse(centerX + 130, fishMouthY, 12, mouthOpenHeight, Math.PI / 6, 0, Math.PI * 2);
        ctx.fillStyle = "#7f1d1d";
        ctx.fill();
      } else {
        // --- HAUNTED KNIGHT (Lord Cadogan) / WITCH ---
        ctx.beginPath();
        ctx.moveTo(centerX - 150, centerY + 140);
        ctx.quadraticCurveTo(centerX - 130, centerY + 60, centerX - 60, centerY + 65);
        ctx.lineTo(centerX + 60, centerY + 65);
        ctx.quadraticCurveTo(centerX + 130, centerY + 60, centerX + 150, centerY + 140);
        ctx.closePath();
        ctx.fillStyle = personaType === "spooky_witch" ? "#1e1b4b" : "#1e293b";
        ctx.fill();
        ctx.strokeStyle = "#0f172a";
        ctx.lineWidth = 4;
        ctx.stroke();

        const faceW = 120;
        const faceH = 130;
        const faceCenterY = centerY - 15;

        ctx.beginPath();
        ctx.ellipse(centerX, faceCenterY, faceW, faceH, 0, 0, Math.PI * 2);
        ctx.fillStyle = personaType === "spooky_witch" ? "#86efac" : "#d4c1a7";
        ctx.fill();
        ctx.strokeStyle = "#4a392c";
        ctx.lineWidth = 5;
        ctx.stroke();

        // Aristocratic wig curls
        ctx.fillStyle = "#e2e8f0";
        ctx.beginPath();
        ctx.ellipse(centerX - 110, faceCenterY - 20, 30, 70, -0.2, 0, Math.PI * 2);
        ctx.ellipse(centerX + 110, faceCenterY - 20, 30, 70, 0.2, 0, Math.PI * 2);
        ctx.ellipse(centerX, faceCenterY - 105, 90, 40, 0, 0, Math.PI * 2);
        ctx.fill();

        // Eyes
        const eyeY = faceCenterY - 12;
        const leftEyeX = centerX - 44;
        const rightEyeX = centerX + 44;

        if (isBlinking) {
          ctx.strokeStyle = "#1e293b";
          ctx.lineWidth = 4;
          ctx.beginPath();
          ctx.moveTo(leftEyeX - 20, eyeY);
          ctx.lineTo(leftEyeX + 20, eyeY);
          ctx.moveTo(rightEyeX - 20, eyeY);
          ctx.lineTo(rightEyeX + 20, eyeY);
          ctx.stroke();
        } else {
          const drawEye = (ex: number) => {
            ctx.beginPath();
            ctx.ellipse(ex, eyeY, 22, 14, 0, 0, Math.PI * 2);
            ctx.fillStyle = "#f8fafc";
            ctx.fill();
            ctx.strokeStyle = "#3e2723";
            ctx.lineWidth = 2;
            ctx.stroke();

            ctx.beginPath();
            ctx.arc(ex + anim.eyeOffset, eyeY + targetY * 0.5, 9, 0, Math.PI * 2);
            ctx.fillStyle = "#7c3aed";
            ctx.fill();
            ctx.beginPath();
            ctx.arc(ex + anim.eyeOffset, eyeY + targetY * 0.5, 5, 0, Math.PI * 2);
            ctx.fillStyle = "#020617";
            ctx.fill();
          };
          drawEye(leftEyeX);
          drawEye(rightEyeX);
        }

        // Mouth (3-stage mouth flapping)
        const mouthCenterY = faceCenterY + 54;
        const mouthW = 44;
        const mouthH = 5 + mouthLevel * 30;
        ctx.beginPath();
        ctx.ellipse(centerX, mouthCenterY, mouthW, mouthH, 0, 0, Math.PI * 2);
        ctx.fillStyle = `rgb(${config.mouth_color.join(",")})`;
        ctx.fill();
        ctx.strokeStyle = "#451a03";
        ctx.lineWidth = 3;
        ctx.stroke();
      }

      ctx.restore(); // end frame clipping

      // 3. Status Plate at bottom
      const plateW = frameW - 80;
      const plateH = 34;
      const plateX = framePaddingX + 40;
      const plateY = framePaddingY + frameH - plateH - 8;

      ctx.beginPath();
      ctx.roundRect(plateX, plateY, plateW, plateH, 6);
      ctx.fillStyle = "#1e1b18";
      ctx.fill();
      ctx.strokeStyle = `rgb(${config.accent_color.join(",")})`;
      ctx.lineWidth = 2;
      ctx.stroke();

      // State label
      ctx.font = "bold 13px 'Cinzel', serif";
      ctx.fillStyle =
        state === PortraitState.SPEAKING
          ? "#f97316"
          : state === PortraitState.LISTENING
          ? "#38bdf8"
          : state === PortraitState.THINKING
          ? "#eab308"
          : "#e2e8f0";
      ctx.fillText(`STATE: ${state}`, plateX + 16, plateY + 22);

      // Camera indicator
      ctx.font = "11px 'Inter', sans-serif";
      ctx.fillStyle = cameraAvailable ? "#4ade80" : "#a8a29e";
      const camText = `Camera: ${cameraAvailable ? cameraMode : "offline"}`;
      const camWidth = ctx.measureText(camText).width;
      ctx.fillText(camText, plateX + plateW - camWidth - 16, plateY + 22);

      // Subtitle / Spoken speech bubble
      if (statusText) {
        ctx.font = "italic 13px 'MedievalSharp', cursive, serif";
        ctx.fillStyle = "#fef08a";
        const maxLen = 65;
        const displaySub = statusText.length > maxLen ? statusText.substring(0, maxLen) + "..." : statusText;
        const subW = ctx.measureText(`"${displaySub}"`).width;
        ctx.fillText(`"${displaySub}"`, Math.max(plateX + 120, centerX - subW / 2), plateY - 14);
      }

      animationFrameId = requestAnimationFrame(render);
    };

    render();

    return () => {
      cancelAnimationFrame(animationFrameId);
    };
  }, [
    state,
    mouthLevel,
    statusText,
    cameraMode,
    cameraAvailable,
    config,
    personaType,
    cursorPos,
    isForceBlinking,
    showGuides,
  ]);

  return (
    <div
      ref={containerRef}
      id="portrait-canvas-container"
      onClick={onCanvasClick}
      onMouseMove={(e) => setCursorPos({ x: e.clientX, y: e.clientY })}
      onMouseLeave={() => setCursorPos(null)}
      className="relative w-full aspect-[5/3] max-w-4xl mx-auto rounded-2xl overflow-hidden shadow-2xl border-4 border-amber-900/60 cursor-pointer group select-none transition-all duration-300 hover:border-amber-700/80"
    >
      <canvas
        ref={canvasRef}
        id="portrait-main-canvas"
        width={config.width || 800}
        height={config.height || 480}
        className="w-full h-full object-contain block bg-stone-950"
      />

      {/* Floating State Badge */}
      <div className="absolute top-4 left-6 flex items-center gap-2 pointer-events-none bg-stone-900/80 backdrop-blur-md px-3 py-1.5 rounded-full border border-amber-500/30 text-xs text-amber-200">
        <span
          className={`w-2.5 h-2.5 rounded-full ${
            state === PortraitState.SPEAKING
              ? "bg-amber-400 animate-ping"
              : state === PortraitState.LISTENING
              ? "bg-cyan-400 animate-pulse"
              : state === PortraitState.THINKING
              ? "bg-yellow-400 animate-bounce"
              : "bg-emerald-500"
          }`}
        />
        <span className="font-cinzel tracking-wider font-semibold">{state}</span>
      </div>

      <div className="absolute top-4 right-6 flex items-center gap-3 text-xs text-stone-400 bg-stone-900/75 backdrop-blur-sm px-3 py-1.5 rounded-full border border-stone-700 pointer-events-none">
        <span className="hidden sm:inline">Press <kbd className="px-1.5 py-0.5 bg-stone-800 rounded border border-stone-600 text-stone-200">Space</kbd> or click to wake</span>
        <span className="sm:hidden">Tap to wake</span>
      </div>
    </div>
  );
};
