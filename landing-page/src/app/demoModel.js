import { isGuest } from "./authModel.js";

export const QUICK_START_URL = "https://github.com/Longado/ontopoc#quick-start";

/** Questions are off for this person: a guest of a public demo whose server has no model (health says demo_ask: false). */
export const askOff = (user, demoAsk) => isGuest(user) && demoAsk === false;

/** A question carried in the address is not sent for a guest until the demo has said asking is on (unknown counts as off). */
export const holdAsk = (user, demoAsk) => isGuest(user) && demoAsk !== true;

/** Calls `read` until it answers, at most `tries` times, `wait` ms apart; the last failure is thrown. */
export async function readAgain(read, { tries = 3, wait = 700 } = {}) {
  for (let n = 1; ; n += 1) {
    try {
      return await read();
    } catch (error) {
      if (n >= tries) throw error;
      await new Promise((done) => setTimeout(done, wait));
    }
  }
}

/** Reads the health document's demo_ask: true, false, or undefined (absent, or the document is unusable). */
export const demoAskOf = (health) => (typeof health?.demo_ask === "boolean" ? health.demo_ask : undefined);
