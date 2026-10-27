import React, { useState } from 'react';

export interface PianoRollNote {
  startTime: number;
  endTime: number;
  duration: number;
  pitchMidi: number;
  noteName: string;
}

interface Props {
  pianoRoll: PianoRollNote[];
  duration?: number;
}

export const PianoRollConsole: React.FC<Props> = ({ pianoRoll, duration = 10 }) => {
  const [selectedNote, setSelectedNote] = useState<PianoRollNote | null>(null);

  if (!pianoRoll || pianoRoll.length === 0) {
    return null;
  }

  const minMidi = Math.min(...pianoRoll.map(n => n.pitchMidi)) - 2;
  const maxMidi = Math.max(...pianoRoll.map(n => n.pitchMidi)) + 2;
  const maxTime = Math.max(...pianoRoll.map(n => n.endTime), duration);

  const svgHeight = 120;
  const svgWidth = 400;

  return (
    <div className="mt-3 bg-zinc-950 border border-zinc-800 rounded-lg overflow-hidden shadow-lg">
      <div className="px-3 py-2 bg-zinc-900 border-b border-zinc-800 flex justify-between items-center">
        <span className="text-[10px] font-mono tracking-wider uppercase text-cyan-400 font-semibold">
          Graphical Mode // Pitch Console
        </span>
        {selectedNote && (
          <span className="text-[10px] font-mono text-zinc-400">
            {selectedNote.noteName} @ {selectedNote.startTime}s
          </span>
        )}
      </div>
      <div className="relative overflow-hidden p-2 bg-zinc-950">
        <svg viewBox={`0 0 ${svgWidth} ${svgHeight}`} className="w-full h-24 bg-zinc-900/40 rounded">
          {[...Array(4)].map((_, i) => (
            <line key={i} x1={0} y1={(svgHeight / 4) * i} x2={svgWidth} y2={(svgHeight / 4) * i} stroke="#27272a" strokeWidth="1" strokeDasharray="2 2" />
          ))}
          {pianoRoll.map((note, idx) => {
            const x = (note.startTime / maxTime) * svgWidth;
            const w = Math.max(4, (note.duration / maxTime) * svgWidth);
            const y = svgHeight - ((note.pitchMidi - minMidi) / (maxMidi - minMidi)) * svgHeight;
            return (
              <g key={idx} onClick={() => setSelectedNote(note)} className="cursor-pointer group">
                <rect x={x} y={y - 4} width={w} height={8} rx={2} className="fill-cyan-500/80 hover:fill-cyan-400 transition-colors stroke-cyan-300 stroke-1" />
              </g>
            );
          })}
        </svg>
      </div>
    </div>
  );
};
