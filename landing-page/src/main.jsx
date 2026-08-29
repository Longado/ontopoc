import React from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App.jsx";
import { StandaloneDemo } from "./StandaloneDemo.jsx";
import { resolveAppSurface } from "./appSurfaceModel.js";
import "./styles.css";

const surface = resolveAppSurface(window.location.pathname);

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    {surface === "landing" ? <App /> : <StandaloneDemo />}
  </React.StrictMode>,
);
