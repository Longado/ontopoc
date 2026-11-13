import { useEffect, useState } from "react";

/** Runs `load` when `deps` change: [{status: "loading" | "ready" | "error", data, error, missing}, reload]. Old data stays while the next loads. */
export function useLoad(load, deps) {
  const [state, setState] = useState({ status: "loading" });
  const [round, setRound] = useState(0);
  useEffect(() => {
    let live = true;
    setState((s) => ({ status: "loading", data: s.data }));
    load().then(
      (data) => live && setState({ status: "ready", data }),
      (error) => live && setState({ status: "error", error: error.message, missing: error.code === 404 }),
    );
    return () => {
      live = false;
    };
  }, [...deps, round]);
  return [state, () => setRound((n) => n + 1)];
}
