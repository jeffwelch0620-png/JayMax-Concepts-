import React,{act} from "react";
import {createRoot} from "react-dom/client";
import {PrepPlanning} from "./PrepPlanning";
import * as api from "../lib/api";
jest.mock("../lib/api",()=>({prepPlanning:jest.fn(),savePrepPlan:jest.fn()}));
const body={action:"save",recipe_version_id:"recipe",unit_profile_id:"unit",track:"bulk",schedule:"daily",weekday_par:"2.123456789012",weekend_par:"7",recur_days:[],fixed_quantity:null,note:"Reviewed values",verified:true};
const saved=(revision=1,changes={})=>({...body,id:`plan-${revision}`,product_id:"product",store_id:"berts",revision,active:true,...changes});
const data={store_id:"berts",products:[{product_id:"product",name:"Invented prep"}],recipes:[{id:"recipe",product_id:"product",product_version_id:"definition",revision:1,reviewNeeded:false}],unitProfiles:[{id:"unit",product_version_id:"definition",source_unit:"lb",base_units_per_source_unit:"1"}],plans:[],legacy_sources:[]};
const ack=(p=saved(),current=p)=>({request_key:"key",plan:p,current_plan:current,replayed:current!==p});
let root,container,drafts,toast;
const button=text=>[...container.querySelectorAll("button")].find(b=>b.textContent===text);
const input=label=>container.querySelector(`[aria-label="${label}"]`);
const click=async el=>act(async()=>el.click());
async function set(label,value){const el=input(label);await act(async()=>{const proto=el.tagName==="SELECT"?HTMLSelectElement.prototype:el.tagName==="TEXTAREA"?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;Object.getOwnPropertyDescriptor(proto,"value").set.call(el,value);el.dispatchEvent(new Event(el.tagName==="SELECT"?"change":"input",{bubbles:true}));});}
const render=async(rid="berts",key=rid)=>act(async()=>root.render(<PrepPlanning key={key} rid={rid} drafts={drafts} showToast={toast}/>));
async function prepare(){await set("Planning product","product");await set("Planning recipe","recipe");await set("Planning unit","unit");await set("Planning track","bulk");await set("Planning weekday par","2.123456789012");await set("Planning weekend par","7");await set("Planning edit reason","Reviewed values");await click(input("Verify planning values"));}
beforeEach(async()=>{
  jest.clearAllMocks();global.IS_REACT_ACT_ENVIRONMENT=true;Object.defineProperty(window,"crypto",{value:{randomUUID:()=>"key"},configurable:true});
  api.prepPlanning.mockResolvedValue(data);api.savePrepPlan.mockResolvedValue(ack());drafts=new Map();toast=jest.fn();container=document.createElement("div");document.body.appendChild(container);root=createRoot(container);await render();await prepare();
});
afterEach(async()=>{await act(async()=>root.unmount());container.remove();});
test("save preserves separate exact pars, identities and the observed version",async()=>{
  await click(button("Save reviewed plan"));expect(api.savePrepPlan).toHaveBeenCalledWith("berts","product",body,0,"key");expect(toast).toHaveBeenCalledWith("Prep planning saved.");expect(container.textContent).toContain("Saved version 1");
});
test("uncertain save retains an exact retry through tab remount",async()=>{
  api.savePrepPlan.mockRejectedValueOnce(new Error("Lost response"));await click(button("Save reviewed plan"));expect(input("Planning weekday par").closest("fieldset").disabled).toBe(true);expect(button("Refresh planning versions").disabled).toBe(true);
  await render("berts","remount");await click(button("Retry the same planning save"));expect(api.savePrepPlan.mock.calls[0]).toEqual(api.savePrepPlan.mock.calls[1]);expect(toast).toHaveBeenCalledTimes(1);
});
test("a mismatched acknowledgement retains the exact request without claiming success",async()=>{
  api.savePrepPlan.mockResolvedValue(ack(saved(1,{weekend_par:"99"})));await click(button("Save reviewed plan"));expect(toast).not.toHaveBeenCalled();expect(button("Retry the same planning save")).toBeDefined();expect(input("Planning weekend par").value).toBe("7");
});
test("a stale rejection retains quantities and refresh requires another review",async()=>{
  api.savePrepPlan.mockRejectedValueOnce({response:{status:409,data:{detail:"Planning changed"}}});await click(button("Save reviewed plan"));expect(input("Planning weekday par").value).toBe("2.123456789012");
  api.prepPlanning.mockResolvedValue({...data,plans:[saved(2,{weekday_par:"8"})]});await click(button("Refresh planning versions"));expect(input("Planning weekday par").value).toBe("2.123456789012");expect(input("Verify planning values").checked).toBe(false);
  await click(button("Save reviewed plan"));expect(api.savePrepPlan).toHaveBeenCalledTimes(1);await click(input("Verify planning values"));api.savePrepPlan.mockResolvedValue(ack(saved(3)));await click(button("Save reviewed plan"));expect(api.savePrepPlan.mock.calls[1][3]).toBe(2);
});
test("recurring weekdays and quantity use the selected unit",async()=>{
  await set("Planning schedule","recurring");await click(input("Planning Sun"));await click(input("Planning Mon"));await set("Planning fixed quantity","1.234567890123");await click(input("Verify planning values"));
  const changes={schedule:"recurring",recur_days:[0,6],fixed_quantity:"1.234567890123"};api.savePrepPlan.mockResolvedValue(ack(saved(1,changes)));await click(button("Save reviewed plan"));expect(api.savePrepPlan.mock.calls[0][2]).toMatchObject(changes);expect(toast).toHaveBeenCalledTimes(1);
});
test("retirement preserves planning quantities and recipe references",async()=>{
  await click(button("Save reviewed plan"));await set("Planning edit reason","Retire with history");api.savePrepPlan.mockResolvedValue(ack(saved(2,{active:false,note:"Retire with history"})));await click(button("Retire plan with history"));
  expect(api.savePrepPlan.mock.calls[1][2]).toEqual({action:"retire",note:"Retire with history"});expect(container.textContent).toContain("Saved version 2: retired");expect(input("Planning weekday par").value).toBe("2.123456789012");
});
test("a replay shows the current plan rather than restoring an older acknowledged par",async()=>{
  api.savePrepPlan.mockResolvedValue(ack(saved(),saved(3,{weekday_par:"9",active:false})));await click(button("Save reviewed plan"));expect(input("Planning weekday par").value).toBe("9");expect(container.textContent).toContain("Saved version 3: retired");expect(toast).toHaveBeenCalledTimes(1);
});
test("a late save from the previous location cannot change the active location",async()=>{
  let resolve;api.savePrepPlan.mockReturnValue(new Promise(r=>{resolve=r;}));await click(button("Save reviewed plan"));api.prepPlanning.mockResolvedValue({...data,store_id:"rudds"});await render("rudds");await act(async()=>resolve(ack()));expect(toast).not.toHaveBeenCalled();expect(input("Planning product").value).toBe("");
});
test("plain decimal spellings match the confirmed quantity without floating point conversion",async()=>{
  await set("Planning weekday par",".5000");await click(input("Verify planning values"));api.savePrepPlan.mockResolvedValue(ack(saved(1,{weekday_par:"0.5"})));await click(button("Save reviewed plan"));expect(api.savePrepPlan.mock.calls[0][2].weekday_par).toBe(".5000");expect(toast).toHaveBeenCalledTimes(1);
});
test("an invalid quantity remains in the draft without creating a request",async()=>{
  await set("Planning weekend par","NaN");await click(input("Verify planning values"));await click(button("Save reviewed plan"));expect(api.savePrepPlan).not.toHaveBeenCalled();expect(input("Planning weekend par").value).toBe("NaN");expect(toast).not.toHaveBeenCalled();
});
