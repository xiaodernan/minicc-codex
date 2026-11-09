// M8-T537: every suite that runs before the product path names itself when it
// fails. The mutation verdict accepts only the product-path completion code, so
// a timeline/desktop/mobile assertion failure must reach the log as a named
// code instead of "the smoke exited 1 without naming a failure code".
//
// This module exists so a node child can exercise the emit path without
// launching Chromium: tests/test_the_other_suites_name_themselves_too.py
// imports it and drives both directions (a throwing run prints one code, a
// passing run prints none).

function announce(code) {
  console.error(`SMOKE_FAILURE_CODE=${code}`);
}

export async function runNamedSuite(code, run) {
  try {
    return await run();
  } catch (error) {
    // The product path names its own (finer) code; an outer wrapper must not
    // print a second code that would shadow it, because the verdict keeps the
    // last code in the log.
    if (!error?.smokeCodeNamed) announce(code);
    throw error;
  }
}

export function failProductPath(code, message) {
  announce(code);
  const error = new Error(message);
  error.smokeCodeNamed = true;
  throw error;
}
