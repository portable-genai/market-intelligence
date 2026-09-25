/**
 * The model pills' source: what answered, read off the console's own API responses.
 *
 * These import `lib/answer-provenance.mjs` itself, so a rule that changes in the component
 * changes here too. What is checked is that a pill can never name a model no response named,
 * that a response from anywhere but the console's API base cannot set it, and that the one
 * `fetch` wrapper is installed once and put back.
 */

import assert from "node:assert/strict";
import { test } from "node:test";

import { answerOf, isConsoleApi, watchAnswers } from "../lib/answer-provenance.mjs";

const HERE = "http://console.test:3000/";
// Standalone: the service on its own origin. Under the portal: a same-origin mount.
const STANDALONE = "http://api.test:8100";
const MOUNTED = "/market-intelligence/api";

function reply(headers) {
  return { headers: new Headers(headers) };
}

function host(headers) {
  const calls = [];
  const original = async (input) => {
    calls.push(input);
    return reply(headers);
  };
  return { fetch: original, original, calls, location: { href: HERE } };
}

test("a response that names no model is no answer, never a guess", () => {
  assert.equal(answerOf(new Headers()), null);
  assert.equal(answerOf(new Headers({ "x-search-used": "true" })), null);
  assert.equal(answerOf(new Headers({ "x-answered-by": "  " })), null);
});

test("the answering model and the search flag are read as sent", () => {
  assert.deepEqual(answerOf(new Headers({ "x-answered-by": "gemini-3.5-flash" })), {
    model: "gemini-3.5-flash",
    search: false,
  });
  assert.deepEqual(
    answerOf(new Headers({ "x-answered-by": "a, b", "x-search-used": "true" })),
    { model: "a, b", search: true },
  );
});

test("a standalone console counts only its service's origin", () => {
  assert.equal(isConsoleApi("http://api.test:8100/v1/brief", HERE, STANDALONE), true);
  assert.equal(isConsoleApi(new URL("http://api.test:8100/healthz"), HERE, STANDALONE), true);
  assert.equal(isConsoleApi({ url: "http://api.test:8100/v1/x" }, HERE, STANDALONE), true);
  assert.equal(isConsoleApi("http://api.test:9999/v1/brief", HERE, STANDALONE), false);
  assert.equal(isConsoleApi("/v1/brief", HERE, STANDALONE), false);
  assert.equal(isConsoleApi(42, HERE, STANDALONE), false);
});

test("a mounted console counts only its own mount on its own origin", () => {
  assert.equal(isConsoleApi("/market-intelligence/api/v1/brief", HERE, MOUNTED), true);
  assert.equal(isConsoleApi("/market-intelligence/api/healthz", HERE, MOUNTED + "/"), true);
  assert.equal(isConsoleApi("/market-intelligence/apisomething", HERE, MOUNTED), false);
  assert.equal(isConsoleApi("/other/api/v1/brief", HERE, MOUNTED), false);
  assert.equal(isConsoleApi("http://elsewhere.test/market-intelligence/api/v1", HERE, MOUNTED), false);
});

test("the wrapper reports an answer from the console's API and ignores other origins", async () => {
  const window = host({ "x-answered-by": "model-a", "x-search-used": "true" });
  const seen = [];
  const stop = watchAnswers(window, STANDALONE, (answer) => seen.push(answer));
  await window.fetch("http://api.test:8100/v1/brief", { method: "POST" });
  await window.fetch("http://elsewhere.test/v1/brief");
  stop();
  assert.deepEqual(seen, [{ model: "model-a", search: true }]);
  assert.equal(window.calls.length, 2, "the wrapper must still perform every call");
});

test("the wrapper is installed once however many listeners, and restored by the last", async () => {
  const window = host({ "x-answered-by": "model-b" });
  const first = [];
  const second = [];
  const stopFirst = watchAnswers(window, MOUNTED, (answer) => first.push(answer.model));
  const wrapped = window.fetch;
  const stopSecond = watchAnswers(window, MOUNTED, (answer) => second.push(answer.model));
  assert.equal(window.fetch, wrapped, "a second listener wrapped fetch again");
  await window.fetch("/market-intelligence/api/v1/brief");
  stopFirst();
  assert.equal(window.fetch, wrapped, "the wrapper left while a listener remained");
  stopSecond();
  assert.equal(window.fetch, window.original, "the original fetch was not put back");
  assert.deepEqual(first, ["model-b"]);
  assert.deepEqual(second, ["model-b"]);
});
