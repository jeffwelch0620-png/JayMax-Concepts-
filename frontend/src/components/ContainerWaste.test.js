import React,{act} from "react";
import {createRoot} from "react-dom/client";
import {PrepContainers,validContainerState,validContainerAck,validContainerWasteReview,reversibleWasteMoves} from "./PrepContainers";
import * as api from "../lib/api";
jest.mock("../lib/api",()=>({prepContainers:jest.fn(),previewPrepContainer:jest.fn(),savePrepContainer:jest.fn()}));
const id=n=>`00000000-0000-4000-8000-${String(n).padStart(12,"0")}`;
const stamp={performed_at:"2026-10-05T13:00:00-04:00",business_date:"2026-10-05",timezone_name:"America/New_York",calendar_date_confirmed:true,note:"Measured spoilage"};
const fill={id:id(1),store_id:"berts",profile_id:id(2),source_batch_id:id(3),product_id:id(4),base_unit:"lb",quantity:"5",factor:"2",base_quantity:"10",label:"Measured sauce pan",...stamp};
const before={fill,moves:[],storage:"10",service:"0",allocated:"10",revision:0,voided:false};
const setup={store_id:"berts",definitions:[],profiles:[{id:id(2),source_unit:"bag"}],products:[],units:[],lots:[],fills:[before],directWasteSupported:true};
const loss={...stamp,action:"waste",fill_id:fill.id,quantity:"1.5",compartment:"storage",category:"storage_spoilage",contents_measured:true};
function preview(body=loss){
  const facts={...stamp,action:"waste",fill_id:fill.id,quantity:body.quantity,compartment:body.compartment,target_move_id:null,revision:1,storage_delta:"-3",service_delta:"0"};delete facts.calendar_date_confirmed;
  const obsBody={...stamp,quantity:body.quantity,factor:"2",source_kind:"prepared",product_version_id:id(6),profile_id:id(7),source_batch_id:fill.source_batch_id,source_unit:"bag",measurement_basis:"measured",already_included_in_batch:false,category:body.category};
  const waste={...stamp,purpose:"waste",kind:"initial",predecessor_id:null,root_id:null,revision:1,reason:stamp.note,raw_item_code:null,product_id:fill.product_id,base_unit:"lb",source_batch_id:fill.source_batch_id,container_fill_id:fill.id,body:obsBody,factor:"2",baseQuantity:"3",movements:[{side:"apply",quantity:"-3",raw_item_code:null,product_id:fill.product_id,base_unit:"lb",source_batch_id:fill.source_batch_id,reverses_movement_id:null}],cost:{status:"not_calculated",amount:null}};
  return {reviewHash:"a".repeat(64),review:{store_id:"berts",action:"waste",table:"container_moves",body,facts,sources:{before,after:{storage:"7",service:"0"}},accountingEffect:"none",consumptionEffect:"none",waste,wasteReviewHash:"b".repeat(64),wasteEffect:"measured_loss"}};
}
function ack(p,key){const r=p.review,result={...r.facts,id:id(10),command_id:id(9),store_id:"berts"},command={id:id(9),result_id:result.id,store_id:"berts",action:r.action,request_key:key,request_fingerprint:"c".repeat(64),recorded_by:"manager",review_snapshot:r,review_hash:p.reviewHash};
  const event={...r.waste,id:id(20),root_id:id(20),store_id:"berts",review_snapshot:r.waste,review_hash:r.wasteReviewHash,request_key:key,request_fingerprint:command.request_fingerprint,recorded_by:command.recorded_by};
  const link={command_id:command.id,store_id:"berts",move_id:result.id,observation_id:event.id,undo_of_command_id:null};
  const current={...before,moves:[result],storage:"7",allocated:"7",revision:1,waste_history:[{link,event}]};
  return {command,result,waste_link:link,waste_event:event,current,replayed:false};
}
let root,container,n;
beforeEach(()=>{global.IS_REACT_ACT_ENVIRONMENT=true;n=30;Object.defineProperty(global,"crypto",{configurable:true,value:{randomUUID:()=>id(n++)}});jest.clearAllMocks();api.prepContainers.mockResolvedValue(setup);api.previewPrepContainer.mockImplementation((rid,b)=>Promise.resolve(preview(b)));api.savePrepContainer.mockImplementation((rid,b,key)=>Promise.resolve(ack(preview(b.body),key)));container=document.createElement("div");document.body.appendChild(container);root=createRoot(container);});
afterEach(async()=>{await act(async()=>root.unmount());container.remove();});
const render=props=>act(async()=>root.render(<PrepContainers rid="berts" {...props}/>));
const button=t=>[...container.querySelectorAll("button")].find(b=>b.textContent===t);
const click=el=>act(async()=>el.click());
async function input(label,v){const e=container.querySelector(`[aria-label="${label}"]`);await act(async()=>{Object.getOwnPropertyDescriptor(e.tagName==="SELECT"?HTMLSelectElement.prototype:HTMLInputElement.prototype,"value").set.call(e,v);e.dispatchEvent(new Event(e.tagName==="SELECT"?"change":"input",{bubbles:true}));});}
async function review(){await input("Container action","waste");await input("Filled container",fill.id);await input("Movement quantity in original measured unit","1.5");await input("Physical timestamp with offset",stamp.performed_at);await input("Location calendar date",stamp.business_date);await input("Measurement or correction evidence",stamp.note);await click(container.querySelector('[aria-label="Confirm measured contents and calendar day"]'));await click(button("Review container command"));}

