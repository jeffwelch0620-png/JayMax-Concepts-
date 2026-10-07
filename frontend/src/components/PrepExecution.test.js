import React,{act} from "react";
import {createRoot} from "react-dom/client";
import {PrepExecution} from "./PrepExecution";
import * as api from "../lib/api";
jest.mock("../lib/api",()=>({prepExecution:jest.fn(),nativePrepBatchSetup:jest.fn(),previewPrepExecution:jest.fn(),savePrepExecution:jest.fn()}));
const hash="b".repeat(64),draftHash="a".repeat(64);
const base={store_id:"berts",prep_date:"2026-10-08",track:"daily",revision:0,status:"draft",draft_version_id:"draft",draft:{id:"draft",list_id:"list",store_id:"berts",revision:1,review_hash:draftHash,review_snapshot:{prep_date:"2026-10-08",track:"daily"}},release:null,
  tasks:[{id:"task",included:true,planned_quantity:"4",product_id:"product",recipe_version_id:"recipe",task_snapshot:{name:"Sauce",source_unit:"lb"}}],completions:[],history:[]};
const batch={id:"batch",root_id:"batch",store_id:"berts",business_date:"2026-10-08",kind:"initial",source_kind:"production",product_id:"product",recipe_version_id:"recipe",base_unit:"lb",performed_at:"2026-10-08T10:00:00-04:00",review_snapshot:{usableBaseOutput:"3"}};
const release={id:"release",action:"release",draft_version_id:"draft"};
const released={...base,revision:1,status:"released",release};
let container,root,drafts,toast,changed;
const button=text=>[...container.querySelectorAll("button")].find(e=>e.textContent===text);
const input=label=>container.querySelector(`[aria-label="${label}"]`);
const click=async el=>act(async()=>el.click());
async function set(label,value){const el=input(label);await act(async()=>{const proto=el.tagName==="SELECT"?HTMLSelectElement.prototype:HTMLTextAreaElement.prototype;Object.getOwnPropertyDescriptor(proto,"value").set.call(el,value);el.dispatchEvent(new Event(el.tagName==="SELECT"?"change":"input",{bubbles:true}));});}
const render=async(day="2026-10-08",key=day)=>act(async()=>root.render(<PrepExecution key={key} rid="berts" day={day} track="daily" drafts={drafts} showToast={toast} onChange={changed}/>));
async function prepare(){await set("Prep execution reason","Reviewed service");await click(button("Preview prep command"));await click(input("Review prep execution"));}
function acknowledgement(body,version,key,current){
  const event={id:"event",list_id:"list",store_id:"berts",revision:version+1,action:body.command.action,draft_version_id:body.command.draft_version_id,review_hash:body.expected_review_hash,review_snapshot:{command:body.command}};
  const after=current||(["link","finish","reconcile"].includes(body.command.action)?{...progressState(progress({effective_base_quantity:"3",reviewed_base_quantity:"3",status:"in_progress"})),revision:version+1,history:[event]}:{...released,revision:version+1,history:[event]});return {request_key:key,event,current:after,replayed:false};
}
beforeEach(async()=>{
  jest.clearAllMocks();global.IS_REACT_ACT_ENVIRONMENT=true;Object.defineProperty(window,"crypto",{value:{randomUUID:()=>"key"},configurable:true});
  api.prepExecution.mockResolvedValue(base);api.nativePrepBatchSetup.mockResolvedValue({events:[batch]});
  api.previewPrepExecution.mockImplementation((rid,day,track,command,version)=>Promise.resolve({reviewHash:hash,review:{store_id:rid,prep_date:day,track,base_revision:version,command,draft_review_hash:draftHash,status_after:command.action==="reopen"?"draft":"released",task:["complete","link","finish","reconcile"].includes(command.action)?base.tasks[0]:null,batch:["complete","link"].includes(command.action)?batch:null,progress_before:progress(),original_link:null}}));
  api.savePrepExecution.mockImplementation((rid,day,track,body,version,key)=>Promise.resolve(acknowledgement(body,version,key)));
  drafts=new Map();toast=jest.fn();changed=jest.fn();container=document.createElement("div");document.body.appendChild(container);root=createRoot(container);await render();
});
afterEach(async()=>{await act(async()=>root.unmount());container.remove();});
test("release saves an explicitly reviewed command against the observed execution version",async()=>{
  await prepare();await click(button("Save reviewed prep command"));
  expect(api.savePrepExecution).toHaveBeenCalledWith("berts","2026-10-08","daily",{command:{action:"release",draft_version_id:"draft",reason:"Reviewed service",task_id:null,batch_event_id:null},expected_review_hash:hash,reviewed:true},0,"key");
  expect(container.textContent).toContain("Execution version 1 · released");expect(changed).toHaveBeenCalledTimes(1);expect(toast).toHaveBeenCalledTimes(1);
});
test("completion preview shows measured output independently of planned quantity",async()=>{
  api.prepExecution.mockResolvedValue(released);await click(button("Refresh prep execution"));await set("Prep execution action","complete");await set("Prep execution task","task");await set("Prep execution batch","batch");await prepare();
  expect(container.textContent).toContain("Measured output: 3 lb");expect(api.previewPrepExecution.mock.calls[0][3]).toEqual({action:"complete",draft_version_id:"draft",reason:"Reviewed service",task_id:"task",batch_event_id:"batch"});
});
test("changing evidence invalidates the reviewed command",async()=>{
  await prepare();await set("Prep execution reason","Changed decision");expect(input("Review prep execution")).toBeNull();expect(button("Save reviewed prep command").disabled).toBe(true);
});
test("uncertain command retains its exact body and key across signed navigation",async()=>{
  await prepare();api.savePrepExecution.mockRejectedValueOnce(new Error("Response lost"));await click(button("Save reviewed prep command"));expect(button("Refresh prep execution").disabled).toBe(true);
  await render("2026-10-08","remount");await click(button("Retry same prep command"));expect(api.savePrepExecution.mock.calls[0]).toEqual(api.savePrepExecution.mock.calls[1]);expect(toast).toHaveBeenCalledTimes(1);
});
test("partial or mismatched acknowledgement cannot clear the uncertain request",async()=>{
  await prepare();api.savePrepExecution.mockResolvedValue({request_key:"wrong",current:released});await click(button("Save reviewed prep command"));expect(button("Retry same prep command")).toBeDefined();expect(toast).not.toHaveBeenCalled();expect(changed).not.toHaveBeenCalled();
});
test("a conflict retains the reason and requires refreshing then previewing again",async()=>{
  await prepare();api.savePrepExecution.mockRejectedValueOnce({response:{status:409,data:{detail:"Execution changed"}}});await click(button("Save reviewed prep command"));expect(input("Prep execution reason").value).toBe("Reviewed service");
  api.prepExecution.mockResolvedValue({...base,revision:2});await click(button("Refresh prep execution"));await click(button("Preview prep command"));expect(api.previewPrepExecution.mock.calls[1][4]).toBe(2);expect(button("Save reviewed prep command").disabled).toBe(true);
});
test("replay displays the current reopened state instead of the old release",async()=>{
  await prepare();api.savePrepExecution.mockImplementation((rid,day,track,body,version,key)=>{const r=acknowledgement(body,version,key);return Promise.resolve({...r,replayed:true,current:{...base,revision:2,history:[r.event]}});});
  await click(button("Save reviewed prep command"));expect(container.textContent).toContain("Execution version 2 · draft");expect(toast).toHaveBeenCalledTimes(1);
});
test("late completion acknowledgement cannot change another service day",async()=>{
  await prepare();let resolve;api.savePrepExecution.mockImplementation((rid,day,track,body,version,key)=>new Promise(r=>{resolve=()=>r(acknowledgement(body,version,key));}));await click(button("Save reviewed prep command"));
  api.prepExecution.mockResolvedValue({...base,prep_date:"2026-10-09",draft:null,draft_version_id:null});await render("2026-10-09");await act(async()=>resolve());expect(toast).not.toHaveBeenCalled();expect(changed).not.toHaveBeenCalled();
});
test("unconfirmed preview cannot enable a command save",async()=>{
  api.previewPrepExecution.mockResolvedValue({reviewHash:hash,review:{store_id:"rudds"}});await set("Prep execution reason","Reviewed");await click(button("Preview prep command"));expect(button("Save reviewed prep command").disabled).toBe(true);expect(api.savePrepExecution).not.toHaveBeenCalled();
});
test("batch corrections remain visibly flagged against the original completion",async()=>{
  api.prepExecution.mockResolvedValue({...released,revision:2,completions:[{execution_id:"completion",task_id:"task",effective_batch:{...batch,kind:"void",review_snapshot:{usableBaseOutput:null}},needs_review:true}]});await click(button("Refresh prep execution"));expect(container.textContent).toContain("Batch corrected or voided; manager review required");
  await set("Prep execution action","complete");expect(input("Prep execution task").options).toHaveLength(1);
});
const progress=(changes={})=>({task_id:"task",closed:false,needs_review:false,links:[],planned_base_quantity:"4",effective_base_quantity:"0",reviewed_base_quantity:"0",status:"open",...changes});
const progressState=(p=progress(),links=[])=>({...released,progress_supported:true,task_progress:[p],completions:links});
async function loadProgress(p=progress(),links=[]){api.prepExecution.mockResolvedValue(progressState(p,links));await click(button("Refresh prep execution"));}
test("partial production remains open and displays independent reviewed and planned totals",async()=>{
  await loadProgress(progress({links:[{execution_id:"link"}],effective_base_quantity:"3",reviewed_base_quantity:"3",status:"in_progress"}));
  expect(container.textContent).toContain("planned 4, current recorded 3, reviewed 3");
  await set("Prep execution action","link");await set("Prep execution task","task");await set("Prep execution batch","batch");
  api.previewPrepExecution.mockImplementation((rid,day,track,command,version)=>Promise.resolve({reviewHash:hash,review:{store_id:rid,prep_date:day,track,base_revision:version,command,draft_review_hash:draftHash,status_after:"released",task:base.tasks[0],batch,progress_before:progress({links:[{execution_id:"link"}],effective_base_quantity:"3",reviewed_base_quantity:"3",status:"in_progress"}),original_link:null}}));
  await prepare();expect(api.previewPrepExecution.mock.calls[0][3]).toEqual({action:"link",draft_version_id:"draft",reason:"Reviewed service",task_id:"task",batch_event_id:"batch",link_event_id:null,task_complete:null});
});
test("finish selects existing progress without requiring another production batch",async()=>{
  const p=progress({effective_base_quantity:"3",reviewed_base_quantity:"3",status:"in_progress"});await loadProgress(p);
  await set("Prep execution action","finish");await set("Prep execution task","task");expect(input("Prep execution batch")).toBeNull();
  api.previewPrepExecution.mockImplementation((rid,day,track,command,version)=>Promise.resolve({reviewHash:hash,review:{store_id:rid,prep_date:day,track,base_revision:version,command,draft_review_hash:draftHash,status_after:"released",task:base.tasks[0],batch:null,progress_before:p,original_link:null}}));
  await prepare();expect(api.previewPrepExecution.mock.calls[0][3].batch_event_id).toBeNull();expect(api.previewPrepExecution.mock.calls[0][3].action).toBe("finish");
});
test("void reconciliation requires a selected original link, latest void and explicit open outcome",async()=>{
  const voided={...batch,id:"void",kind:"void",review_snapshot:{usableBaseOutput:null}},p=progress({closed:true,needs_review:true,status:"needs_review",links:[{execution_id:"link"}]}),link={execution_id:"link",task_id:"task",effective_batch:voided,needs_review:true};
  await loadProgress(p,[link]);await set("Prep execution action","reconcile");await set("Prep execution task","task");await set("Prep reconciliation link","link");await set("Prep execution batch","void");
  expect([...input("Prep reconciliation outcome").options].find(o=>o.value==="complete").disabled).toBe(true);
  await set("Prep execution reason","Reviewed void");await click(button("Preview prep command"));expect(api.previewPrepExecution).not.toHaveBeenCalled();
  await set("Prep reconciliation outcome","open");api.previewPrepExecution.mockImplementation((rid,day,track,command,version)=>Promise.resolve({reviewHash:hash,review:{store_id:rid,prep_date:day,track,base_revision:version,command,draft_review_hash:draftHash,status_after:"released",task:base.tasks[0],batch:voided,progress_before:p,original_link:{id:"link",review_snapshot:{batch}}}}));
  await click(button("Preview prep command"));expect(container.textContent).toContain("Voided production: task must reopen");expect(api.previewPrepExecution.mock.calls[0][3].task_complete).toBe(false);
});
test("uncertain partial requests retain their exact additional evidence fields on navigation",async()=>{
  await loadProgress();await set("Prep execution action","link");await set("Prep execution task","task");await set("Prep execution batch","batch");await prepare();
  api.savePrepExecution.mockRejectedValueOnce(new Error("Lost response"));await click(button("Save reviewed prep command"));
  await render("2026-10-08","progress-remount");await click(button("Retry same prep command"));expect(api.savePrepExecution.mock.calls[0]).toEqual(api.savePrepExecution.mock.calls[1]);
  expect(api.savePrepExecution.mock.calls[1][3].command.link_event_id).toBeNull();expect(toast).toHaveBeenCalledTimes(1);
});
test("mismatched progress evidence prevents a partial preview from being reviewed",async()=>{
  await loadProgress();await set("Prep execution action","link");await set("Prep execution task","task");await set("Prep execution batch","batch");
  api.previewPrepExecution.mockImplementation((rid,day,track,command,version)=>Promise.resolve({reviewHash:hash,review:{store_id:rid,prep_date:day,track,base_revision:version,command,draft_review_hash:draftHash,status_after:"released",task:base.tasks[0],batch,progress_before:progress({reviewed_base_quantity:"999"})}}));
  await set("Prep execution reason","Reviewed");await click(button("Preview prep command"));expect(input("Review prep execution")).toBeNull();expect(api.savePrepExecution).not.toHaveBeenCalled();
});
