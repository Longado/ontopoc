import { useEffect, useState } from "react";

/**
 * Runs `load` when `deps` change: [{status: "loading" | "ready" | "error", data, error, missing}, reload].
 * What was loaded for other deps is never shown for these: it reads as loading. Data stays while the same request is loaded again (reload).
 */
export function useLoad(load, deps) {
  const key = JSON.stringify(deps);
  const [state, setState] = useState({ key, status: "loading" });
  const [round, setRound] = useState(0);
  useEffect(() => {
    let live = true;
    setState((s) => ({ key, status: "loading", data: s.key === key ? s.data : undefined }));
    load().then(
      (data) => live && setState({ key, status: "ready", data }),
      (error) => live && setState({ key, status: "error", error: error.message, missing: error.code === 404 }),
    );
    return () => {
      live = false;
    };
  }, [key, round]);
  return [state.key === key ? state : { key, status: "loading" }, () => setRound((n) => n + 1)];
}
