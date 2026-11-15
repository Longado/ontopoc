import React from "react";

/** A native select with one arrow of our own, as far from the right edge as the text is from the left. */
export function Select({ value, onChange, children, label, disabled }) {
  return (
    <span className="select">
      <select value={value} onChange={(e) => onChange(e.target.value)} aria-label={label} disabled={disabled}>
        {children}
      </select>
      <svg viewBox="0 0 12 12" width="12" height="12" aria-hidden="true">
        <path d="M2.5 4.5 6 8l3.5-3.5" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </span>
  );
}
