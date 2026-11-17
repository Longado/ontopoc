import assert from "node:assert/strict";
import test from "node:test";
import { CHECKS, STEPS, diagnose, errorReport, portAfterKind } from "./connectModel.js";
import { setLocale } from "./i18n/index.js";

setLocale("zh");   // these tests assert the Chinese words; the English ones are in english.test.js

test("each failure the server words maps to its likely cause", () => {
  assert.equal(diagnose("找不到这个主机名：名字解析不出地址").kind, "host");
  assert.equal(diagnose("连接被对方拒绝：地址或端口不对，或数据库没有在听").kind, "port");
  assert.equal(diagnose("连不上：对方没有应答，或连接中途断了").kind, "port");
  assert.equal(diagnose("用户名或密码不对，或这个账号不让从这台机器登录").kind, "password");
  assert.equal(diagnose("没有这个数据库").kind, "database");
  assert.equal(diagnose("TLS 证书验证没通过，连接已拒绝：self signed certificate").kind, "cert");
  assert.equal(diagnose("TLS 握手失败：EOF").kind, "cert");
  assert.equal(diagnose("数据库不支持 TLS：让 DBA 开启它").kind, "tls");
  assert.equal(diagnose("连接超时或读取超时（连接 10 秒、读取 30 秒没有应答）").kind, "timeout");
  assert.equal(diagnose("这个地址是云服务商的内部地址（元数据服务，169.254 开头一类）").kind, "blocked");
  assert.equal(diagnose("这台服务器还连不了 PostgreSQL：少了连接它用的程序包 pg8000").kind, "driver");
});

test("the sentences the service writes in English map to the same causes", () => {
  assert.equal(diagnose("Could not resolve this host name: it does not map to an address").kind, "host");
  assert.equal(diagnose("The other side refused the connection: the address or port is wrong, or the database is not listening").kind, "port");
  assert.equal(diagnose("Cannot connect: no answer from the other side, or the connection dropped midway").kind, "port");
  assert.equal(diagnose("Wrong username or password, or this account may not sign in from this machine").kind, "password");
  assert.equal(diagnose("No such database").kind, "database");
  assert.equal(diagnose("The TLS certificate check failed and the connection was stopped: self signed certificate").kind, "cert");
  assert.equal(diagnose("The TLS handshake failed: EOF").kind, "cert");
  assert.equal(diagnose("The database does not support TLS: ask your DBA to turn it on").kind, "tls");
  assert.equal(diagnose("The connection or the read timed out (no answer within 10 seconds to connect or 30 seconds to read)").kind, "timeout");
  assert.equal(diagnose("The query ran past the time limit and the database stopped it").kind, "timeout");
  assert.equal(diagnose("This address is the cloud provider's internal address (the metadata service, one starting with 169.254)").kind, "blocked");
  assert.equal(diagnose("This server cannot reach PostgreSQL yet: the driver package pg8000 is missing").kind, "driver");
});

test("an unknown message still gets general checks, and an empty one is safe", () => {
  const d = diagnose("数据库说：something odd");
  assert.equal(d.kind, "other");
  assert.ok(d.causes.length >= 2);
  assert.equal(diagnose("").kind, "other");
  assert.equal(diagnose(undefined).kind, "other");
});

test("every diagnosis lists causes that each say what to check", () => {
  const said = { host: "找不到这个主机名", port: "连接被对方拒绝", password: "用户名或密码不对", database: "没有这个数据库", cert: "TLS 证书", tls: "不支持 TLS", timeout: "连接超时", blocked: "元数据服务", driver: "程序包", other: "x" };
  for (const [kind, message] of Object.entries(said)) {
    const d = diagnose(message);
    assert.equal(d.kind, kind);
    assert.ok(d.title);
    assert.ok(d.causes.length > 0);
    for (const c of d.causes) assert.ok(c.what && c.check, kind);
  }
});

test("the five checks the guide names are all covered", () => {
  assert.deepEqual(CHECKS, ["host", "port", "password", "cert", "timeout"]);
});

test("the error report is plain text with the address and the message, and never a password", () => {
  const text = errorReport({ source: "erp", kind: "PostgreSQL", host: "erp-db.fake.invalid", port: 5432, database: "erp", username: "ro", tls: "required", message: "找不到这个主机名：名字解析不出地址", at: "2026-11-16 10:30", password: "hunter2" });
  assert.match(text, /erp-db\.fake\.invalid:5432/);
  assert.match(text, /找不到这个主机名/);
  assert.match(text, /账号：ro/);
  assert.match(text, /加密：必须/);
  assert.doesNotMatch(text, /hunter2/);
});

test("switching the database type sets that type's port", () => {
  assert.equal(portAfterKind("mysql"), "3306");
  assert.equal(portAfterKind("postgresql"), "5432");
});

test("the wizard has five steps in order", () => {
  assert.deepEqual(STEPS.map((s) => s.key), ["type", "connect", "test", "tables", "schedule"]);
});
