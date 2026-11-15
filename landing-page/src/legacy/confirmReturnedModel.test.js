import assert from "node:assert/strict";
import test from "node:test";

import { returnedNote } from "./ontologyConfirmModel.js";

const run = (suggested, confirmation = null) => ({ evaluation: { reference: suggested ? { suggested } : null }, confirmation });

test("重传时，模型又提出的那些你上次判错的对象要说出来", () => {
  assert.equal(returnedNote(run({ types: {}, relations: {}, returned: ["客户", "地区"] })), "模型又提出了你上次判错的：客户、地区");
  assert.equal(returnedNote(run({ types: {}, relations: {}, returned: [] })), "");
  assert.equal(returnedNote(run(null)), "");
});

test("已经重新确认过这次运行之后，就不再提示", () => {
  assert.equal(returnedNote(run({ types: {}, relations: {}, returned: ["客户"] }, { decisions: { types: {} } })), "");
});