test("loss history validates its one matching contents withdrawal and journal pair",()=>{const p=preview(),a=ack(p,id(30));expect(validContainerState(a.current,"berts")).toBe(true);for(const change of [{waste_history:[]},{waste_history:[{...a.current.waste_history[0],event:{...a.waste_event,source_batch_id:id(99)}}]},{moves:[{...a.result,service_delta:"-3"}]},{moves:[{...a.result,compartment:null}]}])expect(validContainerState({...a.current,...change},"berts")).toBe(false);});
test("review binds the pinned fill conversion, exact withdrawal and both after-compartment quantities",()=>{const p=preview();expect(validContainerWasteReview(p.review,loss,"berts")).toBe(true);for(const change of [{waste:{...p.review.waste,factor:"3"}},{sources:{...p.review.sources,after:{storage:"10",service:"0"}}},{facts:{...p.review.facts,storage_delta:"-4"}},{waste:{...p.review.waste,source_batch_id:id(99)}}])expect(validContainerWasteReview({...p.review,...change},loss,"berts")).toBe(false);});
test("paired acknowledgement binds command, observation, request and original immutable state",()=>{const p=preview(),pending={key:id(30),body:{expected_review_hash:p.reviewHash},review:p},a=ack(p,pending.key);expect(validContainerAck(a,pending,"berts")).toBe(true);for(const change of [{waste_event:{...a.waste_event,request_key:id(31)}},{waste_event:{...a.waste_event,recorded_by:"other"}},{waste_link:{...a.waste_link,observation_id:id(32)}},{waste_event:{...a.waste_event,review_hash:"d".repeat(64)}}])expect(validContainerAck({...a,...change},pending,"berts")).toBe(false);});
test("tiny exact scientific notation is accepted without rounding or disappearance",()=>{const f={...fill,quantity:"1E-12",factor:"1E-12",base_quantity:"1E-24"},s={...before,fill:f,storage:"1E-24",allocated:"1E-24"};expect(validContainerState(s,"berts")).toBe(true);expect(validContainerState({...s,storage:"0"},"berts")).toBe(false);expect(validContainerState({...s,storage:"1E-99"},"berts")).toBe(false);});
test("measured waste requires reviewed pair before save and confirms accounting separation",async()=>{await render();await review();expect(container.textContent).toContain("1.5 × 2 = 3 lb");expect(button("Save reviewed container command").disabled).toBe(true);await click(container.querySelector('[aria-label="Confirm container review"]'));await click(button("Save reviewed container command"));expect(api.savePrepContainer.mock.calls[0][1].body).toEqual(loss);expect(container.textContent).toContain("contents and waste journal saved together");expect(container.textContent).toContain("Food Cost is unchanged");});
test("uncertain paired save retains exact request through remount",async()=>{const drafts=new Map();api.savePrepContainer.mockRejectedValueOnce(new Error("Lost response"));await render({drafts});await review();await click(container.querySelector('[aria-label="Confirm container review"]'));await click(button("Save reviewed container command"));const first=api.savePrepContainer.mock.calls[0];await act(async()=>root.render(null));await render({drafts});await click(button("Retry same container command"));expect(api.savePrepContainer.mock.calls[1]).toEqual(first);expect(drafts.size).toBe(0);});
test("missing journal acknowledgement holds both success and exact retained retry",async()=>{api.savePrepContainer.mockImplementationOnce((rid,b,key)=>{const a=ack(preview(b.body),key);delete a.waste_event;return Promise.resolve(a);});await render();await review();await click(container.querySelector('[aria-label="Confirm container review"]'));await click(button("Save reviewed container command"));expect(container.textContent).toContain("did not match");expect(button("Retry same container command")).toBeTruthy();expect(container.querySelector('[role="status"]')).toBeNull();});
test("altered quantity in paired preview never becomes savable",async()=>{api.previewPrepContainer.mockImplementationOnce((rid,b)=>{const p=preview(b);p.review.waste.body.quantity="9";return Promise.resolve(p);});await render();await review();expect(container.textContent).toContain("Paired waste preview did not match");expect(button("Save reviewed container command")).toBeFalsy();});
test("loss commands are unavailable until the backend confirms installed waste schema",async()=>{api.prepContainers.mockResolvedValueOnce({...setup,directWasteSupported:false});await render();expect(container.querySelector('[aria-label="Container action"]').textContent).not.toContain("Record measured container waste");});
test("stale loss requires explicit revise before a fresh measurement review",async()=>{api.savePrepContainer.mockRejectedValueOnce({response:{status:409,data:{detail:"Container changed"}}});await render();await review();await click(container.querySelector('[aria-label="Confirm container review"]'));await click(button("Save reviewed container command"));await click(button("Revise rejected container command"));expect(container.querySelector('[aria-label="Movement quantity in original measured unit"]').value).toBe("1.5");expect(button("Save reviewed container command")).toBeFalsy();});
test("paired reversal validates original loss, exact restoration and linked journal void",()=>{const a=ack(preview(),id(30)),old=a.current.waste_history[0];const move={...a.result,id:id(40),command_id:id(41),revision:2,action:"undo_waste",quantity:null,target_move_id:a.result.id,storage_delta:"3",service_delta:"0",note:"Erroneous measurement"};const p={...a.waste_event.review_snapshot,kind:"void",revision:2,root_id:a.waste_event.root_id,predecessor_id:a.waste_event.id,body:null,reason:move.note,movements:[{...old.event.review_snapshot.movements[0],side:"reverse",quantity:"3",reverses_movement_id:id(42)}]};const event={...a.waste_event,id:id(43),kind:"void",revision:2,predecessor_id:a.waste_event.id,reason:move.note,review_snapshot:p};const link={command_id:move.command_id,move_id:move.id,observation_id:event.id,store_id:"berts",undo_of_command_id:old.link.command_id};const state={...a.current,moves:[a.result,move],storage:"10",allocated:"10",revision:2,waste_history:[old,{link,event}]};expect(validContainerState(state,"berts")).toBe(true);expect(validContainerState({...state,waste_history:[old,{link:{...link,undo_of_command_id:id(44)},event}]},"berts")).toBe(false);});
test("late loss callback cannot clear a different location or revive logged-out draft",async()=>{const drafts=new Map();let resolve;api.savePrepContainer.mockImplementationOnce(()=>new Promise(r=>{resolve=r;}));await render({drafts});await review();await click(container.querySelector('[aria-label="Confirm container review"]'));await click(button("Save reviewed container command"));const first=api.savePrepContainer.mock.calls[0];drafts.clear();await render({rid:"rudds",drafts});await act(async()=>resolve(ack(preview(first[1].body),first[2])));expect(drafts.size).toBe(0);expect(container.querySelector('[role="status"]')).toBeNull();});

