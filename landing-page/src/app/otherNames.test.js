import assert from "node:assert/strict";
import test from "node:test";

import { derivedPayload, emptyDerivedForm, formFromLine } from "./derivedModel.js";
import { demoQuestions } from "./homeModel.js";
import { setLocale } from "./i18n/index.js";
import { alsoCalled, otherNamesFrom, otherNamesText, typePayload } from "./typeModel.js";
import { emptyViewForm, viewPayload } from "./viewModel.js";

setLocale("zh");

test("other names are typed in one box, separated by commas or 、, and read back the same way", () => {
  assert.deepEqual(otherNamesFrom(" 订单， 销售单,sales order 、 订单 ;"), ["订单", "销售单", "sales order"]);   // a repeat is kept once
  assert.deepEqual(otherNamesFrom(""), []);
  assert.equal(otherNamesText(["订单", "销售单"]), "订单、销售单");
  assert.equal(alsoCalled(["订单", "销售单"]), "又称：订单、销售单");
  assert.equal(alsoCalled([]), "");
  assert.equal(alsoCalled(undefined), "");
  setLocale("en");
  try {
    assert.equal(otherNamesText(["订单", "sales order"]), "订单, sales order");
    assert.equal(alsoCalled(["订单"]), "Also called: 订单");
  } finally {
    setLocale("zh");
  }
});

test("the type form sends the other names of the type, of each property and of each meaning; a form that has none to say sends none", () => {
  const form = {
    english: "order", name: "Order", otherNames: "订单", description: "", dataset: "orders", key: ["order_id"],
    columns: [
      { name: "order_id", type: "text", include: true, label: "", otherNames: "订单号", declared: "text", enum: false },
      { name: "status_code", type: "integer", include: true, label: "", otherNames: "", declared: "integer", enum: true, meanings: { 3: "Delivered", 4: "Cancelled" }, meaningOthers: { 3: "已送达、送到了", 4: "" } },
    ],
  };
  const payload = typePayload(form);
  assert.deepEqual(payload.other_names, ["订单"]);
  assert.deepEqual(payload.properties.map((p) => p.other_names), [["订单号"], []]);
  assert.deepEqual(payload.enums, { status_code: [{ value: "3", label: "Delivered", other_names: ["已送达", "送到了"] }, { value: "4", label: "Cancelled", other_names: [] }] });
  const plain = typePayload({ ...form, otherNames: undefined, columns: form.columns.map(({ otherNames, meaningOthers, ...c }) => c) });
  assert.equal("other_names" in plain, false);
  assert.equal(plain.properties.some((p) => "other_names" in p), false);
  assert.deepEqual(plain.enums.status_code[0], { value: "3", label: "Delivered" });
});

test("a view and a derived property send their other names, and editing a derived property starts from the saved ones", () => {
  const view = { ...emptyViewForm(), name: "Valid orders", otherNames: "有效订单", filters: [{ column: "status_code", op: "is_not", label: "Cancelled" }] };
  assert.deepEqual(viewPayload("order", view).other_names, ["有效订单"]);
  assert.equal("other_names" in viewPayload("order", { ...view, otherNames: undefined }), false);
  const derived = { ...emptyDerivedForm("function"), name: "Gross", english_name: "gross", expression: "amount * 1.13", otherNames: "含税金额" };
  assert.deepEqual(derivedPayload("order", derived).other_names, ["含税金额"]);
  assert.equal(formFromLine({ definition: { kind: "function", name: "Gross", english_name: "gross", expression: "amount", other_names: ["含税金额", "毛额"] } }).otherNames, "含税金额、毛额");
});

test("the demo's Chinese questions are natural Chinese: the one refused names the customer type by its other name", () => {
  const demo = [{ id: "order", name: "Order", state: "confirmed" }, { id: "customer", name: "Customer", state: "needs_look", waiting: true }];
  assert.deepEqual(demoQuestions(demo), ["有效订单的总金额是多少？", "按客户城市看有效订单金额", "已送达的订单有几笔？"]);
});
