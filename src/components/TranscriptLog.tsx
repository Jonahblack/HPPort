import React from "react";
import { ChatMessage, PortraitState } from "../types";
import { MessageSquare, Trash2, Bot, User, Sparkles, Volume2 } from "lucide-react";

interface TranscriptLogProps {
  messages: ChatMessage[];
  currentState: PortraitState;
  onClear: () => void;
  onReplay: (text: string) => void;
}

const FSM_STEPS: PortraitState[] = [
  PortraitState.IDLE,
  PortraitState.WAKE_PENDING,
  PortraitState.GREETING,
  PortraitState.LISTENING,
  PortraitState.THINKING,
  PortraitState.SPEAKING,
  PortraitState.COOLDOWN,
];

export const TranscriptLog: React.FC<TranscriptLogProps> = ({
  messages,
  currentState,
  onClear,
  onReplay,
}) => {
  return (
    <div className="bg-stone-900/90 border border-stone-800 rounded-xl p-4 flex flex-col gap-3">
      {/* FSM State Indicator Ribbon */}
      <div className="flex flex-col gap-1.5 pb-3 border-b border-stone-800">
        <span className="font-cinzel text-[11px] tracking-wider text-stone-400 font-bold uppercase">
          Finite State Machine (FSM) Lifecycle
        </span>
        <div className="grid grid-cols-7 gap-1">
          {FSM_STEPS.map((st) => {
            const isCurrent = currentState === st;
            return (
              <div
                key={st}
                className={`text-[10px] text-center py-1 rounded font-mono font-medium transition-all ${
                  isCurrent
                    ? "bg-amber-600 text-amber-50 font-bold shadow-md shadow-amber-900/40 ring-1 ring-amber-400"
                    : "bg-stone-800 text-stone-400"
                }`}
              >
                {st}
              </div>
            );
          })}
        </div>
      </div>

      {/* Transcript Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <MessageSquare className="w-4 h-4 text-amber-400" />
          <span className="font-cinzel text-xs font-bold tracking-wider text-stone-200">
            DIALOGUE TRANSCRIPT
          </span>
          <span className="text-xs text-stone-500 font-mono">({messages.length})</span>
        </div>
        {messages.length > 0 && (
          <button
            onClick={onClear}
            className="text-xs text-stone-400 hover:text-rose-400 flex items-center gap-1 transition-colors cursor-pointer"
          >
            <Trash2 className="w-3.5 h-3.5" />
            <span>Clear</span>
          </button>
        )}
      </div>

      {/* Messages Scroll View */}
      <div className="max-h-56 overflow-y-auto space-y-2 pr-1">
        {messages.length === 0 ? (
          <div className="text-center py-6 text-xs text-stone-500 italic">
            No dialogue recorded yet. Speak the wake word, step in front of the camera, or press Space to initiate contact.
          </div>
        ) : (
          messages.map((msg) => (
            <div
              key={msg.id}
              className={`p-2.5 rounded-lg text-xs flex flex-col gap-1 transition-all ${
                msg.role === "user"
                  ? "bg-stone-800/80 border border-stone-700/60 ml-4"
                  : msg.role === "model"
                  ? "bg-amber-950/40 border border-amber-900/50 mr-4 text-amber-100"
                  : "bg-stone-900 text-stone-400 italic text-[11px]"
              }`}
            >
              <div className="flex items-center justify-between text-[10px] text-stone-400">
                <span className="flex items-center gap-1 font-semibold capitalize">
                  {msg.role === "user" ? (
                    <User className="w-3 h-3 text-stone-300" />
                  ) : (
                    <Sparkles className="w-3 h-3 text-amber-400" />
                  )}
                  {msg.role === "user" ? "Mortal" : "Portrait"}
                </span>
                <div className="flex items-center gap-2">
                  <span>{msg.timestamp}</span>
                  {msg.role === "model" && (
                    <button
                      onClick={() => onReplay(msg.text)}
                      title="Replay Voice"
                      className="text-amber-400/80 hover:text-amber-300 transition-colors"
                    >
                      <Volume2 className="w-3 h-3" />
                    </button>
                  )}
                </div>
              </div>
              <p className="leading-relaxed whitespace-pre-wrap">{msg.text}</p>
            </div>
          ))
        )}
      </div>
    </div>
  );
};
