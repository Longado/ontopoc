import assert from "node:assert/strict";
import test from "node:test";

import { setLocale } from "./i18n/index.js";
import { groupByType, healthOf, matchLine, sentenceParts, sortProblemsFirst } from "./relationModel.js";

setLocale("en");

const order = { id: "order_customer", from: "order", to: "customer", from_name: "Order", to_name: "Customer", cardinality: "many_to_one", state: "confirmed", numbers: { rows: 160, matched: 157, unmatched: 3, fan_keys: 0, many_repeats: 0 } };
const clean = { ...order, id: "order_product", to: "product", to_name: "Product", numbers: { rows: 160, matched: 160, unmatched: 0, fan_keys: 0, many_repeats: 0 } };

test("a relation reads as a sentence with its two types picked out", () => {
  assert.deepEqual(sentenceParts(order), ["Each ", "Order", " belongs to one ", "Customer"]);
  assert.deepEqual(sentenceParts({ ...order, cardinality: "one_to_many", from_name: "Customer", to_name: "Order" }), ["Each ", "Customer", " has many ", "Order"]);
  assert.deepEqual(sentenceParts({ ...order, cardinality: "one_to_one" }), ["Each ", "Order", " pairs with one ", "Customer"]);
});

test("match health is ok, warn, bad or unknown from the numbers alone", () => {
  assert.equal(healthOf(clean), "ok");
  assert.equal(healthOf(order), "warn");
  assert.equal(healthOf({ ...order, numbers: { rows: 100, matched: 40, unmatched: 60, fan_keys: 0, many_repeats: 0 } }), "bad");
  assert.equal(healthOf({ ...clean, numbers: { ...clean.numbers, fan_keys: 2 } }), "warn");
  assert.equal(healthOf({ ...order, numbers: null }), "unknown");
  assert.equal(healthOf({ ...order, numbers: { rows: 0, matched: 0, unmatched: 0, fan_keys: 0, many_repeats: 0 } }), "unknown");
});

test("the match line counts the many side finding the one side, with the unmatched keys when known", () => {
  assert.equal(matchLine(order, [{ key: "KH099", rows: 3 }]), "157 of 160 Order find their Customer · 3 don't (KH099)");
  assert.equal(matchLine(order, []), "157 of 160 Order find their Customer · 3 don't");
  assert.equal(matchLine(clean, []), "All 160 Order find their Product");
  assert.equal(matchLine({ ...order, numbers: null }, []), "Can't be checked right now");
  assert.equal(matchLine({ ...order, cardinality: "one_to_many", from_name: "Customer", to_name: "Order" }, []), "157 of 160 Order find their Customer · 3 don't");
});

test("problems sort first and keep their order otherwise; groups are by the type the relation starts from", () => {
  const waiting = { ...clean, id: "w", state: "proposed" };
  const sent = { ...clean, id: "s", state: "rejected" };
  assert.deepEqual(sortProblemsFirst([clean, waiting, order, sent]).map((r) => r.id), ["s", "order_customer", "w", "order_product"]);
  const ticket = { ...clean, id: "t", from: "ticket", from_name: "Ticket" };
  const groups = groupByType([ticket, order, clean]);
  assert.deepEqual(groups.map((g) => [g.name, g.items.map((r) => r.id)]), [["Order", ["order_customer", "order_product"]], ["Ticket", ["t"]]]);
});
