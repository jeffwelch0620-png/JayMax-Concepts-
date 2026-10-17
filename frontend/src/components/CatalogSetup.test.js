import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { SetupTab } from "./SetupTab";
import * as api from "../lib/api";
import { resetComponentApiMock } from "../testHelpers/componentApiMock";
import { useStoreState } from "../lib/useStoreState";
jest.mock("../lib/api", () => require("../testHelpers/componentApiMock").createComponentApiMock());
const item = { controlNumber: "F01", itemCode: "stable_food", name: "Invented food", storageArea: "Freezer", active: true, countActive: false, orderEnabled: true, salesTracked: true, par: 0,
  baseUnit: "lb", countUnit: "bag", basePerCountUnit: 25, lastCounted: "2026-10-01", lastCountedBy: "Invented counter", currentStock: 7,
  packCount: 4, unitQty: 5, unitUOM: "lb", portionSize: 4, portionUOM: "oz", purchaseUnit: "case", itemType: "portion",
  vendorSkus: [{ id: "sku", vendorId: "pfg", vendor: "PFG", vendorSku: "00001", packDescription: "  Original supplier description  ", price: "12345678901234567890.000000000001", priceSource: "invoice", priceUpdatedAt: "2026-10-01", purchaseUnit: "case", packCount: 4, unitQty: 5, unitUOM: "lb", basePerPurchaseUnit: 20 }] };
let root, container, persist, success;
const find = id => container.querySelector(`[data-testid="${id}"]`);
const click = id => act(async () => find(id).click());
beforeEach(async () => {
  resetComponentApiMock(api);
  global.IS_REACT_ACT_ENVIRONMENT = true; api.listVendorContacts.mockResolvedValue([]);
  api.catalogMappingEnabled=false;api.actualInventoryEnabled=false;api.supplierContactsEnabled=false;api.sharedCatalog.mockResolvedValue({products:[],revision:1});
  api.nativeOperatingSummary.mockResolvedValue({basis:"native_received_purchases_and_explicit_counts",items:[],liveOnHandAvailable:false,countStatus:"scope_missing"});
  api.supplierContacts.mockResolvedValue({store_id:"berts",contacts:[],legacy_contacts:[]});
  container=document.createElement("div");document.body.appendChild(container);root=createRoot(container);
  persist=jest.fn().mockResolvedValue({ revision: 1 });success=jest.fn();
  await act(async () => root.render(<SetupTab rid="berts" items={[item]} areas={[{ name:"Freezer",prefix:"F" }]} persistItems={persist} persistAreas={persist} showToast={success} />));
});
afterEach(async () => { await act(async () => root.unmount());container.remove();jest.restoreAllMocks(); });

const revisionProps = (revision, items = [item], drafts) => ({ rid: "berts", revision, items, drafts,
  areas: [{name:"Freezer",prefix:"F"}], persistItems: persist, persistAreas: persist, showToast: success });
const changeInput = async (field, value) => act(async () => {
  Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,"value").set.call(field,value);
  field.dispatchEvent(new Event("input",{bubbles:true}));
});
const parInput = () => [...container.querySelectorAll("label")].find(label => label.textContent.includes("Par Level (purchase units)")).querySelector("input");

test("the real editor preserves exact decimal metadata through an unrelated save and decimal input", async () => {
  const exact = "1.123456789012345678";
  const precise = { ...item, par: exact, packCount: exact, unitQty: exact, portionSize: exact, basePerCountUnit: exact,
    vendorSkus: [{ ...item.vendorSkus[0], packCount: exact, unitQty: exact, basePerPurchaseUnit: exact }] };
  await act(async () => root.render(<SetupTab {...revisionProps(10, [precise])} />));
  await click("edit-item-F01");
  await changeInput(parInput(), "2.123456789012345678");
  await click("item-submit-button");
  expect(persist).toHaveBeenCalledTimes(1);
  const saved = persist.mock.calls[0][0][0];
  expect(saved.par).toBe("2.123456789012345678");
  for (const key of ["packCount", "unitQty", "portionSize", "basePerCountUnit"]) expect(saved[key]).toBe(exact);
  for (const key of ["packCount", "unitQty", "basePerPurchaseUnit"]) expect(saved.vendorSkus[0][key]).toBe(exact);
});

