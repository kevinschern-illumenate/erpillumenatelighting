/**
 * W-0.1: the benchmark inside a browser Web Worker. Built to one IIFE file by `browser.mjs`, which sends
 * the LISP sources, the models and the options, and gets the timings back.
 */
import { type BenchInput, type BenchOptions, runBench } from '../src/bench';

self.onmessage = (
  event: MessageEvent<{
    sources: Record<string, string>;
    input: BenchInput;
    options: BenchOptions;
  }>,
) => {
  const { sources, input, options } = event.data;
  try {
    self.postMessage({ ok: true, result: runBench(sources, input, options) });
  } catch (error) {
    self.postMessage({ ok: false, error: String(error) });
  }
};
