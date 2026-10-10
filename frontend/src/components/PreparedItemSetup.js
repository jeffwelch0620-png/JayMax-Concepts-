import React, { useEffect, useRef, useState } from "react";
import * as api from "../lib/api";
import { Field, cardCls, inpCls, btnAcc, btnGhost } from "./common";

const blankLine = () => ({ source_kind: "raw", raw_item_code: "", prepared_recipe_id: null, prepared_profile_id: null, quantity: "", source_unit: "", factor: "", evidence: "" });
const detail = e => { const d = e?.response?.data?.detail; return typeof d === "string" ? d : Array.isArray(d) ? d.map(x => x.msg).join("; ") : e.message || "Prep setup failed"; };
const decimalKey = value => {
  const m = String(value).match(/^\+?(\d+)(?:\.(\d*))?(?:e([+-]?\d+))?$/i);
  if (!m || Math.abs(Number(m[3] || 0)) > 100) return null;
  const digits = (m[1] + (m[2] || "")).replace(/^0+/, "");
  if (!digits) return "zero";
  const trailing = digits.length - digits.replace(/0+$/, "").length;
  return `${digits.replace(/0+$/, "")}:${Number(m[3] || 0) - (m[2] || "").length + trailing}`;
};

export function PreparedItemSetup({ restaurantId }) {
  const [data, setData] = useState(null), [busy, setBusy] = useState(false), [error, setError] = useState(""), [message, setMessage] = useState("");
  const [name, setName] = useState(""), [base, setBase] = useState(""), [identityNote, setIdentityNote] = useState(""), [identityConfirmed, setIdentityConfirmed] = useState(false);
  const [productId, setProductId] = useState(""), [unitLabel, setUnitLabel] = useState(""), [unitFactor, setUnitFactor] = useState(""), [unitNote, setUnitNote] = useState(""), [unitConfirmed, setUnitConfirmed] = useState(false);
  const [outputId, setOutputId] = useState(""), [yieldQty, setYieldQty] = useState(""), [method, setMethod] = useState(""), [recipeNote, setRecipeNote] = useState("");
  const [legacyId, setLegacyId] = useState(""), [lines, setLines] = useState([blankLine()]), [review, setReview] = useState(null), [reviewed, setReviewed] = useState(false), [history, setHistory] = useState(null);
  const pending = useRef(null), mounted = useRef(true);
  useEffect(() => {
    let active = true;
    mounted.current = true;
    api.nativePrepSetup(restaurantId).then(d => active && setData(d)).catch(e => active && setError(detail(e)));
    return () => { active = false; mounted.current = false; };
  }, [restaurantId]);
  const frozen = busy || !!pending.current;
  const product = data?.products.find(p => p.id === productId);
  const units = data?.profiles.filter(p => p.product_version_id === productId) || [];
  const priorRecipe = data?.recipes.find(r => r.product_id === product?.product_id);
  const legacy = data?.legacySources.find(s => `${s.sourceType}:${s.sourceId}` === legacyId);
  function change(fn) { fn(); setReview(null); setReviewed(false); setUnitConfirmed(false); setIdentityConfirmed(false); setHistory(null); setMessage(""); }
  function updateLine(index, patch) { change(() => setLines(current => current.map((l, i) => i === index ? { ...l, ...patch } : l))); }
  async function refresh() {
    setBusy(true);
    try {
      const d = await api.nativePrepSetup(restaurantId);
      if (!mounted.current) return;
      setData(d); pending.current = null; setReview(null); setReviewed(false); setUnitConfirmed(false); setIdentityConfirmed(false); setHistory(null); setError(""); setMessage("Setup refreshed. Review any changed definitions again.");
    } catch (e) { if (mounted.current) setError(detail(e)); }
    finally { if (mounted.current) setBusy(false); }
  }
  async function save(kind, body) {
    setBusy(true); setError("");
    try {
      if (!pending.current) pending.current = { kind, body, key: crypto.randomUUID() };
      const p = pending.current;
      const fn = { product: api.saveNativePrepProduct, profile: api.saveNativePrepProfile, recipe: api.saveNativePrepRecipe }[p.kind];
      const r = await fn(restaurantId, p.body, p.key);
      const record = r[p.kind];
      const matches = p.kind === "product" ? record?.name === p.body.name && record?.base_unit === p.body.base_unit
        : p.kind === "profile" ? record?.product_version_id === p.body.product_version_id && record?.source_unit === p.body.source_unit && decimalKey(record?.base_units_per_source_unit) !== null && decimalKey(record?.base_units_per_source_unit) === decimalKey(p.body.factor)
          : record?.product_version_id === p.body.recipe.product_version_id && record?.review_hash === p.body.expected_review_hash;
      if (!record?.id || !matches || record.store_id !== ({ papa_leonis: "papa" }[restaurantId] || restaurantId)) throw new Error("Saved definition was not confirmed. Retry the same review.");
      if (!mounted.current) return;
      pending.current = null; setIdentityConfirmed(false); setUnitConfirmed(false); setReviewed(false); setReview(null); setHistory(null);
      setMessage("Verified definition saved. Earlier versions remain available in history.");
      try { const d = await api.nativePrepSetup(restaurantId); if (mounted.current) setData(d); }
      catch (e) { if (mounted.current) setError(`Definition saved; refresh failed: ${detail(e)}`); }
    } catch (e) {
      if (mounted.current) {
        setError(detail(e));
        if ([409, 422].includes(e?.response?.status)) { pending.current = null; setReview(null); setReviewed(false); setUnitConfirmed(false); setIdentityConfirmed(false); }
      }
    } finally { if (mounted.current) setBusy(false); }
  }
  function recipeBody() {
    return { product_version_id: productId, output_profile_id: outputId, entered_yield: yieldQty, predecessor_id: priorRecipe?.id || null, method, note: recipeNote,
      lines: lines.map(l => ({ ...l, raw_item_code: l.source_kind === "raw" ? l.raw_item_code : null })),
      legacy: legacy ? { source_type: legacy.sourceType, source_id: legacy.sourceId, expected_source_hash: legacy.hash } : null };
  }
  async function preview() {
    setBusy(true); setError(""); setReview(null); setReviewed(false);
    try {
      const body = recipeBody(); const r = await api.previewNativePrepRecipe(restaurantId, body);
      if (!r.reviewHash || !r.review?.lines?.length || r.review.product.id !== productId) throw new Error("Recipe preview was not confirmed.");
      if (mounted.current) setReview({ ...r, body });
    } catch (e) { if (mounted.current) setError(detail(e)); }
    finally { if (mounted.current) setBusy(false); }
  }
  async function showHistory(id) {
    setBusy(true); setError(""); setHistory(null);
    try { const h = await api.nativePrepHistory(restaurantId, id); if (mounted.current) setHistory(h); }
    catch (e) { if (mounted.current) setError(detail(e)); }
    finally { if (mounted.current) setBusy(false); }
  }
  const textInput = (label, value, setter) => <Field label={label}><input aria-label={label} className={inpCls} disabled={frozen} value={value} onChange={e => change(() => setter(e.target.value))} /></Field>;
  return <section className={`${cardCls} p-4 mb-6 space-y-3`} aria-label="Prepared item setup">
    <h3 className="font-semibold">Prepared items and recipe review</h3><p>Define what you prep, how you measure it, and the usable yield. Physical inventory and Food Cost remain based on purchased-item counts. Batch recording will follow in a later step.</p>
    {!data && !error && <p>Loading prep setup…</p>}
    {data && <>
      <h4>New prepared item</h4>
      {textInput("Prepared item name", name, setName)}
      <Field label="Prepared inventory unit"><select aria-label="Prepared inventory unit" className={inpCls} disabled={frozen} value={base} onChange={e => change(() => setBase(e.target.value))}><option value="">Choose fixed unit</option>{data.baseUnits.map(u => <option key={u}>{u}</option>)}</select></Field>
      <p>For a bag counted as one prepared item, choose “each” and name the contents clearly. One bag and one raw piece are separate items.</p>
      {textInput("Prepared identity evidence", identityNote, setIdentityNote)}
      <label><input aria-label="Confirm prepared identity" type="checkbox" checked={identityConfirmed} disabled={frozen} onChange={e => setIdentityConfirmed(e.target.checked)} /> I verified this prepared identity and fixed unit.</label>
      <button className={btnAcc} disabled={frozen || !identityConfirmed || !name.trim() || !base || !identityNote.trim()} onClick={() => save("product", { name: name.trim(), base_unit: base, note: identityNote.trim(), verified: true })}>Save prepared item</button>
      <h4>Verified prep units and recipe</h4>
      <Field label="Prepared item"><select aria-label="Prepared item" className={inpCls} value={productId} disabled={frozen} onChange={e => change(() => { setProductId(e.target.value); setOutputId(""); setUnitFactor(""); })}><option value="">Choose prepared item</option>{data.products.map(p => <option key={p.id} value={p.id}>{p.name} · {p.base_unit}</option>)}</select></Field>
      {product && <>
        {textInput("Prep measurement label", unitLabel, setUnitLabel)}{textInput(`Verified ${product.base_unit} per measurement`, unitFactor, setUnitFactor)}{textInput("Prep unit evidence", unitNote, setUnitNote)}
        <p>Enter actual fill separately when recording a batch later; a nominal container size is not a measured fill.</p>
        <label><input aria-label="Confirm prep unit" type="checkbox" disabled={frozen} checked={unitConfirmed} onChange={e => setUnitConfirmed(e.target.checked)} /> I verified this measurement conversion.</label>
        <button className={btnAcc} disabled={frozen || !unitConfirmed || !unitLabel.trim() || !unitFactor || !unitNote.trim()} onClick={() => save("profile", { product_version_id: productId, source_unit: unitLabel.trim().toLowerCase(), factor: unitFactor, predecessor_id: units.find(u => u.source_unit === unitLabel.trim().toLowerCase())?.id || null, note: unitNote.trim(), verified: true })}>Save prep unit version</button>
        {units.map(u => <p key={u.id}>1 {u.source_unit} = {u.base_units_per_source_unit} {product.base_unit} · unit version {u.revision}</p>)}
        <Field label="Usable yield measurement"><select aria-label="Usable yield measurement" className={inpCls} disabled={frozen} value={outputId} onChange={e => change(() => setOutputId(e.target.value))}><option value="">Choose verified yield unit</option>{units.map(u => <option key={u.id} value={u.id}>{u.source_unit}</option>)}</select></Field>
        {textInput("Usable yield quantity", yieldQty, setYieldQty)}{textInput("Prep method", method, setMethod)}{textInput("Recipe review evidence", recipeNote, setRecipeNote)}
        <Field label="Existing prep source (optional)"><select aria-label="Existing prep source" className={inpCls} disabled={frozen} value={legacyId} onChange={e => change(() => setLegacyId(e.target.value))}><option value="">New recipe without a legacy link</option>{data.legacySources.filter(s => s.sourceType !== "dish" || s.snapshot.header.recipe_type === "prep").map(s => <option key={`${s.sourceType}:${s.sourceId}`} value={`${s.sourceType}:${s.sourceId}`}>{s.name} · {s.mappingState}</option>)}</select></Field>
        {legacy && <p>Source review: {legacy.issues.join("; ")}. Verify the native ingredients and yield below; existing quantities are retained as evidence.</p>}
        {lines.map((line, index) => <div key={index} className="border border-slate-700 rounded p-3 space-y-2">
          <Field label={`Ingredient ${index + 1} type`}><select aria-label={`Ingredient ${index + 1} type`} className={inpCls} value={line.source_kind} disabled={frozen} onChange={e => updateLine(index, { ...blankLine(), source_kind: e.target.value })}><option value="raw">Purchased ingredient</option><option value="prepared">Existing prepared recipe</option></select></Field>
          {line.source_kind === "raw" ? <Field label={`Ingredient ${index + 1} item`}><select aria-label={`Ingredient ${index + 1} item`} className={inpCls} disabled={frozen} value={line.raw_item_code} onChange={e => updateLine(index, { raw_item_code: e.target.value, source_unit: "", factor: "" })}><option value="">Choose purchased item</option>{data.rawItems.map(r => <option key={r.code} value={r.code} disabled={!r.base_unit}>{r.name} · {r.base_unit || "verify inventory unit first"}</option>)}</select></Field> : <>
            <Field label={`Ingredient ${index + 1} recipe`}><select aria-label={`Ingredient ${index + 1} recipe`} className={inpCls} disabled={frozen} value={line.prepared_recipe_id || ""} onChange={e => updateLine(index, { prepared_recipe_id: e.target.value, prepared_profile_id: null, source_unit: "", factor: "" })}><option value="">Choose approved prepared recipe</option>{data.recipes.filter(r => r.product_id !== product.product_id && !r.reviewNeeded).map(r => <option key={r.id} value={r.id}>{data.products.find(p => p.product_id === r.product_id)?.name || "Prepared recipe"} · recipe version {r.revision}</option>)}</select></Field>
            <Field label={`Ingredient ${index + 1} prep unit`}><select aria-label={`Ingredient ${index + 1} prep unit`} className={inpCls} disabled={frozen} value={line.prepared_profile_id || ""} onChange={e => { const u = data.profiles.find(p => p.id === e.target.value); updateLine(index, { prepared_profile_id: u?.id || null, source_unit: u?.source_unit || "", factor: u?.base_units_per_source_unit || "" }); }}><option value="">Choose verified prep unit</option>{data.profiles.filter(p => p.product_version_id === data.recipes.find(r => r.id === line.prepared_recipe_id)?.product_version_id).map(u => <option key={u.id} value={u.id}>{u.source_unit} · factor {u.base_units_per_source_unit}</option>)}</select></Field>
          </>}
          {[['quantity', 'quantity'], ['source_unit', 'unit'], ['factor', 'conversion'], ['evidence', 'evidence']].map(([field, label]) => <Field key={field} label={`Ingredient ${index + 1} ${label}`}><input aria-label={`Ingredient ${index + 1} ${label}`} className={inpCls} disabled={frozen || (line.source_kind === "prepared" && ['source_unit', 'factor'].includes(field))} value={line[field]} onChange={e => updateLine(index, { [field]: e.target.value })} /></Field>)}
          <p>Conversion means fixed inventory units per entered ingredient unit. For purchased ingredients, use physical units such as lb or oz.</p>
          <button className={btnGhost} disabled={frozen || lines.length === 1} onClick={() => change(() => setLines(current => current.filter((_, i) => i !== index)))}>Remove ingredient {index + 1}</button>
        </div>)}
        <button className={btnGhost} disabled={frozen} onClick={() => change(() => setLines(current => [...current, blankLine()]))}>Add ingredient</button>
        <button className={btnAcc} disabled={frozen || !outputId || !yieldQty || !method.trim() || !recipeNote.trim()} onClick={preview}>Preview recipe version</button>
        {review && <div aria-label="Recipe review"><p>Usable output: {review.review.usableBaseYield} {product.base_unit}. Recipe version {review.review.revision}.</p>{review.review.lines.map(l => <p key={l.line_number}>Ingredient {l.line_number}: {l.quantity} {l.source_unit} = {l.base_quantity} {l.base_unit} · {l.source_kind === "prepared" ? "Existing prep input; raw ancestry retained without another withdrawal" : "Gross purchased input"}</p>)}
          <label><input aria-label="Confirm recipe review" type="checkbox" checked={reviewed} disabled={frozen} onChange={e => setReviewed(e.target.checked)} /> I verified the identities, conversions and usable yield.</label>
          <button className={btnAcc} disabled={frozen || !reviewed} onClick={() => save("recipe", { recipe: review.body, expected_review_hash: review.reviewHash, reviewed: true })}>Approve recipe version</button>
        </div>}
        <button className={btnGhost} disabled={frozen} onClick={() => showHistory(product.product_id)}>Show prepared item history</button>
      </>}
      <h4>Existing mapping review</h4>
      {data.legacySources.length === 0 && <p>No legacy prep definitions found at this location.</p>}
      {data.legacySources.map(s => <details key={`${s.sourceType}:${s.sourceId}`}><summary>{s.name} · {s.mappingState === "reviewed" ? "Source reviewed" : s.mappingState === "source_changed" ? "Source changed — review again" : "Needs review"}</summary><p>{s.issues.join("; ")}</p>{s.snapshot.lines?.map(l => <p key={l.id}>{l.item_code || l.prep_dish_id || "Unknown ingredient"}: {l.qty} {l.uom || "unit missing"}</p>)}</details>)}
      {data.recipes.map(r => <p key={r.id}>{data.products.find(p => p.product_id === r.product_id)?.name || "Prepared recipe"} · recipe version {r.revision} · {r.reviewNeeded ? `Needs review: ${r.reviewIssues.join("; ")}` : "Definition reviewed"}</p>)}
      {history && <div aria-label="Prepared item history">{history.productVersions.map(p => <p key={p.id}>{p.name} · identity version {p.revision} · {p.base_unit}</p>)}{history.unitProfiles.map(u => <p key={u.id}>Unit version {u.revision}: 1 {u.source_unit} = {u.base_units_per_source_unit}</p>)}{history.recipeVersions.map(r => <p key={r.id}>Recipe version {r.revision}: usable output {r.usable_base_yield}; {r.note}</p>)}</div>}
    </>}
    {pending.current && <button className={btnAcc} disabled={busy} onClick={() => save(pending.current.kind, pending.current.body)}>Retry same definition review</button>}
    <button className={btnGhost} disabled={frozen} onClick={refresh}>Refresh prep setup</button>
    {error && <p role="alert">{error}</p>}{message && <p role="status">{message}</p>}
  </section>;
}