test.each(["1e400", "1" + "0".repeat(400), "1e-400", "0E-10", "9".repeat(512) + "." + "1".repeat(512)])("all seven editable decimal fields retain %s through reopen and an unrelated save", async value => {
  const precise = { ...item, par: value, packCount: value, unitQty: value, portionSize: value,
    vendorSkus: [{ ...item.vendorSkus[0], packCount: value, unitQty: value, price: value }] };
  await act(async () => root.render(<SetupTab {...revisionProps(10, [precise])} />));
  await click("edit-item-F01");
  const fields = find("item-name-input").closest("form").querySelectorAll('input[inputmode="decimal"]');
  expect(fields).toHaveLength(7);
  for (const field of fields) { expect(field.type).toBe("text"); expect(field.value).toBe(value); }
  await changeInput(find("item-name-input"), "Unrelated fictional rename");
  await click("item-submit-button");
  const saved = persist.mock.calls[0][0][0];
  for (const key of ["par", "packCount", "unitQty", "portionSize"]) expect(saved[key]).toBe(value);
  for (const key of ["packCount", "unitQty", "price"]) expect(saved.vendorSkus[0][key]).toBe(value);
  const body = jest.requireActual("../lib/api").mongoItemToPgBody(saved, "berts");
  expect(body.par).toBe(value); expect(body.vendor_skus[0].price).toBe(value);
  expect(body.base_per_count_unit).toBe("25"); expect(body.vendor_skus[0].base_per_purchase_unit).toBe("20");
});

test.each(['1e400','1e-400'])('preview marks unsafe price %s unavailable without losing exact input', async price => {
  const unsafe={...item,vendorSkus:[{...item.vendorSkus[0],price}]};
  await act(async()=>root.render(<SetupTab {...revisionProps(10,[unsafe])}/>));
  await click('edit-item-F01');
  expect(find('portion-preview').textContent).toContain('Outside supported calculation range');
  expect(find('portion-preview').textContent).not.toMatch(/Infinity|NaN|∞|\$0\.00/);
  await click('item-submit-button');
  expect(persist.mock.calls[0][0][0].vendorSkus[0].price).toBe(price);
});

test.each([
  ['weight versus volume',{portionUOM:'fl oz'}],
  ['unsupported matching unit',{unitUOM:'scoop',portionUOM:'scoop',vendorSkus:[{...item.vendorSkus[0],unitUOM:'scoop'}]}],
  ['nonpositive portion',{portionSize:'-4'}],
  ['missing unit must not default to each',{unitUOM:'',portionUOM:'each',vendorSkus:[{...item.vendorSkus[0],unitUOM:''}]}],
  ['negative pack factors must not cancel',{vendorSkus:[{...item.vendorSkus[0],packCount:'-4',unitQty:'-5'}]}],
])('setup refuses to display an invented portion conversion or cost: %s',async(label,changes)=>{
  const incomplete={...item,...changes};
  await act(async()=>root.render(<SetupTab {...revisionProps(10,[incomplete])}/>));
  await click('edit-item-F01');
  const preview=find('portion-preview').textContent;
  expect(preview).toContain('Portions and cost unavailable');
  expect(preview).not.toContain('portions per case');expect(preview).not.toMatch(/\$[0-9]/);
  expect(find('setup-cost-F01').textContent).toContain('Unknown');
  expect(find('setup-cost-F01').title).toContain('confirm compatible pack and portion');
  expect(persist).not.toHaveBeenCalled();
  await changeInput(find('item-name-input'),'Unrelated fictional rename');await click('item-submit-button');
  const saved=persist.mock.calls[0][0][0];
  expect(saved.itemCode).toBe(incomplete.itemCode);expect(saved.basePerCountUnit).toBe(incomplete.basePerCountUnit);
  expect(saved.vendorSkus[0].basePerPurchaseUnit).toBe(incomplete.vendorSkus[0].basePerPurchaseUnit);
  expect(saved.vendorSkus[0].price).toBe(incomplete.vendorSkus[0].price);
  expect(saved.portionUOM).toBe(incomplete.portionUOM);expect(saved.portionSize).toBe(String(incomplete.portionSize));
});

test('missing portion metadata leaves setup cost unknown rather than a zero estimate',async()=>{
  const incomplete={...item,portionSize:null};
  await act(async()=>root.render(<SetupTab {...revisionProps(10,[incomplete])}/>));
  await click('edit-item-F01');
  expect(find('portion-preview').textContent).toContain("Portion Size isn't set");
  expect(find('setup-cost-F01').textContent).toContain('Unknown');
  expect(find('setup-cost-F01').textContent).not.toContain('$0.00');
  expect(persist).not.toHaveBeenCalled();
});

