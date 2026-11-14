import { useEffect, useState } from "react";

/** Runs `load` a moment after `key` stops changing; what it returns is {status, data, error}. The last good data stays while the next is worked out. */
export function useSettled(load, key, wait = 350) {
  const [state, setState] = useState({ status: "loading" });
  useEffect(() => {
    let live = true;
    const timer = setTimeout(() => {
      setState((s) => ({ ...s, status: "loading", error: "" }));
      load().then((data) => live && setState({ status: "ready", data }), (e) => live && setState((s) => ({ status: "error", data: s.data, error: e.message })));
    }, wait);
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, [key]);
  return state;
}
