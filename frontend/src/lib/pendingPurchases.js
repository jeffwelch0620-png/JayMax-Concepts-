// This tab's submitted initial reviews are recovery evidence, never authority
// to post. Commands still use the normal API and require an explicit retry.
const PREFIX = "jaymax:pending-purchases:v1:";
const MAX_BYTES = 2 * 1024 * 1024;
const MAX_RECORDS = 32;
const id = v => typeof v === "string" && /^[A-Za-z0-9_.-]{1,160}$/.test(v);
const uuid = v => typeof v === "string" && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(v);
const scalar = v => v == null || typeof v === "string" || (typeof v === "number" && Number.isFinite(v));
const units = ["lb", "oz", "g", "kg", "fl_oz", "ml", "l", "gal", "each"];
const failure = () => new Error("Submitted purchase recovery could not be retained or read in this tab. No new posting will be sent. Keep this tab open and contact a manager.");
const object = v => v && typeof v === "object" && !Array.isArray(v);
const exactKeys = (v, keys) => object(v) && Object.keys(v).length === keys.length && keys.every(k => Object.hasOwn(v, k));
const lineKeys = ["line_id", "classification", "movement_kind", "item_code", "base_unit", "received_quantity", "received_unit", "base_units_per_received_unit", "movement_date", "original_line_id", "verified", "note"];
const headerKeys = ["document_id", "vendor_id", "document_number", "document_type", "invoice_date", "confirmed_currency", "fees_source", "tax_source"];
const sourceLineKeys = ["id", "description_snapshot", "vendor_sku_snapshot", "pack_description_raw", "ordered_quantity_source", "shipped_quantity_source", "weight_source", "extended_amount_source", "pricing_unit_raw", "vendor_uom_raw"];
const take = (value, keys) => Object.fromEntries(keys.map(k => [k, value[k] ?? null]));

function validRecord(r) {
  if (!exactKeys(r, ["versionId", "key", "body", "document", "source"]) || !id(r.versionId) || !uuid(r.key)
    || !exactKeys(r.body, ["confirmed_currency", "received_date", "lines"]) || r.body.confirmed_currency !== "USD"
    || !(r.body.received_date === null || (typeof r.body.received_date === "string" && /^\d{4}-\d{2}-\d{2}$/.test(r.body.received_date)))
    || !Array.isArray(r.body.lines) || !r.body.lines.length || r.body.lines.length > 2000
    || !r.body.lines.every(l => exactKeys(l, lineKeys) && id(l.line_id) && l.verified === true && typeof l.note === "string" && !!l.note.trim()
      && ["food", "nonfood", "fee", "tax"].includes(l.classification)
      && ["receipt", "physical_return", "price_credit", "no_inventory"].includes(l.movement_kind)
      && (l.base_unit === null || units.includes(l.base_unit)) && lineKeys.every(k => k === "verified" || scalar(l[k])))
    || !exactKeys(r.document, ["id", "status", "header", "totals", "lines", "errors"]) || r.document.id !== r.versionId
    || r.document.status !== "awaiting_review" || !exactKeys(r.document.header, headerKeys) || !id(r.document.header.document_id)
    || !headerKeys.every(k => scalar(r.document.header[k])) || !["invoice", "credit"].includes(r.document.header.document_type)
    || !exactKeys(r.document.totals, ["lineTotal", "statedTotal", "difference"]) || !Object.values(r.document.totals).every(scalar)
    || !Array.isArray(r.document.lines) || r.document.lines.length !== r.body.lines.length
    || !r.document.lines.every((l, i) => exactKeys(l, sourceLineKeys) && id(l.id) && l.id === r.body.lines[i].line_id && Object.values(l).every(scalar))
    || new Set(r.body.lines.map(l => l.line_id)).size !== r.body.lines.length || !Array.isArray(r.document.errors) || r.document.errors.length
    || !exactKeys(r.source, ["id", "original_filename", "byte_count", "source_record_count", "source_sha256"]) || !id(r.source.id)
    || typeof r.source.original_filename !== "string" || !Object.values(r.source).every(scalar)) throw failure();
  return r;
}

export function pendingPurchaseRecord(source, document, body, key) {
  // Select display fields explicitly: do not persist auth, raw source bytes,
  // arbitrary server metadata or another invoice's review.
  return validRecord(JSON.parse(JSON.stringify({ versionId: document.id, key, body,
    document: { id: document.id, status: "awaiting_review", header: take(document.header, headerKeys),
      totals: take(document.totals, ["lineTotal", "statedTotal", "difference"]),
      lines: document.lines.map(l => take(l, sourceLineKeys)), errors: [] },
    source: take(source, ["id", "original_filename", "byte_count", "source_record_count", "source_sha256"]) })));
}

export function pendingPurchaseJournal(actorId, restaurantId, storage = () => window.sessionStorage) {
  restaurantId = restaurantId === "papa_leonis" ? "papa" : restaurantId;
  const key = `${PREFIX}${actorId}:${restaurantId}`;
  function read() {
    try {
      if (!id(actorId) || !["berts", "rudds", "papa", "comm"].includes(restaurantId)) throw failure();
      const raw = storage().getItem(key);
      if (raw === null) return [];
      if (new Blob([raw]).size > MAX_BYTES) throw failure();
      const value = JSON.parse(raw);
      if (!exactKeys(value, ["schema", "actorId", "restaurantId", "records"]) || value.schema !== 1
        || value.actorId !== actorId || value.restaurantId !== restaurantId || !Array.isArray(value.records)
        || value.records.length > MAX_RECORDS || new Set(value.records.map(r => r?.versionId)).size !== value.records.length) throw failure();
      return value.records.map(validRecord);
    } catch { throw failure(); }
  }
  function write(records) {
    try {
      const raw = JSON.stringify({ schema: 1, actorId, restaurantId, records });
      if (records.length > MAX_RECORDS || new Blob([raw]).size > MAX_BYTES) throw failure();
      storage().setItem(key, raw);
      if (storage().getItem(key) !== raw) throw failure();
    } catch { throw failure(); }
  }
  return {
    list: read,
    save(record) {
      validRecord(record);
      const records = read(), existing = records.find(r => r.versionId === record.versionId);
      if (existing) {
        if (existing.key !== record.key || JSON.stringify(existing.body) !== JSON.stringify(record.body)) throw failure();
        return existing;
      }
      write([...records, record]);
      return record;
    },
    clear(versionId, requestKey) {
      const records = read(), found = records.find(r => r.versionId === versionId);
      if (!found) return;
      if (found.key !== requestKey) throw failure();
      write(records.filter(r => r !== found));
    },
  };
}