test('a weight pack and volume portion show the specific mismatch guidance without a numeric estimate',async()=>{
  const mismatched={...item,packCount:'1',unitQty:'5',portionSize:'4',portionUOM:'fl oz',
    vendorSkus:[{...item.vendorSkus[0],packCount:'1',unitQty:'5',price:'20'}]};
  await act(async()=>root.render(<SetupTab {...revisionProps(10,[mismatched])}/>));
  await click('edit-item-F01');
  const preview=find('portion-preview').textContent;
  expect(preview).toContain("size unit and portion unit aren't the same measure type");
  expect(preview).not.toContain('portions per case');
  expect(preview).not.toMatch(/\$[0-9]|1\.25|16\.00/);
  expect(find('setup-cost-F01').textContent).toContain('Unknown');
  expect(persist).not.toHaveBeenCalled();
});

test.each(['20','0E-10'])('valid setup uses the recipe-cost contract with price %s',async price=>{
  const valid={...item,vendorSkus:[{...item.vendorSkus[0],price}]};
  await act(async()=>root.render(<SetupTab {...revisionProps(10,[valid])}/>));await click('edit-item-F01');
  const expected=price==='0E-10'?'$0.00':'$0.25';
  expect(find('portion-preview').textContent).toContain('80.0 portions per case');
  expect(find('portion-preview').textContent).toContain(`${expected} cost per portion`);
  expect(find('setup-cost-F01').textContent).toBe(expected);expect(persist).not.toHaveBeenCalled();
});

const localSession = {user:{id:"synthetic-owner"}};
const localEmpty = {items:[],areas:[]};
function StoreCatalog({onError}) {
  const store = useStoreState("berts", localSession, localEmpty, onError);
  return store.state ? <SetupTab {...revisionProps(store.state.revision, store.state.items)}
    showError={onError} persistItems={(next,revision)=>store.save("items",next,revision)} /> : <p>Loading</p>;
}

test.each([null, '', '0E-10'])('editor and list distinguish missing price %p from explicit zero', async price => {
  const priced={...item,vendorSkus:[{...item.vendorSkus[0],price}]};
  await act(async()=>root.render(<SetupTab {...revisionProps(10,[priced])}/>));
  await click('edit-item-F01');
  const expected=price==='0E-10'?'$0.00':'Unknown';
  expect(find('portion-preview').textContent).toContain('80.0 portions per case');
  expect(find('portion-preview').textContent).toContain(`${expected} cost per portion`);
  expect(find('portion-preview').textContent).not.toContain('Outside supported calculation range');
  expect(find('setup-item-row-F01').textContent).toContain(expected);
  await changeInput(find('item-name-input'),'Fictional unrelated rename');
  await click('item-submit-button');
  expect(persist.mock.calls[0][0][0].vendorSkus[0].price).toBe(price===''?null:price);
});

test('real store and editor retain a refused supplier-pack edit and save only an explicitly cleared price', async () => {
  const detail='Clear the planning price when changing a supplier pack, then review its new price and physical conversion';
  const errors=jest.fn();
  api.fetchState.mockResolvedValue({revision:10,items:[item]});
  api.putCollection.mockRejectedValueOnce({response:{status:409,data:{detail}}})
    .mockResolvedValueOnce({revision:11});
  await act(async()=>root.render(<StoreCatalog onError={errors}/>));
  await click('edit-item-F01');
  const pack=[...find('vendor-sku-row-0').querySelectorAll('label')]
    .find(label=>label.textContent==='Pack Count').querySelector('input');
  await changeInput(pack,'5');
  await click('item-submit-button');
  expect(container.querySelector('[role="alert"]').textContent).toContain(detail);
  expect(container.querySelector('[role="alert"]').textContent).toContain('draft is retained');
  expect(pack.value).toBe('5');
  const price=container.querySelector('[aria-label="Supplier price sku"]');
  expect(price.value).toBe(item.vendorSkus[0].price);
  expect(api.putCollection).toHaveBeenCalledTimes(1);expect(success).not.toHaveBeenCalled();
  await changeInput(price,''); await click('item-submit-button');
  expect(api.putCollection).toHaveBeenCalledTimes(2);
  expect(api.putCollection).toHaveBeenLastCalledWith('berts','items',[
    expect.objectContaining({basePerCountUnit:25,vendorSkus:[expect.objectContaining({packCount:'5',price:null,basePerPurchaseUnit:20})]})
  ],10);
  expect(success).toHaveBeenCalledTimes(1);
});

