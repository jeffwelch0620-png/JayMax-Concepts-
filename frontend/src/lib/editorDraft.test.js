import { equalEditorValue, mergeEditorFields, snapshotEditorValue } from "./editorDraft";

test("structural snapshots preserve null conversions and exact prices without sharing nested arrays", () => {
  const base={vendorSkus:[{price:"12345678901234567890.000000000001",basePerPurchaseUnit:null}]};
  const snapshot=snapshotEditorValue(base);
  expect(equalEditorValue(base,snapshot)).toBe(true);
  base.vendorSkus[0].basePerPurchaseUnit=20;
  expect(snapshot.vendorSkus[0].basePerPurchaseUnit).toBeNull();
  expect(snapshot.vendorSkus[0].price).toBe("12345678901234567890.000000000001");
  expect(equalEditorValue(base,snapshot)).toBe(false);
});

test("three-way recovery keeps remote additions and independent local edits without mutating inputs", () => {
  const base={name:"Original",par:1},draft={...base,name:"Local"},latest={...base,par:2,notes:"Remote"};
  const result=mergeEditorFields(base,draft,latest);
  expect(result).toEqual({data:{name:"Local",par:2,notes:"Remote"},conflicts:[]});
  expect(base).toEqual({name:"Original",par:1});expect(latest.name).toBe("Original");
});

test("same-field edits conflict unless the values agree", () => {
  expect(mergeEditorFields({par:1},{par:3},{par:2}).conflicts).toEqual(["par"]);
  expect(mergeEditorFields({par:1},{par:2},{par:2})).toEqual({data:{par:2},conflicts:[]});
});

test("coupled fields and row arrays never merge by position", () => {
  const base={pack:4,rows:[{id:"a",factor:null}]};
  const draft={...base,pack:5},latest={...base,rows:[{id:"b",factor:20}]};
  expect(mergeEditorFields(base,draft,latest,[{label:"pack and rows",fields:["pack","rows"]}]).conflicts).toEqual(["pack and rows"]);
});
