import { mergeSalesDraft } from "./salesDraft";

const base = { periodStart: "2026-10-01", periodEnd: "2026-10-07", dishSales: { a: "2", b: "3" }, itemCounts: { food: { beginning: "4", ending: "1" } } };
test("merges separate sales and count fields while retaining server metadata", () => {
  const draft = { ...base, dishSales: { ...base.dishSales, a: "17" }, itemCounts: { food: { beginning: "5", ending: "1" } } };
  const latest = { ...base, dishSales: { ...base.dishSales, b: "8" }, itemCounts: { food: { beginning: "4", ending: "0" } }, source: "server" };
  expect(mergeSalesDraft(base, draft, latest)).toEqual({ conflicts: [], data: {
    ...latest, dishSales: { a: "17", b: "8" }, itemCounts: { food: { beginning: "5", ending: "0" } },
  } });
});
test("same-field conflicts retain the local draft without mutating any input", () => {
  const draft = { ...base, dishSales: { ...base.dishSales, a: "17" } };
  const latest = { ...base, dishSales: { ...base.dishSales, a: "99" } };
  const result = mergeSalesDraft(base, draft, latest);
  expect(result.conflicts).toEqual(["dishSales.a"]);
  expect(result.data.dishSales.a).toBe("17");
  expect(base.dishSales.a).toBe("2"); expect(latest.dishSales.a).toBe("99");
});
test("matching edits are accepted and independent additions/deletions survive", () => {
  const draft = { ...base, dishSales: { a: "17", c: "1" } };
  const latest = { ...base, dishSales: { a: "17", b: "3", d: "9" } };
  expect(mergeSalesDraft(base, draft, latest)).toEqual({ conflicts: [], data: { ...base, dishSales: { a: "17", c: "1", d: "9" } } });
});
test("a remote edit to a locally deleted field conflicts", () => {
  expect(mergeSalesDraft(base, { ...base, dishSales: { a: "2" } }, { ...base, dishSales: { a: "2", b: "9" } }).conflicts).toEqual(["dishSales.b"]);
});
test("never merges a retained draft into different period dates or without its baseline", () => {
  expect(mergeSalesDraft(base, base, { ...base, periodStart: "2026-10-08" }).conflicts).toHaveLength(1);
  expect(mergeSalesDraft(undefined, base, base).conflicts).toHaveLength(1);
});
