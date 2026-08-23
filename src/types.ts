export enum PortraitState {
  IDLE = "IDLE",
  WAKE_PENDING = "WAKE_PENDING",
  GREETING = "GREETING",
  LISTENING = "LISTENING",
  THINKING = "THINKING",
  SPEAKING = "SPEAKING",
  COOLDOWN = "COOLDOWN",
}

export type PersonaType = "photo_portrait" | "haunted_portrait" | "talking_fish" | "spooky_witch";

export interface AssetLayerSet {
  base: string | null;
  eyesClosed: string | null;
  mouth1: string | null;
  mouth2: string | null;
  mouth3: string | null;
}

export interface LatencyMetrics {
  sttDuration: number;
  llmTimeFirstToken: number;
  llmTokensPerSec: number;
  ttsFirstAudio: number;
  totalTurnLatency: number;
}

export interface RenderConfig {
  width: number;
  height: number;
  fps: number;
  window_title: string;
  background_color: number[];
  accent_color: number[];
  eye_color: number[];
  pupil_color: number[];
  mouth_color: number[];
  status_text_color: number[];
}

export interface CameraConfig {
  enabled: boolean;
  hailo_threshold: number;
  poll_interval_seconds: number;
  cooldown_seconds: number;
  motion_fallback_enabled: boolean;
  voice_only_fallback: boolean;
}

export interface ConversationConfig {
  language: string;
  wake_word: string;
  stop_phrase: string;
  gemini_model: string;
  system_prompt: string;
  listen_timeout_seconds: number;
  phrase_time_limit_seconds: number;
  wake_listen_timeout_seconds: number;
  wake_phrase_limit_seconds: number;
  max_history_messages: number;
  max_silence_turns: number;
  greeting_on_camera: string;
  greeting_on_voice: string;
  silence_prompt: string;
  farewell: string;
}

export interface AppConfig {
  demo_mode: {
    enabled: boolean;
    auto_wake_on_start: boolean;
    auto_wake_interval_seconds: number;
    scripted_user_input: string;
  };
  renderer: RenderConfig;
  camera: CameraConfig;
  conversation: ConversationConfig;
  cooldown: {
    seconds: number;
  };
}

export interface ChatMessage {
  id: string;
  role: "user" | "model" | "system";
  text: string;
  timestamp: string;
  state?: PortraitState;
}

export interface CameraTriggerStatus {
  active: boolean;
  mode: "hailo_ai" | "motion_detection" | "disabled" | "standby";
  personDetected: boolean;
  motionScore: number;
  lastTriggerAt: number | null;
}

export interface VisionLogEntry {
  id: string;
  timestamp: string;
  level: "info" | "success" | "warn" | "error" | "scan";
  message: string;
  score?: number;
  threshold?: number;
}

export interface CameraDeviceInfo {
  label: string;
  width: number;
  height: number;
  fps?: number;
  facingMode?: string;
  isSimulated?: boolean;
}

