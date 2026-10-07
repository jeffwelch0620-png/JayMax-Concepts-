import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { SupplierPriceHistory } from "./SupplierPriceHistory";
import * as api from "../lib/api";
jest.mock("../lib/api", () => ({ supplierPriceReview: jest.fn(), adoptSupplierPrice: jest.fn() }));
const sku="11111111-1111-4111-8111-111111111111";
const candidate={ line_id:"line",document_number:"TEST",goods_received_date:"2026-10-04",price:"20.000000000000000009",issues:[],plan_hash:"hash" };
const review={ current:{vendor_item_id:sku,price:null,purchase_unit:"case",effective_date:null},history:[],candidates:[candidate],revision:4,offset:0,has_more:false };
const saved={ event:{id:"event",vendor_item_id:sku,price:candidate.price,source:"invoice",request_key:"synthetic-key",effective_date:candidate.goods_received_date,basis_snapshot:{line_id:"line"}},revision:5 };
const items=[{controlNumber:"R01",name:"Invented food",vendorSkus:[{id:sku,vendor:"Invented supplier",vendorSku:"00001"}]}];
let root,container,onSaved,toast;
const label=text=>container.querySelector(`[aria-label="${text}"]`);
const button=text=>[...container.querySelectorAll("button")].find(b=>b.textContent===text);
const click=async el=>act(async()=>el.click());
const input=async(text,value)=>{const el=label(text);await act(async()=>{Object.getOwnPropertyDescriptor(el.tagName==="SELECT" ? HTMLSelectElement.prototype : HTMLInputElement.prototype,"value").set.call(el,value);el.dispatchEvent(new Event(el.tagName==="SELECT" ? "change" : "input",{bubbles:true}));});};
const render=async rid=>act(async()=>root.render(<SupplierPriceHistory key={rid} restaurantId={rid} items={items} onSaved={onSaved} showToast={toast} />));
beforeEach(async()=>{
  jest.clearAllMocks();global.IS_REACT_ACT_ENVIRONMENT=true;
  Object.defineProperty(window,"crypto",{value:{randomUUID:jest.fn(()=>"synthetic-key")},configurable:true});
  api.supplierPriceReview.mockResolvedValue(review);api.adoptSupplierPrice.mockResolvedValue(saved);
  onSaved=jest.fn();toast=jest.fn();container=document.createElement("div");document.body.appendChild(container);root=createRoot(container);await render("rudds");
});
afterEach(async()=>{await act(async()=>root.unmount());container.remove();});
async function form(){await input("Price history supplier",sku);await click(button("Load price history"));await input("Receipt planning price","line");await input("Price review note","Verified receipt and pack");await click(label("Confirm receipt planning price"));}
test("reviewed exact price sends source identity and hash, and announces only a confirmed save",async()=>{
  await form();await click(button("Adopt receipt planning price"));
  expect(api.adoptSupplierPrice).toHaveBeenCalledWith("rudds",sku,{line_id:"line",expected_plan_hash:"hash",verified:true,note:"Verified receipt and pack"},"synthetic-key");
  expect(onSaved).toHaveBeenCalledTimes(1);expect(toast).toHaveBeenCalledTimes(1);expect(container.textContent).toContain("Actual Food Cost independently");
});
test("uncertain saves retain the review and replay the same request key",async()=>{
  api.adoptSupplierPrice.mockRejectedValueOnce(new Error("Lost connection"));await form();await click(button("Adopt receipt planning price"));
  expect(label("Price review note").value).toBe("Verified receipt and pack");expect(label("Price history supplier").disabled).toBe(true);
  expect(onSaved).not.toHaveBeenCalled();await click(button("Retry the same price review"));
  expect(api.adoptSupplierPrice.mock.calls[0]).toEqual(api.adoptSupplierPrice.mock.calls[1]);expect(onSaved).toHaveBeenCalledTimes(1);
});
test("mismatched acknowledgements retain the review and do not announce success",async()=>{
  api.adoptSupplierPrice.mockResolvedValue({...saved,event:{...saved.event,price:"0"}});await form();await click(button("Adopt receipt planning price"));
  expect(container.textContent).toContain("was not confirmed");expect(onSaved).not.toHaveBeenCalled();expect(toast).not.toHaveBeenCalled();
  expect(label("Price review note").value).toBe("Verified receipt and pack");
});
test("held receipts cannot be adopted and unknown catalog prices remain explicit",async()=>{
  api.supplierPriceReview.mockResolvedValue({...review,candidates:[{...candidate,price:null,issues:["Receipt predates current price"]}]});await form();
  expect(button("Adopt receipt planning price").disabled).toBe(true);expect(container.textContent).toContain("Unknown / needs review");expect(container.textContent).toContain("Receipt predates");
});
test("stale rejection retains notes and refresh requires confirmation again",async()=>{
  api.adoptSupplierPrice.mockRejectedValue({response:{status:409,data:{detail:["Source changed"]}}});await form();await click(button("Adopt receipt planning price"));
  expect(container.textContent).toContain("Source changed");expect(label("Price review note").value).toBe("Verified receipt and pack");
  await click(button("Load price history"));expect(label("Confirm receipt planning price").checked).toBe(false);expect(onSaved).not.toHaveBeenCalled();
});
test("a previous location's late save cannot announce success in the new location",async()=>{
  let resolve;api.adoptSupplierPrice.mockReturnValue(new Promise(r=>{resolve=r;}));await form();await click(button("Adopt receipt planning price"));await render("berts");
  await act(async()=>resolve(saved));expect(onSaved).not.toHaveBeenCalled();expect(toast).not.toHaveBeenCalled();
});
test("a previous supplier read cannot replace a newly selected supplier review",async()=>{
  let resolve;api.supplierPriceReview.mockReturnValue(new Promise(r=>{resolve=r;}));await input("Price history supplier",sku);await click(button("Load price history"));await input("Price history supplier","");
  await act(async()=>resolve(review));expect(label("Receipt planning price")).toBeNull();
});
