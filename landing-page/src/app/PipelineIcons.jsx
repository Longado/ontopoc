import React from "react";

// The pipeline pages' own small icons (24x24 line icons, same drawing as ui/Icon.jsx): one per kind of step, the column types of the preview, and the canvas controls.
const PATHS = {
  input: "M4 6c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3zM4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3",
  join: "M9 6.5a5.5 5.5 0 100 11 5.5 5.5 0 000-11zM15 6.5a5.5 5.5 0 100 11 5.5 5.5 0 000-11z",
  transform: "M7 7h13M16 3l4 4-4 4M17 17H4M8 13l-4 4 4 4",
  filter: "M4 5h16l-6 8v6l-4-2v-4z",
  aggregate: "M18 5H6l6 7-6 7h12",
  union: "M6 3v6a6 6 0 006 6M18 3v6a6 6 0 01-6 6v6",
  split: "M12 3v6M12 9l-6 6v6M12 9l6 6v6",
  llm: "M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8zM19 16l.8 2.2L22 19l-2.2.8L19 22l-.8-2.2L16 19l2.2-.8z",
  output: "M12 4v11M7 10l5 5 5-5M4 20h16",
  branch: "M6 4v8a4 4 0 004 4h8M15 12l3 4-3 4",
  minus: "M5 12h14",
  plus: "M12 5v14M5 12h14",
  fit: "M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5",
  steps: "M4 6h16M4 12h16M4 18h10",
  maximize: "M14 4h6v6M10 20H4v-6M20 4l-7 7M4 20l7-7",
  restore: "M20 10h-6V4M4 14h6v6M14 10l7-7M10 14l-7 7",
  tall: "M7 9l5-5 5 5M7 15l5 5 5-5",
  close: "M6 6l12 12M18 6L6 18",
  check: "M5 12.5l4.5 4.5L19 7.5",
  alert: "M12 4l9 16H3zM12 10v4M12 17h.01",
  cross: "M12 21a9 9 0 100-18 9 9 0 000 18zM9 9l6 6M15 9l-6 6",
  success: "M12 21a9 9 0 100-18 9 9 0 000 18zM8 12.5l3 3 5-6",
  info: "M12 21a9 9 0 100-18 9 9 0 000 18zM12 11v5M12 8h.01",
  calendar: "M4 6h16v14H4zM4 10h16M8 3v4M16 3v4",
  clock: "M12 21a9 9 0 100-18 9 9 0 000 18zM12 7v5l3 2",
  toggle: "M7 8h10a4 4 0 010 8H7a4 4 0 010-8zM17 12h.01",
  sparkle: "M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z",
  play: "M7 4l12 8-12 8z",
  stop: "M6 6h12v12H6z",
  trash: "M5 7h14M9 7V4h6v3M7 7l1 13h8l1-13",
  external: "M14 4h6v6M20 4l-9 9M18 13v6H5V6h6",
  more: "M5 12h.01M12 12h.01M19 12h.01",
  pipeline: "M3 6h5v5H3zM16 13h5v5h-5zM8 8.5h4a2 2 0 012 2V13",
  grid: "M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z",
};

/** A drawn icon of this file. `size` in px (default 16). */
export function PIcon({ name, size = 16 }) {
  return (
    <svg className="icon" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      <path d={PATHS[name] ?? PATHS.info} />
    </svg>
  );
}

/** What a step looks like on the canvas: its kind (the colour of its chip and the icon). A transform with one operator takes the look of that operator (a filter, an aggregation). */
export function kindOf(step) {
  if (step?.type === "transform" && step.operators?.length === 1) {
    if (step.operators[0].op === "filter") return "filter";
    if (step.operators[0].op === "aggregate") return "aggregate";
  }
  return step?.type ?? "transform";
}

/** The 20px chip of a step: the kind's icon in the kind's colour on a tint of it. */
export function KindChip({ step, kind = kindOf(step), size = 20 }) {
  return <span className={`pl-chip k-${kind}`} style={{ width: size, height: size }} aria-hidden="true"><PIcon name={kind} size={Math.round(size * 0.7)} /></span>;
}

const TYPE_ICON = { date: "calendar", month: "calendar", datetime: "clock", boolean: "toggle" };
const TYPE_GLYPH = { text: "A", integer: "123", decimal: "1.0" };

/** The type of a column as a small mark: A for text, 123, 1.0, a calendar, a clock, a toggle. */
export function TypeMark({ type }) {
  const icon = TYPE_ICON[type];
  return <span className="pl-type" aria-hidden="true">{icon ? <PIcon name={icon} size={13} /> : TYPE_GLYPH[type] ?? "?"}</span>;
}
