import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { SetupTab } from "./SetupTab";
import * as api from "../lib/api";
import { resetComponentApiMock } from "../testHelpers/componentApiMock";
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
  const pack = find("vendor-sku-row-0").querySelector('input[type="number"]');
  await act(async () => { Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(pack, "5"); pack.dispatchEvent(new Event("input", {bubbles:true})); });
  expect(container.textContent).toContain("Stored conversion differs from pack details: confirm or keep");
  expect(find("verify-supplier-0").disabled).toBe(true); await click("verify-supplier-0"); expect(review).not.toHaveBeenCalled();
  await click("item-submit-button"); expect(persist.mock.calls[0][0][0].vendorSkus[0].basePerPurchaseUnit).toBe(20);
  expect(persist.mock.calls[0][0][0].vendorSkus[0].packCount).toBe(5);
});

test("editing a pack leaves an unknown conversion null and new supplier rows require a save", async () => {
  api.nativePurchasesEnabled = true;
  const nullable = { ...item, vendorSkus: [{ ...item.vendorSkus[0], basePerPurchaseUnit: null }] };
  await act(async () => root.render(<SetupTab rid="berts" items={[nullable]} areas={[{name:"Freezer",prefix:"F"}]} persistItems={persist} persistAreas={persist} showToast={success} onVerifySupplier={jest.fn()} />));
  await click("edit-item-F01");
  const pack = find("vendor-sku-row-0").querySelector('input[type="number"]');
  await act(async () => { Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(pack, "6"); pack.dispatchEvent(new Event("input", {bubbles:true})); });
  await click("add-vendor-sku-button"); expect(find("verify-supplier-1").disabled).toBe(true);
  await click("item-submit-button"); expect(persist.mock.calls[0][0][0].vendorSkus[0].basePerPurchaseUnit).toBeNull();
});
