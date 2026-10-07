import React,{act} from "react";
import {createRoot} from "react-dom/client";
import {PrepDayDrafts} from "./PrepDayDrafts";
import * as api from "../lib/api";
jest.mock("../lib/api",()=>({prepDayDraft:jest.fn(),previewPrepDayDraft:jest.fn(),savePrepDayDraft:jest.fn()}));
jest.mock("../lib/calc",()=>({todayISO:()=>"2026-10-08"}));
const hash="a".repeat(64),inputs={track:"daily",day_group:"weekday",count_event_id:null,overrides:[],note:"Reviewed day"};
const task={product_id:"product",name:"Invented prep",source_unit:"lb",mode:"target_par",included:true,planned_quantity:null,issue:"Physical prep count is missing"};
const review=(body=inputs,version=0)=>({store_id:"berts",prep_date:"2026-10-08",track:"daily",base_revision:version,inputs:body,status:"draft",execution_ready:false,unresolved_tasks:1,tasks:[task]});
const saved=(revision=1,body=inputs)=>({id:`version-${revision}`,list_id:"list",store_id:"berts",revision,status:"draft",review_hash:hash,review_snapshot:review(body,revision-1)});
const data={store_id:"berts",prep_date:"2026-10-08",track:"daily",current:null,counts:[],planning:{plans:[{id:"plan",product_id:"product",unit_profile_id:"unit",active:true,track:"daily"}],products:[{product_id:"product",name:"Invented prep"}],unitProfiles:[{id:"unit",source_unit:"lb"}]}};
let root,container,drafts,toast;
const button=text=>[...container.querySelectorAll("button")].find(b=>b.textContent===text);
const input=label=>container.querySelector(`[aria-label="${label}"]`);
const click=async el=>act(async()=>el.click());
async function set(label,value){const el=input(label);await act(async()=>{const proto=el.tagName==="SELECT"?HTMLSelectElement.prototype:el.tagName==="TEXTAREA"?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;Object.getOwnPropertyDescriptor(proto,"value").set.call(el,value);el.dispatchEvent(new Event(el.tagName==="SELECT"?"change":"input",{bubbles:true}));});}
const render=async(rid="berts",track="daily",key=rid)=>act(async()=>root.render(<PrepDayDrafts key={key} rid={rid} track={track} drafts={drafts} showToast={toast}/>));
async function prepare(){await set("Prep draft reason","Reviewed day");await click(button("Preview dated tasks"));await click(input("Review dated prep draft"));}
beforeEach(async()=>{
  jest.clearAllMocks();global.IS_REACT_ACT_ENVIRONMENT=true;Object.defineProperty(window,"crypto",{value:{randomUUID:()=>"key"},configurable:true});
  api.prepDayDraft.mockResolvedValue(data);api.previewPrepDayDraft.mockImplementation((rid,day,body,version)=>Promise.resolve({reviewHash:hash,review:review(body,version)}));
  api.savePrepDayDraft.mockImplementation((rid,day,body,version)=>Promise.resolve({request_key:"key",draft:saved(version+1,body.draft),current_draft:saved(version+1,body.draft),replayed:false}));
  drafts=new Map();toast=jest.fn();container=document.createElement("div");document.body.appendChild(container);root=createRoot(container);await render();await prepare();
});
afterEach(async()=>{await act(async()=>root.unmount());container.remove();});
test("dated draft saves the reviewed snapshot and preserves unknown quantities",async()=>{
  expect(container.textContent).toContain("Unknown lb");await click(button("Save reviewed dated draft"));expect(api.savePrepDayDraft).toHaveBeenCalledWith("berts","2026-10-08",{draft:inputs,expected_review_hash:hash,reviewed:true},0,"key");expect(toast).toHaveBeenCalledWith("Dated prep draft saved.");expect(container.textContent).toContain("Saved draft version 1");
});
test("changing a day override invalidates the preview and requires another review",async()=>{
  await set("Day override plan","fixed_quantity");await set("Day quantity plan",".5000");await set("Day reason plan","Reviewed demand");expect(input("Review dated prep draft")).toBeNull();expect(button("Save reviewed dated draft").disabled).toBe(true);
  await click(button("Preview dated tasks"));await click(input("Review dated prep draft"));await click(button("Save reviewed dated draft"));expect(api.savePrepDayDraft.mock.calls[0][2].draft.overrides).toEqual([{planning_version_id:"plan",kind:"fixed_quantity",quantity:"0.5",reason:"Reviewed demand"}]);
});
test("uncertain dated saves retain the exact request through navigation",async()=>{
  api.savePrepDayDraft.mockRejectedValueOnce(new Error("Response lost"));await click(button("Save reviewed dated draft"));expect(button("Refresh dated draft versions").disabled).toBe(true);
  await render("berts","daily","remount");await click(button("Retry the same dated save"));expect(api.savePrepDayDraft.mock.calls[0]).toEqual(api.savePrepDayDraft.mock.calls[1]);expect(toast).toHaveBeenCalledTimes(1);
});
test("a mismatched save acknowledgement cannot clear the exact request",async()=>{
  api.savePrepDayDraft.mockResolvedValue({request_key:"wrong",draft:saved(),current_draft:saved()});await click(button("Save reviewed dated draft"));expect(toast).not.toHaveBeenCalled();expect(button("Retry the same dated save")).toBeDefined();
});
test("a stale conflict retains day edits and refresh uses the new observed version",async()=>{
  api.savePrepDayDraft.mockRejectedValueOnce({response:{status:409,data:{detail:"Sources changed"}}});await click(button("Save reviewed dated draft"));expect(input("Prep draft reason").value).toBe("Reviewed day");
  api.prepDayDraft.mockResolvedValue({...data,current:saved(2,{...inputs,note:"Other manager"})});await click(button("Refresh dated draft versions"));expect(input("Prep draft reason").value).toBe("Reviewed day");
  await click(button("Preview dated tasks"));await click(input("Review dated prep draft"));await click(button("Save reviewed dated draft"));expect(api.savePrepDayDraft.mock.calls[1][3]).toBe(2);
});
test("a replay shows the current draft rather than restoring the older acknowledged overrides",async()=>{
  api.savePrepDayDraft.mockResolvedValue({request_key:"key",draft:saved(),current_draft:saved(3,{...inputs,day_group:"weekend",note:"Newer saved day"}),replayed:true});await click(button("Save reviewed dated draft"));expect(input("Prep draft reason").value).toBe("Newer saved day");expect(input("Prep draft par group").value).toBe("weekend");expect(toast).toHaveBeenCalledTimes(1);
});
test("a late save from another day cannot alter the selected day",async()=>{
  let resolve;api.savePrepDayDraft.mockReturnValue(new Promise(r=>{resolve=r;}));await click(button("Save reviewed dated draft"));api.prepDayDraft.mockResolvedValue({...data,prep_date:"2026-10-09"});await set("Prep draft date","2026-10-09");await act(async()=>resolve({request_key:"key",draft:saved(),current_draft:saved()}));expect(toast).not.toHaveBeenCalled();expect(input("Prep draft reason").value).toBe("");
});
test("an unconfirmed preview cannot enable a dated save",async()=>{
  await set("Prep draft reason","Changed reason");api.previewPrepDayDraft.mockResolvedValue({reviewHash:hash,review:{...review(),prep_date:"2026-10-09"}});await click(button("Preview dated tasks"));expect(button("Save reviewed dated draft").disabled).toBe(true);expect(api.savePrepDayDraft).not.toHaveBeenCalled();
});
test("a released draft holds day edits and previews while allowing a confirmed refresh",async()=>{
  api.prepDayDraft.mockResolvedValue({...data,current:saved(),execution_status:"released"});await click(button("Refresh dated draft versions"));
  expect(input("Prep draft reason").disabled).toBe(false); // fieldset supplies the actual disabled behavior
  expect(input("Prep draft reason").closest("fieldset").disabled).toBe(true);
  expect(button("Preview dated tasks").disabled).toBe(true);expect(button("Save reviewed dated draft").disabled).toBe(true);
  expect(button("Refresh dated draft versions").disabled).toBe(false);expect(container.textContent).toContain("Released draft is held for execution");
});