test.each(["1e200000", "1e-513", "NaN", "-1"])("real store and editor retain invalid text %s and its specific error without a transport write", async value => {
  const errors = jest.fn(), transport = jest.fn();
  api.fetchState.mockResolvedValue({revision:10,items:[item]});
  api.putCollection.mockImplementation((rid,name,next) => {
    next.forEach(row => jest.requireActual("../lib/api").mongoItemToPgBody(row,rid));
    return transport();
  });
  await act(async () => root.render(<StoreCatalog onError={errors}/>));
  await click("edit-item-F01"); await changeInput(parInput(),value);
  expect(parInput().value).toBe(value);
  await click("item-submit-button");
  expect(transport).not.toHaveBeenCalled(); expect(success).not.toHaveBeenCalled();
  expect(parInput().value).toBe(value);
  expect(container.querySelector('[role="alert"]').textContent).toContain("512 integer digits");
  expect(errors).toHaveBeenLastCalledWith(expect.stringContaining("512 integer digits"));
  expect(container.textContent).not.toContain("Save was not confirmed");
});

test("background refresh cannot rebase an open catalog editor; cancel and reopen uses latest data", async () => {
  await act(async () => root.render(<SetupTab {...revisionProps(10)} />));
  await click("edit-item-F01");
  await changeInput(parInput(),"2");
  await act(async () => root.render(<SetupTab {...revisionProps(11,[{...item,par:1}])} />));
  await click("item-submit-button");
  expect(persist).not.toHaveBeenCalled(); expect(success).not.toHaveBeenCalled();
  expect(container.querySelector('[role="alert"]').textContent).toContain("draft is retained");
  expect(parInput().value).toBe("2");
  await act(async () => [...container.querySelectorAll("button")].find(b => b.textContent.includes("Cancel")).click());
  await click("edit-item-F01");
  expect(parInput().value).toBe("1");
  await click("item-submit-button");
  expect(persist).toHaveBeenCalledWith([expect.objectContaining({par:"1"})],11);
});

test("retained editor keeps its original version across navigation and later typing", async () => {
  const drafts = new Map();
  await act(async () => root.render(<SetupTab key="retained" {...revisionProps(10,[item],drafts)} />));
  await click("edit-item-F01");
  await act(async () => root.render(<p>Other panel</p>));
  await act(async () => root.render(<SetupTab {...revisionProps(11,[{...item,par:1}],drafts)} />));
  await changeInput(find("item-name-input"),"Retained fictional edit");
  await click("item-submit-button");
  expect(persist).not.toHaveBeenCalled();
  expect(drafts.get("item:berts").draftRevision).toBe(10);
  expect(find("item-name-input").value).toBe("Retained fictional edit");
});

test("new item appends to the latest catalog and uses its latest available control number", async () => {
  await act(async () => root.render(<SetupTab {...revisionProps(10)} />));
  await act(async () => root.render(<SetupTab {...revisionProps(11)} />));
  await changeInput(find("item-name-input"),"Fictional new item");
  await click("item-submit-button");
  expect(persist).toHaveBeenCalledWith(expect.any(Array),11);
  persist.mockClear(); success.mockClear();
  await changeInput(find("item-name-input"),"Second fictional draft");
  const added = { ...item, controlNumber: "F-002", itemCode: "second_food", name: "Another fictional item" };
  await act(async () => root.render(<SetupTab {...revisionProps(12,[item,added])} />));
  await click("item-submit-button");
  expect(persist).toHaveBeenCalledWith([item,added,expect.objectContaining({controlNumber:"F-003",name:"Second fictional draft"})],12);
  await changeInput(find("item-name-input"),"Discardable fictional draft");
  await act(async () => [...container.querySelectorAll("button")].find(b => b.textContent.includes("Cancel")).click());
  expect(find("item-name-input").value).toBe("");
});

test("409 then a same-item refresh refuses retry without a second persist", async () => {
  const drafts = new Map();
  await act(async () => root.render(<SetupTab key="conflict" {...revisionProps(10,[item],drafts)} />));
  await click("edit-item-F01");
  persist.mockRejectedValueOnce({response:{status:409,data:{detail:"Catalog changed elsewhere"}}});
  await click("item-submit-button");
  expect(success).not.toHaveBeenCalled(); expect(drafts.get("item:berts").draftRevision).toBe(10);
  expect(find("item-name-input").value).toBe(item.name);
  await act(async () => root.render(<SetupTab {...revisionProps(11,[{...item,par:1}],drafts)} />));
  await click("item-submit-button");
  expect(persist).toHaveBeenCalledTimes(1); expect(success).not.toHaveBeenCalled();
  expect(drafts.get("item:berts").draftRevision).toBe(10);
});

