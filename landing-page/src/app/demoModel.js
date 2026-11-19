import { isGuest } from "./authModel.js";

export const QUICK_START_URL = "https://github.com/Longado/ontopoc#quick-start";

/** Questions are off for this person: a guest of a public demo whose server has no model (health says demo_ask: false). */
export const askOff = (user, demoAsk) => isGuest(user) && demoAsk === false;

/** Reads the health document's demo_ask: true, false, or undefined (absent, or the document is unusable). */
export const demoAskOf = (health) => (typeof health?.demo_ask === "boolean" ? health.demo_ask : undefined);
