const nonempty = value => typeof value === "string" && value.length > 0;

export function validatePurchaseDocument(document, id) {
  if (document?.id !== id || !["posted", "held", "awaiting_review"].includes(document.status)
    || !document.header || !document.totals || !Array.isArray(document.lines)
    || !document.lines.every(line => nonempty(line?.id)) || !Array.isArray(document.errors)
    || !document.errors.every(reason => typeof reason === "string")) {
    throw new Error("Saved document status was not confirmed. Check again.");
  }
  return document;
}

export function purchaseRecoveryOutcome(document, id, requestKey) {
  validatePurchaseDocument(document, id);
  const header = document.header;
  if (!header.posted_batch_id) {
    if (document.status === "posted" || header.posted_request_key || header.posted_version_id) {
      throw new Error("Saved document status was not confirmed. Check again.");
    }
    return { kind: document.status === "held" ? "held" : "awaiting_review", document };
  }
  const initialVersion = header.initial_posted_version_id ?? header.posted_version_id;
  if (!nonempty(header.posted_batch_id) || !nonempty(header.posted_request_key)
    || !nonempty(initialVersion) || !nonempty(header.posted_version_id)
    || (header.current_correction_id != null && !nonempty(header.current_correction_id))
    || (header.posted_version_id !== initialVersion && !nonempty(header.current_correction_id))
    || (document.status === "posted" && header.posted_version_id !== id)) {
    throw new Error("Saved document status was not confirmed. Check again.");
  }
  // The original batch identity survives later corrections. A document being
  // posted is not sufficient proof that this frozen request was saved.
  if (initialVersion !== id || header.posted_request_key !== requestKey) {
    return { kind: "other_request", document };
  }
  if (nonempty(header.current_correction_id)) return { kind: "saved_corrected", document };
  if (document.status !== "posted" || header.posted_version_id !== id) {
    throw new Error("Saved document status was not confirmed. Check again.");
  }
  return { kind: "saved", document };
}