test("409 then an unrelated refresh allows a guarded retry while preserving new records", async () => {
  await act(async () => root.render(<SetupTab {...revisionProps(10)} />));
  await click("edit-item-F01"); await changeInput(parInput(),"2");
  persist.mockRejectedValueOnce({response:{status:409,data:{detail:"Catalog changed elsewhere"}}});
  await click("item-submit-button");
  const other = {...item,controlNumber:"F02",itemCode:"other_food",par:9};
  await act(async () => root.render(<SetupTab {...revisionProps(11,[item,other])} />));
  await click("item-submit-button");
  expect(persist).toHaveBeenLastCalledWith([expect.objectContaining({par:"2"}),other],11);
  expect(persist).toHaveBeenCalledTimes(2); expect(success).toHaveBeenCalledTimes(1);
});

test("explicit item recovery preserves independent local and remote edits and exact supplier data", async () => {
  const base = {...item,vendorSkus:[{...item.vendorSkus[0],basePerPurchaseUnit:null}]};
  const latest = {...base,notes:"Remote metadata",vendorSkus:[{...base.vendorSkus[0],price:"98765432109876543210.000000000009"}]};
  const load = jest.fn().mockResolvedValue({revision:11,items:[latest]});
  await act(async () => root.render(<SetupTab {...revisionProps(10,[base])} onCatalogLinked={load} />));
  await click("edit-item-F01"); await changeInput(parInput(),"2");
  await act(async () => root.render(<SetupTab {...revisionProps(11,[latest])} onCatalogLinked={load} />));
  await click("item-submit-button"); expect(persist).not.toHaveBeenCalled();
  await click("review-item-draft"); expect(persist).not.toHaveBeenCalled();
  await click("item-submit-button");
  const saved = persist.mock.calls[0][0][0];
  expect(saved.par).toBe("2"); expect(saved.notes).toBe("Remote metadata");
  expect(saved.vendorSkus[0].price).toBe(latest.vendorSkus[0].price);
  expect(saved.vendorSkus[0].basePerPurchaseUnit).toBeNull();
  expect(saved).not.toHaveProperty("draftBase"); expect(saved).not.toHaveProperty("draftRevision");
  expect(persist.mock.calls[0][1]).toBe(11);
});

test("overlapping item changes are named and retained until explicitly resolved", async () => {
  await act(async () => root.render(<SetupTab {...revisionProps(10)} />));
  await click("edit-item-F01"); await changeInput(parInput(),"2");
  await act(async () => root.render(<SetupTab {...revisionProps(11,[{...item,par:1}])} />));
  await click("review-item-draft");
  expect(container.querySelector('[role="alert"]').textContent).toContain("Conflicting item changes: par");
  expect(parInput().value).toBe("2"); await click("item-submit-button"); expect(persist).not.toHaveBeenCalled();
  await changeInput(parInput(),"1"); await click("review-item-draft"); await click("item-submit-button");
  expect(persist).toHaveBeenCalledWith([expect.objectContaining({par:"1"})],11);
});

test("recovery refuses coupled pack and supplier changes even across different fields", async () => {
  await act(async () => root.render(<SetupTab {...revisionProps(10)} />)); await click("edit-item-F01");
  const pack = [...container.querySelectorAll("label")].find(label => label.textContent.startsWith("Pack Count")).querySelector("input");
  await changeInput(pack,"6");
  const latest = {...item,vendorSkus:[{...item.vendorSkus[0],basePerPurchaseUnit:24}]};
  await act(async () => root.render(<SetupTab {...revisionProps(11,[latest])} />));
  await click("review-item-draft");
  expect(container.querySelector('[role="alert"]').textContent).toContain("pack, portion and supplier details");
  expect(pack.value).toBe("6"); expect(persist).not.toHaveBeenCalled();
});

