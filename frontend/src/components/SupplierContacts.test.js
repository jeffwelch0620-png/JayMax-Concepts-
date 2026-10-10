import React,{act} from "react";
import {createRoot} from "react-dom/client";
import {SupplierContacts} from "./SupplierContacts";
import * as api from "../lib/api";
jest.mock("../lib/api",()=>({supplierContacts:jest.fn(),saveSupplierContact:jest.fn()}));
const contact={store_id:"berts",vendor_id:"supplier",vendor_name:"Invented supplier",vendor_active:true,vendor_version:1,version:0,order_email:"",event_id:null};
const data={store_id:"berts",contacts:[contact],legacy_contacts:[{vendor:"Old name",raw_record:{order_email:"old@example.invalid"}}]};
let root,container,toast,drafts;
const button=text=>[...container.querySelectorAll("button")].find(b=>b.textContent===text);
const input=label=>container.querySelector(`[aria-label="${label}"]`);
const click=async el=>act(async()=>el.click());
async function set(label,value){const el=input(label);await act(async()=>{const proto=el.tagName==="SELECT"?HTMLSelectElement.prototype:el.tagName==="TEXTAREA"?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;Object.getOwnPropertyDescriptor(proto,"value").set.call(el,value);el.dispatchEvent(new Event(el.tagName==="SELECT"?"change":"input",{bubbles:true}));});}
const render=async(rid="berts",key=rid)=>act(async()=>root.render(<SupplierContacts key={key} rid={rid} drafts={drafts} showToast={toast}/>));
const saved=(email="orders@example.invalid",version=1,event="event")=>({...contact,order_email:email,version,event_id:event});
const ack=c=>({request_key:"key",contact:c,current_contact:c,replayed:false});
async function prepare(){await set("Contact supplier","supplier");await set("Supplier order email","orders@example.invalid");await set("Contact edit reason","Verified by manager");}
beforeEach(async()=>{
  jest.clearAllMocks();global.IS_REACT_ACT_ENVIRONMENT=true;
  Object.defineProperty(window,"crypto",{value:{randomUUID:()=>"key"},configurable:true});
  api.supplierContacts.mockResolvedValue(data);api.saveSupplierContact.mockResolvedValue(ack(saved()));
  toast=jest.fn();drafts=new Map();container=document.createElement("div");document.body.appendChild(container);root=createRoot(container);await render();await prepare();
});
afterEach(async()=>{await act(async()=>root.unmount());container.remove();});
test("saving uses stable supplier identity and the observed contact and supplier versions",async()=>{
  await click(button("Save reviewed contact"));
  expect(api.saveSupplierContact).toHaveBeenCalledWith("berts","supplier",{order_email:"orders@example.invalid",expected_vendor_version:1,note:"Verified by manager",legacy_vendor:null,verified:false},0,"key");
  expect(toast).toHaveBeenCalledWith("Supplier contact saved.");expect(container.textContent).toContain("Contact version 1");
});
test("blank email is an explicit reviewed clear",async()=>{
  await set("Supplier order email","");api.saveSupplierContact.mockResolvedValue(ack(saved("")));await click(button("Save reviewed contact"));
  expect(api.saveSupplierContact.mock.calls[0][2].order_email).toBe("");expect(toast).toHaveBeenCalledTimes(1);
});
test("uncertain saves retain the exact request and survive tab remount within the session",async()=>{
  api.saveSupplierContact.mockRejectedValueOnce(new Error("Lost response"));await click(button("Save reviewed contact"));
  expect(input("Supplier order email").disabled).toBe(true);expect(button("Refresh contact versions").disabled).toBe(true);expect(toast).not.toHaveBeenCalled();
  await render("berts","remount");expect(input("Supplier order email").value).toBe("orders@example.invalid");
  await click(button("Retry the same contact save"));expect(api.saveSupplierContact.mock.calls[0]).toEqual(api.saveSupplierContact.mock.calls[1]);expect(toast).toHaveBeenCalledTimes(1);
});
test("mismatched acknowledgement cannot clear the request or announce success",async()=>{
  api.saveSupplierContact.mockResolvedValue(ack(saved("wrong@example.invalid")));await click(button("Save reviewed contact"));
  expect(container.textContent).toContain("was not confirmed");expect(button("Retry the same contact save")).toBeDefined();expect(toast).not.toHaveBeenCalled();
});
test("stale rejection retains input and explicit refresh rebases reviewed versions",async()=>{
  api.saveSupplierContact.mockRejectedValueOnce({response:{status:409,data:{detail:"Contact changed"}}});await click(button("Save reviewed contact"));
  expect(input("Supplier order email").value).toBe("orders@example.invalid");expect(input("Contact edit reason").value).toBe("Verified by manager");
  api.supplierContacts.mockResolvedValue({...data,contacts:[{...contact,version:2,vendor_version:3,order_email:"other@example.invalid",event_id:"other"}]});
  await click(button("Refresh contact versions"));expect(input("Supplier order email").value).toBe("orders@example.invalid");expect(container.textContent).toContain("other@example.invalid");
  api.saveSupplierContact.mockResolvedValue(ack(saved("orders@example.invalid",3)));await click(button("Save reviewed contact"));
  expect(api.saveSupplierContact.mock.calls[1][3]).toBe(2);expect(api.saveSupplierContact.mock.calls[1][2].expected_vendor_version).toBe(3);
});
test("legacy mapping requires explicit verification and preserves the chosen source identity",async()=>{
  await set("Preserved contact","Old name");await click(button("Save reviewed contact"));expect(api.saveSupplierContact).not.toHaveBeenCalled();
  await click(input("Verify preserved supplier contact"));api.saveSupplierContact.mockResolvedValue(ack(saved("old@example.invalid")));await click(button("Save reviewed contact"));
  expect(api.saveSupplierContact.mock.calls[0][2]).toMatchObject({legacy_vendor:"Old name",verified:true,order_email:"old@example.invalid"});expect(container.textContent).not.toContain("await explicit supplier mapping");
});
test("a replay displays the current email rather than the original acknowledged value",async()=>{
  api.saveSupplierContact.mockResolvedValue({request_key:"key",replayed:true,contact:saved(),current_contact:saved("newer@example.invalid",3,"newer")});
  await click(button("Save reviewed contact"));expect(input("Supplier order email").value).toBe("newer@example.invalid");expect(container.textContent).toContain("Contact version 3");expect(toast).toHaveBeenCalledTimes(1);
});
test("a previous location's late save cannot change the active location",async()=>{
  let resolve;api.saveSupplierContact.mockReturnValue(new Promise(r=>{resolve=r;}));await click(button("Save reviewed contact"));
  api.supplierContacts.mockResolvedValue({store_id:"rudds",contacts:[{...contact,store_id:"rudds"}],legacy_contacts:[]});await render("rudds");
  await act(async()=>resolve(ack(saved())));expect(toast).not.toHaveBeenCalled();expect(input("Contact supplier").value).toBe("");
  await set("Contact supplier","supplier");expect(container.textContent).toContain("No saved email");expect(input("Supplier order email").value).toBe("");
});
test("an in-flight refresh blocks a save until its read is confirmed",async()=>{
  let resolve;api.supplierContacts.mockReturnValue(new Promise(r=>{resolve=r;}));await click(button("Refresh contact versions"));expect(button("Save reviewed contact").disabled).toBe(true);
  await act(async()=>resolve(data));expect(button("Save reviewed contact").disabled).toBe(false);
});
test("switching suppliers retains each unsaved email and reason",async()=>{
  api.supplierContacts.mockResolvedValue({...data,contacts:[contact,{...contact,vendor_id:"other",vendor_name:"Other supplier"}]});await click(button("Refresh contact versions"));
  await set("Contact supplier","other");await set("Supplier order email","other@example.invalid");await set("Contact edit reason","Other review");
  await set("Contact supplier","supplier");expect(input("Supplier order email").value).toBe("orders@example.invalid");expect(input("Contact edit reason").value).toBe("Verified by manager");
  await set("Contact supplier","other");expect(input("Supplier order email").value).toBe("other@example.invalid");expect(input("Contact edit reason").value).toBe("Other review");
});
