import React from "react";

// 24x24 line icons, drawn here so the app needs no icon package. Add one by adding its paths below.
const P = {
  home: "M3 11l9-8 9 8M5 10v10h5v-6h4v6h5V10",
  chat: "M4 5h16v11H9l-5 4z",
  board: "M4 4h7v9H4zM13 4h7v5h-7zM13 11h7v9h-7zM4 15h7v5H4z",
  bell: "M6 16V11a6 6 0 0112 0v5l2 2H4zM10 21h4",
  check: "M5 12.5l4.5 4.5L19 7.5",
  "check-circle": "M12 21a9 9 0 100-18 9 9 0 000 18zM8 12.5l3 3 5-6",
  database: "M4 6c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3zM4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3",
  table: "M4 5h16v14H4zM4 10h16M4 15h16M10 5v14",
  plug: "M9 3v5M15 3v5M6 8h12v3a6 6 0 01-12 0zM12 17v4",
  pipeline: "M3 6h5v5H3zM16 13h5v5h-5zM8 8.5h4a2 2 0 012 2V13M14 15.5",
  clock: "M12 21a9 9 0 100-18 9 9 0 000 18zM12 7v5l3 2",
  lineage: "M5 5a2 2 0 100 .01M19 5a2 2 0 100 .01M12 19a2 2 0 100 .01M5 7v2a3 3 0 003 3h8a3 3 0 003-3V7M12 12v5",
  tasks: "M9 6h11M9 12h11M9 18h11M4 6l1 1 2-2M4 12l1 1 2-2M4 18l1 1 2-2",
  cube: "M12 3l8 4.5v9L12 21l-8-4.5v-9zM12 12l8-4.5M12 12v9M12 12L4 7.5",
  link: "M10 14a4 4 0 005.7 0l3-3a4 4 0 00-5.7-5.7l-1 1M14 10a4 4 0 00-5.7 0l-3 3A4 4 0 0011 18.7l1-1",
  apps: "M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM17 14v6M14 17h6",
  bot: "M5 8h14v10H5zM12 4v4M9 13h.01M15 13h.01M9 16h6M3 12v3M21 12v3",
  users: "M9 11a3.5 3.5 0 100-7 3.5 3.5 0 000 7zM2.5 20a6.5 6.5 0 0113 0M16 4.5a3.5 3.5 0 010 6.5M18 14a6.5 6.5 0 013.5 6",
  user: "M12 12a4 4 0 100-8 4 4 0 000 8zM4.5 21a7.5 7.5 0 0115 0",
  shield: "M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z",
  settings: "M4 7h10M18 7h2M4 17h2M10 17h10M16 4v6M8 14v6",
  search: "M11 18a7 7 0 100-14 7 7 0 000 14zM20 20l-4-4",
  "chevron-down": "M6 9l6 6 6-6",
  "chevron-right": "M9 6l6 6-6 6",
  "chevrons-left": "M12 7l-5 5 5 5M18 7l-5 5 5 5",
  "chevrons-right": "M6 7l5 5-5 5M12 7l5 5-5 5",
  menu: "M4 6h16M4 12h16M4 18h16",
  close: "M6 6l12 12M18 6L6 18",
  more: "M5 12h.01M12 12h.01M19 12h.01",
  plus: "M12 5v14M5 12h14",
  upload: "M12 16V4M7 9l5-5 5 5M4 20h16",
  logout: "M15 4h4v16h-4M10 8l-4 4 4 4M6 12h10",
  info: "M12 21a9 9 0 100-18 9 9 0 000 18zM12 11v5M12 8h.01",
  alert: "M12 4l9 16H3zM12 10v4M12 17h.01",
  play: "M7 4l12 8-12 8z",
  trash: "M5 7h14M9 7V4h6v3M7 7l1 13h8l1-13",
  edit: "M4 20h4L19 9l-4-4L4 16zM13 7l4 4",
  external: "M14 4h6v6M20 4l-9 9M18 13v6H5V6h6",
  arrow: "M5 12h14M13 6l6 6-6 6",
  send: "M4 12l16-8-6 16-3-7z",
};

/** An inline SVG icon. Props: `name` (a key of the list above: home chat board bell check check-circle database table plug pipeline clock lineage tasks cube link apps bot users user shield
 * settings search chevron-down chevron-right chevrons-left chevrons-right menu close more plus upload logout info alert play trash edit external arrow send), `size` (px, default 18).
 * It takes the text colour and is hidden from screen readers; put the words next to it or give the button an aria-label. */
export function Icon({ name, size = 18 }) {
  return (
    <svg className="icon" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      <path d={P[name] ?? P.info} />
    </svg>
  );
}

export const ICON_NAMES = Object.keys(P);