test.each([{latest:[]},{latest:[{...item,itemCode:"replacement_food"}]}])("removed or replaced items cannot be resurrected by recovery", async ({latest}) => {
  await act(async () => root.render(<SetupTab {...revisionProps(10)} />)); await click("edit-item-F01");
  await changeInput(find("item-name-input"),"Retained fictional name");
  await act(async () => root.render(<SetupTab {...revisionProps(11,latest)} />));
  await click("review-item-draft"); await click("item-submit-button");
  expect(persist).not.toHaveBeenCalled(); expect(find("item-name-input").value).toBe("Retained fictional name");
});

test("late item recovery reads cannot replace typing that happened while reading", async () => {
  let complete;
  const load = jest.fn().mockReturnValue(new Promise(resolve => {complete=resolve;}));
  await act(async () => root.render(<SetupTab {...revisionProps(10)} onCatalogLinked={load} />)); await click("edit-item-F01");
  act(() => find("review-item-draft").click());
  await changeInput(find("item-name-input"),"Newer typing");
  await act(async () => complete({revision:11,items:[{...item,par:1}]}));
  expect(find("item-name-input").value).toBe("Newer typing"); expect(parInput().value).toBe("0");
});

test.each(["same","returned","away"])("typing during new item creation retains its saved identity across navigation (%s)", async navigate => {
  const drafts=new Map();
  let complete;persist.mockImplementationOnce(()=>new Promise(resolve=>{complete=resolve;}));
  await act(async()=>root.render(<SetupTab key="creation" {...revisionProps(10,[item],drafts)} />));
  await changeInput(find("item-name-input"),"New fictional item");
  act(()=>find("item-submit-button").click());await changeInput(find("item-name-input"),"Later fictional name");
  if(navigate!=="same")await act(async()=>root.render(<p>Other location</p>));
  if(navigate==="returned")await act(async()=>root.render(<SetupTab {...revisionProps(10,[item],drafts)} />));
  const submitted=persist.mock.calls[0][0].at(-1),canonical={...submitted,itemCode:"canonical_new_item"};
  await act(async()=>complete({revision:11,items:[item,canonical]}));
  await act(async()=>root.render(<SetupTab key={navigate==="same"?"creation":undefined} {...revisionProps(11,[item,canonical],drafts)} />));
  expect(find("item-name-input").value).toBe("Later fictional name");await click("item-submit-button");
  expect(persist).toHaveBeenCalledTimes(1);
  await click("review-item-draft");await click("item-submit-button");
  expect(persist.mock.calls[1][0]).toHaveLength(2);
  expect(persist.mock.calls[1][0].find(row=>row.itemCode===canonical.itemCode).name).toBe("Later fictional name");
  expect(persist.mock.calls[1][0].at(-1)).not.toHaveProperty("draftToken");
  expect(persist.mock.calls[1][0].at(-1)).not.toHaveProperty("receiptReviewRequired");
});

test("revision-only native creation receipt keeps the submitted identity until a fresh canonical read",async()=>{
  api.isPostgres=true;let complete;persist.mockImplementationOnce(()=>new Promise(resolve=>{complete=resolve;}));
  await act(async()=>root.render(<SetupTab {...revisionProps(10)} />));await changeInput(find("item-name-input"),"New native item");
  act(()=>find("item-submit-button").click());await changeInput(find("item-name-input"),"Later native name");
  const submitted=persist.mock.calls[0][0].at(-1);
  const canonical={...submitted,itemCode:`berts_${submitted.controlNumber}`,basePerCountUnit:20,vendorSkus:[{...submitted.vendorSkus[0],id:"saved_sku",vendorSku:submitted.vendorSkus[0].id,basePerPurchaseUnit:null}]};
  await act(async()=>complete({revision:11}));await act(async()=>root.render(<SetupTab {...revisionProps(11,[item,canonical])} />));
  await click("item-submit-button");expect(persist).toHaveBeenCalledTimes(1);
  await click("review-item-draft");await click("item-submit-button");
  const saved=persist.mock.calls[1][0].at(-1);
  expect(saved.itemCode).toBe(canonical.itemCode);expect(saved.basePerCountUnit).toBe(20);
  expect(saved.vendorSkus).toEqual(canonical.vendorSkus);expect(saved.name).toBe("Later native name");
});

