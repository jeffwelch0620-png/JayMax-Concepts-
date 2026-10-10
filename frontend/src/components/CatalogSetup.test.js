import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { SetupTab } from "./SetupTab";
import * as api from "../lib/api";
jest.mock("../lib/api", () => ({ __esModule: true, listVendorContacts: jest.fn(), sharedCatalog: jest.fn(), catalogMappingEnabled: false }));
const item = { controlNumber: "F01", itemCode: "stable_food", name: "Invented food", storageArea: "Freezer", active: true, countActive: false, orderEnabled: true, salesTracked: true, par: 0,
  baseUnit: "lb", countUnit: "bag", basePerCountUnit: 25, lastCounted: "2026-10-01", lastCountedBy: "Invented counter", currentStock: 7,
  packCount: 4, unitQty: 5, unitUOM: "lb", portionSize: 4, portionUOM: "oz", purchaseUnit: "case", itemType: "portion",
  vendorSkus: [{ id: "sku", vendorId: "pfg", vendor: "PFG", vendorSku: "00001", packDescription: "  Original supplier description  ", price: "12345678901234567890.000000000001", priceSource: "invoice", priceUpdatedAt: "2026-10-01", purchaseUnit: "case", packCount: 4, unitQty: 5, unitUOM: "lb", basePerPurchaseUnit: 20 }] };
let root, container, persist, success;
const find = id => container.querySelector(`[data-testid="${id}"]`);
const click = id => act(async () => find(id).click());
beforeEach(async () => {
  global.IS_REACT_ACT_ENVIRONMENT = true; api.listVendorContacts.mockResolvedValue([]);
  api.catalogMappingEnabled=false;api.sharedCatalog.mockResolvedValue({products:[],revision:1});
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
