import React,{act} from "react";
import {createRoot} from "react-dom/client";
import {NativeOrderWorkflow} from "./NativeOrderWorkflow";
import * as api from "../lib/api";
jest.mock("../lib/api",()=>({listOrders:jest.fn(),orderCommand:jest.fn()}));
jest.mock("./NativeOrderReceiving",()=>({NativeOrderReceiving:()=> <div>Receipt review</div>}));
const po={id:"po_test",restaurantId:"berts",status:"draft",vendor:"Invented supplier",creatorActor:"manager",orderVersion:3,total:null,lines:[{name:"Food",vendorSku:"001",qty:"1.5",purchaseUnit:"case",unitCost:null}]};
let root,container,toast;
const button=text=>[...container.querySelectorAll("button")].find(b=>b.textContent===text);
const click=async el=>act(async()=>el.click());
const render=async rid=>act(async()=>root.render(<NativeOrderWorkflow key={rid} rid={rid} showToast={toast}/>));
beforeEach(async()=>{
  jest.clearAllMocks();global.IS_REACT_ACT_ENVIRONMENT=true;
  Object.defineProperty(window,"crypto",{value:{randomUUID:()=>"key"},configurable:true});
  api.listOrders.mockResolvedValue([po]);api.orderCommand.mockResolvedValue({request_key:"key",order:{...po,status:"pending",orderVersion:5}});
  toast=jest.fn();container=document.createElement("div");document.body.appendChild(container);root=createRoot(container);await render("berts");
});
afterEach(async()=>{await act(async()=>root.unmount());container.remove();});
test("a reviewed transition carries the observed order version and confirms its result",async()=>{
  expect(container.textContent).toContain("unknown / incomplete");expect(container.textContent).toContain("Price unknown");await click(button("submit"));
  expect(api.orderCommand).toHaveBeenCalledWith("berts","po_test",{action:"submit",note:""},3,"key");expect(container.textContent).toContain("pending");expect(toast).toHaveBeenCalledTimes(1);
});
test("an uncertain command retries the identical request without clearing the review",async()=>{
  api.orderCommand.mockRejectedValueOnce(new Error("Lost connection"));await click(button("submit"));
  expect(toast).not.toHaveBeenCalled();expect(button("Refresh reviewed orders").disabled).toBe(true);await click(button("Retry the same order command"));
  expect(api.orderCommand.mock.calls[0]).toEqual(api.orderCommand.mock.calls[1]);expect(toast).toHaveBeenCalledTimes(1);
});
test("a mismatched state or stale acknowledgement cannot announce success",async()=>{
  api.orderCommand.mockResolvedValue({request_key:"key",order:{...po,status:"pending",orderVersion:3}});await click(button("submit"));
  expect(container.textContent).toContain("was not confirmed");expect(toast).not.toHaveBeenCalled();expect(container.textContent).toContain("draft");
});
test("archiving requires an acknowledged archive and retains no false delete success",async()=>{
  api.orderCommand.mockResolvedValue({request_key:"key",order:{...po,archivedAt:"2026-10-06T12:00:00Z",orderVersion:6}});await click(button("archive"));
  expect(container.textContent).not.toContain("po_test");expect(toast).toHaveBeenCalledWith("Order archived with its history retained.");
});
test("a stale rejection allows refresh and retains the entered reason",async()=>{
  const el=container.querySelector('textarea');await act(async()=>{Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,"value").set.call(el,"Keep this review");el.dispatchEvent(new Event("input",{bubbles:true}));});
  api.orderCommand.mockRejectedValue({response:{status:409,data:{detail:"Order changed"}}});await click(button("submit"));
  expect(container.querySelector('textarea').value).toBe("Keep this review");expect(button("Refresh reviewed orders").disabled).toBe(false);expect(toast).not.toHaveBeenCalled();
});
test("a previous location's late command cannot change the new location",async()=>{
  let resolve;api.orderCommand.mockReturnValue(new Promise(r=>{resolve=r;}));await click(button("submit"));api.listOrders.mockResolvedValue([]);await render("rudds");
  await act(async()=>resolve({request_key:"key",order:{...po,status:"pending",orderVersion:5}}));expect(toast).not.toHaveBeenCalled();expect(container.textContent).not.toContain("po_test");
});
test("a replay acknowledges the original transition and displays the newer current order",async()=>{
  api.orderCommand.mockResolvedValue({request_key:"key",replayed:true,order:{...po,status:"pending",orderVersion:5},current_order:{...po,status:"approved",orderVersion:7}});
  await click(button("submit"));expect(container.textContent).toContain("approved");expect(container.textContent).toContain("Version 7");expect(button("approve")).toBeUndefined();expect(toast).toHaveBeenCalledTimes(1);
});
