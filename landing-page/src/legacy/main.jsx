import React from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App.jsx";
import { StandaloneDemo } from "./StandaloneDemo.jsx";
import { resolveAppSurface } from "./appSurfaceModel.js";
import "./styles.css";

// the old workbench has no sign-in of its own: when the service answers a call with 401, the new app's sign-in form takes over
const plainFetch = window.fetch.bind(window);
window.fetch = async (...args) => {
  const response = await plainFetch(...args);
  if (response.status === 401) window.location.replace("/");
  return response;
};

// the old landing text is still here, at legacy.html?landing; every other address is the old workbench
const surface = resolveAppSurface(new URLSearchParams(window.location.search).has("landing") ? "/landing" : window.location.pathname);

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    {surface === "landing" ? <App /> : <StandaloneDemo />}
  </React.StrictMode>,
);
