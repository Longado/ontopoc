import React, { Fragment } from "react";
import { sourceHref } from "./objectModel.js";

/** A source may be one URL or a URL on its own line next to citation notes. */
export function SourceValue({ value }) {
  if (typeof value !== "string" || !/https?:\/\//i.test(value)) return value;
  return value.split("\n").map((line, i) => {
    const href = sourceHref(line);
    return <Fragment key={i}>{i > 0 && "\n"}{href ? <a href={href} target="_blank" rel="noopener noreferrer">{line}</a> : line}</Fragment>;
  });
}
