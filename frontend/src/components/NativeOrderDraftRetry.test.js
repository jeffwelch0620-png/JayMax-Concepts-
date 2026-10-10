import React,{act} from "react";
import {createRoot} from "react-dom/client";
import {NativeOrderPlanner} from "./NativeOrderPlanner";
import * as api from "../lib/api";
jest.mock("../lib/api",()=>({orderWorkflowEnabled:true,createVersionedOrder:jest.fn(),currentSession:()=>({user:{email:"reviewer@example.invalid"}})}));
jest.mock("./NativeInventoryPosition",()=>({NativeInventoryPosition:()=>null}));
const items=[{itemCode:"canonical",controlNumber:"F01",name:"Food",classification:"raw",active:true,orderEnabled:true,par:2,vendorSkus:[{id:"sku",vendorId:"supplier",vendor:"Supplier",vendorSku:"001",purchaseUnit:"case",price:null,available:true}]}];
let container,root,toast;
const button=text=>[...container.querySelectorAll("button")].find(b=>b.textContent===text);
const click=async el=>act(async()=>el.click());
const input=async(label,value)=>{const el=container.querySelector(`[aria-label="${label}"]`);await act(async()=>{Object.getOwnPropertyDescriptor(el.tagName==="TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype,"value").set.call(el,value);el.dispatchEvent(new Event("input",{bubbles:true}));});};
beforeEach(async()=>{
  jest.clearAllMocks();global.IS_REACT_ACT_ENVIRONMENT=true;Object.defineProperty(window,"crypto",{value:{randomUUID:()=>"key"},configurable:true});
  api.createVersionedOrder.mockImplementation((rid,body,key)=>Promise.resolve({request_key:key,order:{...body,id:"saved",orderVersion:3,restaurantId:rid,status:"draft"}}));
  toast=jest.fn();container=document.createElement("div");document.body.appendChild(container);root=createRoot(container);await act(async()=>root.render(<NativeOrderPlanner rid="berts" items={items} showToast={toast}/>));
});
afterEach(async()=>{await act(async()=>root.unmount());container.remove();});
async function form(){await input("Order quantity canonical","1.500000000001");await input("Order planning evidence","Physical quantities reviewed");await click(container.querySelector('[aria-label="Confirm reviewed order quantities"]'));}
test("draft creation preserves exact quantity, supplier identity and an unknown estimate",async()=>{
  await form();await click(button("Create reviewed draft for Supplier"));
  expect(api.createVersionedOrder.mock.calls[0][1]).toMatchObject({vendorId:"supplier",lines:[{itemCode:"canonical",qty:"1.500000000001",unitCost:null}]});
  expect(toast).toHaveBeenCalledTimes(1);
});
test("a lost draft acknowledgement reuses the same reviewed body and request",async()=>{
  api.createVersionedOrder.mockRejectedValueOnce(new Error("Lost connection"));await form();await click(button("Create reviewed draft for Supplier"));
  expect(toast).not.toHaveBeenCalled();await click(button("Retry the same reviewed draft"));
  expect(api.createVersionedOrder.mock.calls[0]).toEqual(api.createVersionedOrder.mock.calls[1]);expect(toast).toHaveBeenCalledTimes(1);
});
test("unknown prices changed to zero in an acknowledgement do not confirm a draft",async()=>{
  api.createVersionedOrder.mockImplementation((rid,body,key)=>Promise.resolve({request_key:key,order:{...body,id:"saved",orderVersion:3,restaurantId:rid,status:"draft",lines:body.lines.map(l=>({...l,unitCost:"0"}))}}));
  await form();await click(button("Create reviewed draft for Supplier"));expect(toast).not.toHaveBeenCalled();expect(container.textContent).toContain("was not confirmed");
});