test("a cancelled creation draft cannot receive the old receipt identity",async()=>{
  let complete;persist.mockImplementationOnce(()=>new Promise(resolve=>{complete=resolve;}));
  await act(async()=>root.render(<SetupTab {...revisionProps(10)} />));await changeInput(find("item-name-input"),"First draft");
  act(()=>find("item-submit-button").click());
  await act(async()=>[...container.querySelectorAll("button")].find(b=>b.textContent.includes("Cancel")).click());
  await changeInput(find("item-name-input"),"Different new draft");
  const canonical={...persist.mock.calls[0][0].at(-1),itemCode:"first_created"};
  await act(async()=>complete({revision:11,items:[item,canonical]}));
  await act(async()=>root.render(<SetupTab {...revisionProps(11,[item,canonical])} />));
  expect(find("review-item-draft")).toBeNull();await click("item-submit-button");
  expect(persist.mock.calls[1][0]).toHaveLength(3);expect(persist.mock.calls[1][0].at(-1).name).toBe("Different new draft");
});
test("an ordinary item edit preserves activation, actor, canonical units and exact supplier fields", async () => {
  await click("edit-item-F01"); await click("item-submit-button");
  const saved=persist.mock.calls[0][0][0];
  expect(saved.active).toBe(true);expect(saved.countActive).toBe(false);expect(saved.lastCountedBy).toBe(item.lastCountedBy);
  expect(saved.itemCode).toBe("stable_food");expect(saved.countUnit).toBe("bag");expect(saved.basePerCountUnit).toBe(25);
  expect(saved.vendorSkus[0].price).toBe(item.vendorSkus[0].price);expect(saved.vendorSkus[0].packDescription).toBe(item.vendorSkus[0].packDescription);
});
test("count toggle does not retire a catalog item", async () => {
  await click("edit-item-F01");await click("count-active-toggle");await click("item-submit-button");
  const saved=persist.mock.calls[0][0][0];expect(saved.active).toBe(true);expect(saved.countActive).toBe(true);
});
test("retiring preserves the complete item and count participation", async () => {
  jest.spyOn(window,"confirm").mockReturnValue(true);await click("delete-item-F01");
  const saved=persist.mock.calls[0][0];expect(saved).toHaveLength(1);expect(saved[0]).toEqual({ ...item, active:false, orderEnabled:false, salesTracked:false });
  expect(success.mock.calls[0][0]).toContain("history and physical counts retained");
});
test("failed retirement leaves the visible item and produces no success", async () => {
  persist.mockResolvedValueOnce(null);jest.spyOn(window,"confirm").mockReturnValue(true);await click("delete-item-F01");
  expect(find("setup-item-row-F01")).not.toBeNull();expect(success).not.toHaveBeenCalled();
});
test("shared product fields are held while local flags and supplier prices stay editable", async () => {
  api.catalogMappingEnabled=true;
  await act(async () => root.render(<SetupTab rid="berts" items={[{...item,sharedStoreCount:2}]} areas={[{name:"Freezer",prefix:"F"}]} persistItems={persist} persistAreas={persist} showToast={success} />));
  await click("edit-item-F01");expect(find("item-name-input").disabled).toBe(true);expect(find("add-vendor-sku-button").disabled).toBe(true);
  expect(find("count-active-toggle").disabled).toBe(false);expect(container.querySelector('[aria-label="Supplier price sku"]').disabled).toBe(false);
});
test("unknown pack and portion metadata survives an untouched edit as null", async () => {
  const nullable={...item,packCount:null,unitQty:null,portionSize:null,vendorSkus:[{...item.vendorSkus[0],packCount:null,unitQty:null,price:null}]};
  await act(async () => root.render(<SetupTab rid="berts" items={[nullable]} areas={[{name:"Freezer",prefix:"F"}]} persistItems={persist} persistAreas={persist} showToast={success} />));
  await click("edit-item-F01");await click("item-submit-button");const saved=persist.mock.calls[0][0][0];
  expect(saved.packCount).toBeNull();expect(saved.unitQty).toBeNull();expect(saved.portionSize).toBeNull();expect(saved.vendorSkus[0].packCount).toBeNull();expect(saved.vendorSkus[0].price).toBeNull();
});

