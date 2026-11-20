import { useEffect, useState } from "react";
import { getHealth } from "./api.js";
import { demoAskOf, readAgain } from "./demoModel.js";

let pending = null;
/** Health is read once per page load and the promise kept; a read that failed is not kept, so the next page asks again. */
const readOnce = () => (pending ??= readAgain(getHealth).then(demoAskOf, () => { pending = null; return undefined; }));

/** demo_ask from the service's health: true, false, or undefined (not a demo, or unknown). */
export function useDemoAsk() {
  const [value, setValue] = useState();
  useEffect(() => {
    let live = true;
    readOnce().then((v) => live && setValue(v));
    return () => { live = false; };
  }, []);
  return value;
}

/** True when the signed-in person is a guest and questions are off in this demo. */
export { askOff } from "./demoModel.js";
