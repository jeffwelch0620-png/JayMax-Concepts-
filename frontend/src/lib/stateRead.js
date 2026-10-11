// One budget covers the shared state and every PostgreSQL child read. This is
// deliberately scoped to reads; it does not change mutation retry semantics.
export const STATE_READ_TIMEOUT_MS = 60000;
export const STATE_READ_TIMEOUT_MESSAGE = "Location data loading timed out. Check your connection and retry; your draft is retained.";

export async function readStateWithDeadline(load) {
  const controller = new AbortController();
  let timer;
  const deadline = new Promise((resolve, reject) => {
    timer = setTimeout(() => {
      // Reject first so an abort-aware transport cannot replace the useful
      // timeout diagnosis with its generic cancellation error.
      reject(new Error(STATE_READ_TIMEOUT_MESSAGE));
      controller.abort();
    }, STATE_READ_TIMEOUT_MS);
  });
  try {
    return await Promise.race([load({ signal: controller.signal }), deadline]);
  } finally {
    clearTimeout(timer);
    // Also cancel siblings when one child fails. Race observes late transport
    // completions; they cannot produce another result or an unhandled rejection.
    controller.abort();
  }
}