test("typing with native catalog and count panels enabled keeps one count panel and one initial read", async () => {
  api.catalogMappingEnabled=true;api.actualInventoryEnabled=true;api.supplierContactsEnabled=true;
  const warnings=jest.spyOn(console,"error").mockImplementation(()=>{});
  api.nativeOperatingSummary.mockClear();
  await act(async () => root.render(<SetupTab rid="berts" items={[item]} areas={[{name:"Freezer",prefix:"F"}]} persistItems={persist} persistAreas={persist} showToast={success} />));
  const input=find("item-name-input");
  const setValue=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,"value").set;
  for (const name of ["T","TE","TES","TEST","TEST ONLY"]) {
    await act(async () => {setValue.call(input,name);input.dispatchEvent(new Event("input",{bubbles:true}));});
  }
  expect(container.querySelectorAll('[data-testid="native-inventory-position"]')).toHaveLength(1);
  expect(api.nativeOperatingSummary).toHaveBeenCalledTimes(1);
  await act(async () => root.render(<SetupTab rid="rudds" items={[item]} areas={[{name:"Freezer",prefix:"F"}]} persistItems={persist} persistAreas={persist} showToast={success} />));
  expect(container.querySelectorAll('[data-testid="native-inventory-position"]')).toHaveLength(1);
  expect(api.nativeOperatingSummary).toHaveBeenCalledTimes(2);
  expect(api.nativeOperatingSummary).toHaveBeenLastCalledWith("rudds");
  expect(warnings.mock.calls.some(call=>String(call[0]).includes("same key"))).toBe(false);
});

test("saved unknown supplier conversion opens the existing review and retains the item draft", async () => {
  api.nativePurchasesEnabled = true;
  const nullable = { ...item, vendorSkus: [{ ...item.vendorSkus[0], basePerPurchaseUnit: null }] };
  const review = jest.fn(), drafts = new Map();
  const props = { rid: "berts", items: [nullable], areas: [{ name: "Freezer", prefix: "F" }], persistItems: persist, persistAreas: persist, showToast: success, onVerifySupplier: review, drafts };
  // Remount to use the shared App draft cache from the start.
  await act(async () => root.render(<SetupTab key="review" {...props} />));
  await click("edit-item-F01"); await click("verify-supplier-0");
  expect(review).toHaveBeenCalledWith({ itemCode: "stable_food", skuId: "sku" });
  expect(persist).not.toHaveBeenCalled(); expect(drafts.get("item:berts").vendorSkus[0].basePerPurchaseUnit).toBeNull();
  await act(async () => root.render(<p>Invoice Master</p>));
  await act(async () => root.render(<SetupTab {...props} />));
  expect(find("item-name-input").value).toBe("Invented food");
  await click("item-submit-button"); expect(persist.mock.calls[0][0][0].vendorSkus[0].basePerPurchaseUnit).toBeNull();
});

test("pack edits warn without rewriting a stored conversion and must be saved before review", async () => {
  api.nativePurchasesEnabled = true;
  const review = jest.fn();
  await act(async () => root.render(<SetupTab rid="berts" items={[item]} areas={[{name:"Freezer",prefix:"F"}]} persistItems={persist} persistAreas={persist} showToast={success} onVerifySupplier={review} />));
  await click("edit-item-F01"); expect(find("verify-supplier-0").disabled).toBe(false);
  const pack = [...find("vendor-sku-row-0").querySelectorAll("label")].find(label => label.textContent === "Pack Count").querySelector("input");
  await act(async () => { Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(pack, "5"); pack.dispatchEvent(new Event("input", {bubbles:true})); });
  expect(container.textContent).toContain("Stored conversion differs from pack details: confirm or keep");
  expect(find("verify-supplier-0").disabled).toBe(true); await click("verify-supplier-0"); expect(review).not.toHaveBeenCalled();
  await click("item-submit-button"); expect(persist.mock.calls[0][0][0].vendorSkus[0].basePerPurchaseUnit).toBe(20);
  expect(persist.mock.calls[0][0][0].vendorSkus[0].packCount).toBe("5");
});

test("editing a pack leaves an unknown conversion null and new supplier rows require a save", async () => {
  api.nativePurchasesEnabled = true;
  const nullable = { ...item, vendorSkus: [{ ...item.vendorSkus[0], basePerPurchaseUnit: null }] };
  await act(async () => root.render(<SetupTab rid="berts" items={[nullable]} areas={[{name:"Freezer",prefix:"F"}]} persistItems={persist} persistAreas={persist} showToast={success} onVerifySupplier={jest.fn()} />));
  await click("edit-item-F01");
  const pack = [...find("vendor-sku-row-0").querySelectorAll("label")].find(label => label.textContent === "Pack Count").querySelector("input");
  await act(async () => { Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(pack, "6"); pack.dispatchEvent(new Event("input", {bubbles:true})); });
  await click("add-vendor-sku-button"); expect(find("verify-supplier-1").disabled).toBe(true);
  await click("item-submit-button"); expect(persist.mock.calls[0][0][0].vendorSkus[0].basePerPurchaseUnit).toBeNull();
});