test("earlier loss remains selectable after transfers and transfer undo but quantity changes hold it",()=>{
  const loss=ack(preview(),id(30)).result;
  const send={id:id(51),action:"send"};
  const undo={id:id(52),action:"undo",target_move_id:send.id};
  expect(reversibleWasteMoves({moves:[loss,send,undo]})).toEqual([loss]);
  for(const action of ["unpack","waste","undo_waste","void_fill"])
    expect(reversibleWasteMoves({moves:[loss,send,undo,{id:id(53),action}]})).not.toContain(loss);
});

test("older waste target is offered only after correction schema is confirmed",async()=>{
  const a=ack(preview(),id(30));
  const sent={...a.result,id:id(51),revision:2,action:"send",quantity:"0.5",storage_delta:"-1",service_delta:"1",compartment:undefined};
  const state={...a.current,moves:[a.result,sent],storage:"6",service:"1",revision:2};
  api.prepContainers.mockResolvedValue({...setup,fills:[state],directWasteCorrectionSupported:true});
  await render();await input("Container action","undo_waste");await input("Filled container",fill.id);
  expect(container.querySelector('[aria-label="Original movement to undo"]').textContent).toContain("waste");
  api.prepContainers.mockResolvedValue({...setup,fills:[state],directWasteCorrectionSupported:false});
  await click(button("Refresh containers"));
  expect(container.querySelector('[aria-label="Original movement to undo"]').textContent).not.toContain("waste");
});

test("paired older loss reversal validates through a later transfer without rewriting it",()=>{
  const a=ack(preview(),id(30)),old=a.current.waste_history[0];
  const sent={...a.result,id:id(50),command_id:id(51),revision:2,action:"send",quantity:"0.5",storage_delta:"-1",service_delta:"1",compartment:undefined};
  const move={...a.result,id:id(40),command_id:id(41),revision:3,action:"undo_waste",quantity:null,target_move_id:a.result.id,storage_delta:"3",service_delta:"0",note:"Erroneous measurement"};
  const p={...a.waste_event.review_snapshot,kind:"void",revision:2,root_id:a.waste_event.root_id,predecessor_id:a.waste_event.id,body:null,reason:move.note,movements:[{...old.event.review_snapshot.movements[0],side:"reverse",quantity:"3",reverses_movement_id:id(42)}]};
  const event={...a.waste_event,id:id(43),kind:"void",revision:2,predecessor_id:a.waste_event.id,reason:move.note,review_snapshot:p};
  const link={command_id:move.command_id,move_id:move.id,observation_id:event.id,store_id:"berts",undo_of_command_id:old.link.command_id};
  const state={...a.current,moves:[a.result,sent,move],storage:"9",service:"1",allocated:"10",revision:3,waste_history:[old,{link,event}]};
  expect(validContainerState(state,"berts")).toBe(true);
  expect(validContainerState({...state,moves:[a.result,{...sent,action:"unpack",service_delta:"0"},move],service:"0",allocated:"9"},"berts")).toBe(false);
});
