# Screamer Maker

1. Wait for motion + Hailo person gate.
2. Capture a frame, detect best face, align to 256×256.
3. Synthesize a "scream" video from the still image using lightweight 2D warps:
   - Lower-half jaw open (vertical stretch below mouth line)
   - Mouth black-out + red tint
   - Eye brighten + small head bob
   - Camera shake + flicker

This avoids heavy GANs and runs on the Pi CPU. If you later provide a FOMM checkpoint and want to offload inference, you can plug it in by swapping `scream_synth.py`.
