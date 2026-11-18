import assert from "node:assert/strict";
import test from "node:test";
import { ROLE_CARDS, inviteText, newUserProblem, randomPassword, twoPersonBanner } from "./usersModel.js";
import { setLocale } from "./i18n/index.js";

setLocale("zh");   // these tests assert the Chinese words; the English ones are in english.test.js

test("each role card says in one line what the role may do", () => {
  assert.deepEqual(ROLE_CARDS.map((r) => r.key), ["viewer", "builder", "admin"]);
  for (const r of ROLE_CARDS) assert.ok(r.label && r.rights && !r.rights.includes("\n"));
});

test("a random password has 16 characters from mixed classes, and differs between calls", () => {
  let n = 0;
  const rand = () => ((n += 7919) % 1000) / 1000;
  const a = randomPassword(rand);
  const b = randomPassword(rand);
  assert.equal(a.length, 16);
  assert.match(a, /[a-z]/);
  assert.match(a, /[A-Z]/);
  assert.match(a, /[0-9]/);
  assert.doesNotMatch(a, /[0OIl1]/);   // no look-alikes: it gets read aloud and typed
  assert.notEqual(a, b);
});

test("the invitation text carries the login address, the account and the first password", () => {
  const text = inviteText({ origin: "http://10.0.0.5:8787", username: "zhangli", display_name: "张丽", password: "abc", role: "builder" });
  assert.match(text, /http:\/\/10\.0\.0\.5:8787/);
  assert.match(text, /账号：zhangli/);
  assert.match(text, /初始密码：abc/);
  assert.match(text, /张丽/);
  assert.match(text, /建设者/);
  assert.match(text, /第一次登录.*改/);
});

test("the two-person banner is the whole sentence, and says what changes from now on", () => {
  const off = twoPersonBanner({ enabled: false, builders: 3, active: false });
  assert.equal(off.tone, "off");
  assert.match(off.text, /关着/);
  const waiting = twoPersonBanner({ enabled: true, builders: 1, active: false });
  assert.equal(waiting.tone, "waiting");
  assert.match(waiting.text, /只有 1 人/);
  assert.match(waiting.text, /自动按两人确认来$/);
  assert.match(waiting.from, /^从现在起/);
  const on = twoPersonBanner({ enabled: true, builders: 3, active: true });
  assert.equal(on.tone, "on");
  assert.match(on.from, /^从现在起：谁建的.*不能自己确认/);
});

test("the new-user form says what is missing", () => {
  assert.equal(newUserProblem({ username: "", password: "x".repeat(12) }), "要填账号");
  assert.equal(newUserProblem({ username: "a", password: "short" }), "初始密码至少 12 个字符");
  assert.equal(newUserProblem({ username: "a", password: "x".repeat(12) }), "");
});
