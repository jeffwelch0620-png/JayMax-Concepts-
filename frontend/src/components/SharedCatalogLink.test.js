import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { SharedCatalogLink } from "./SharedCatalogLink";
import * as api from "../lib/api";
jest.mock("../lib/api", () => ({ sharedCatalog: jest.fn(), linkSharedItem: jest.fn() }));
const product = { item_code: "canonical_food", name: "Invented food", base_unit: "lb", linked: false, catalog_hash: "hash", supplier_products: [{ id:"sku",vendor_name:"Invented supplier",vendor_sku:"00001",purchase_unit:"case",vendor_description:"Original 4 / 5 LB" }] };
let root, container, linked, toast;
const input = async (label,value) => { const el=container.querySelector(`[aria-label="${label}"]`);await act(async () => { Object.getOwnPropertyDescriptor(el.tagName==="SELECT" ? HTMLSelectElement.prototype : HTMLInputElement.prototype,"value").set.call(el,value);el.dispatchEvent(new Event(el.tagName==="SELECT" ? "change":"input",{bubbles:true})); }); };
const click = async el => act(async () => el.click());
const byLabel = label => container.querySelector(`[aria-label="${label}"]`);
const button = text => [...container.querySelectorAll("button")].find(b => b.textContent===text);
const render = rid => act(async () => root.render(<SharedCatalogLink key={rid} restaurantId={rid} onLinked={linked} showToast={toast} />));
beforeEach(async () => {
  jest.clearAllMocks();global.IS_REACT_ACT_ENVIRONMENT=true;
  api.sharedCatalog.mockResolvedValue({ products:[product],revision:4 });
  api.linkSharedItem.mockResolvedValue({ ok:true,itemCode:"canonical_food",controlNumber:"R01",revision:5 });
  linked=jest.fn();toast=jest.fn();container=document.createElement("div");document.body.appendChild(container);root=createRoot(container);await render("rudds");
});
afterEach(async () => {await act(async () => root.unmount());container.remove();});
async function form() {
  await input("Shared purchased product","canonical_food");await click(byLabel("Link supplier sku"));
  await input("Linked product control number","R01");await input("Linked product count unit","bag");await input("Linked product physical factor","2.000000000001");
  await click(byLabel("Confirm shared product identity"));
}
test("explicit product and SKU selection sends the reviewed identity, exact physical factor and revision", async () => {
  expect(api.linkSharedItem).not.toHaveBeenCalled();await form();await click(button("Link product to this location"));
  expect(api.linkSharedItem).toHaveBeenCalledWith("rudds",{ item_code:"canonical_food",control_number:"R01",storage_area:null,count_unit:"bag",base_per_count_unit:"2.000000000001",vendor_item_ids:["sku"],verified:true,expected_catalog_hash:"hash" },4);
  expect(linked).toHaveBeenCalledTimes(1);expect(toast).toHaveBeenCalledTimes(1);expect(byLabel("Linked product control number").value).toBe("");
});
test("a stale rejected link retains the form and does not announce success", async () => {
  api.linkSharedItem.mockRejectedValue({ response:{status:409,data:{detail:"Shared product changed; refresh"}} });
  await form();await click(button("Link product to this location"));expect(byLabel("Linked product control number").value).toBe("R01");
  expect(container.textContent).toContain("Shared product changed");expect(linked).not.toHaveBeenCalled();expect(toast).not.toHaveBeenCalled();
});
test("an unconfirmed acknowledgement retains the draft and holds duplicate attempts", async () => {
  api.linkSharedItem.mockResolvedValue({ok:true,itemCode:"wrong_product",controlNumber:"R01",revision:5});await form();await click(button("Link product to this location"));
  expect(byLabel("Linked product control number").value).toBe("R01");expect(button("Link product to this location").disabled).toBe(true);expect(linked).not.toHaveBeenCalled();
  expect(container.textContent).toContain("outcome is uncertain");
});
test("already linked products cannot infer another membership or supplier selection", async () => {
  api.sharedCatalog.mockResolvedValue({products:[{...product,linked:true}],revision:5});await click(button("Refresh shared products"));await input("Shared purchased product","canonical_food");
  expect(button("Link product to this location").disabled).toBe(true);expect(byLabel("Link supplier sku").checked).toBe(false);expect(container.textContent).toContain("already registered here");
});
test("refresh reopens review without erasing entered location settings", async () => {
  await form();await click(button("Refresh shared products"));expect(byLabel("Linked product control number").value).toBe("R01");
  expect(byLabel("Confirm shared product identity").checked).toBe(false);expect(button("Link product to this location").disabled).toBe(true);
});
test("a completion from the previous location cannot refresh or clear the new location", async () => {
  let resolve;api.linkSharedItem.mockReturnValue(new Promise(r=>{resolve=r;}));await form();await click(button("Link product to this location"));await render("berts");
  await act(async () => resolve({ok:true,itemCode:"canonical_food",controlNumber:"R01",revision:5}));expect(linked).not.toHaveBeenCalled();expect(toast).not.toHaveBeenCalled();
});
