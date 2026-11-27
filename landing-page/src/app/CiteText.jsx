import React from "react";
import { citeLine, citeParts, citeSource } from "./typeModel.js";

/** A rule's citation: the document and where in it, then the whole sentence with the quoted part marked; while it does not stand, why (no quote). */
export function CiteText({ cite, className = "" }) {
  if (!cite) return null;
  if (cite.stale) return <span className={`warn ${className}`}>{citeLine(cite)}</span>;
  const [before, quoted, after] = citeParts(cite);
  return <span className={`muted ${className}`}>{citeSource(cite)} “{before}<mark>{quoted}</mark>{after}”</span>;
}
