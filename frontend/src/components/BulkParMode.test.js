import React,{act} from "react";
import {createRoot} from "react-dom/client";
import {BulkParMode} from "./BulkParMode";
import * as api from "../lib/api";
jest.mock("../lib/api",()=>({bulkParMode:jest.fn(),saveBulkParMode:jest.fn()}));
const entry=(revision,mode,note="Invented switch")=>({id:`mode-${revision}`,store_id:"berts",revision,mode,note,actor:"owner",recorded_at:"2026-11-05T10:00:00-05:00"});
const state=(mode="window",missing=[],history=[])=>({store_id:"berts",mode,revision:history.length,history,missing_daily_pars:missing});
const ack=(mode="daily",history=[entry(1,"daily")],replayed=false)=>({request_key:"key",mode,revision:history.length,history,replayed});
let root,container,drafts,toast,onMode;
const button=text=>[...container.querySelectorAll("button")].find(b=>b.textContent===text);
const input=label=>container.querySelector(`[aria-label="${label}"]`);
const click=async el=>act(async()=>el.click());
async function note(value){const el=input("Bulk par mode reason");await act(async()=>{Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,"value").set.call(el,value);el.dispatchEvent(new Event("input",{bubbles:true}));});}
const render=async(key="berts")=>act(async()=>root.render(<BulkParMode key={key} rid="berts" drafts={drafts} showToast={toast} onMode={onMode}/>));
beforeEach(async()=>{
  jest.clearAllMocks();global.IS_REACT_ACT_ENVIRONMENT=true;Object.defineProperty(window,"crypto",{value:{randomUUID:()=>"key"},configurable:true});
  api.bulkParMode.mockResolvedValue(state());drafts=new Map();toast=jest.fn();onMode=jest.fn();container=document.createElement("div");document.body.appendChild(container);root=createRoot(container);
});
afterEach(async()=>{await act(async()=>root.unmount());container.remove();});
test("switching to daily pars sends the reason, the read version and one request key",async()=>{
  await render();expect(onMode).toHaveBeenCalledWith("window");expect(container.textContent).toContain("the Monday run uses the weekday par");
  await click(button("Switch to daily pars"));expect(api.saveBulkParMode).not.toHaveBeenCalled();expect(container.textContent).toContain("Record the reason");
  await note("Invented switch");api.saveBulkParMode.mockResolvedValue(ack());api.bulkParMode.mockResolvedValue(state("daily",[],[entry(1,"daily")]));await click(button("Switch to daily pars"));
  expect(api.saveBulkParMode).toHaveBeenCalledWith("berts",{mode:"daily",note:"Invented switch"},0,"key");expect(toast).toHaveBeenCalledWith("Bulk par mode switched.");
  expect(onMode).toHaveBeenLastCalledWith("daily");expect(button("Switch back to weekday / weekend pars")).toBeDefined();expect(container.textContent).toContain("Switch history (1)");
});
test("daily pars cannot be chosen while items are missing them",async()=>{
  api.bulkParMode.mockResolvedValue(state("window",["Invented ranch","Invented slaw"]));await render();
  expect(container.textContent).toContain("enter daily pars for: Invented ranch, Invented slaw");expect(button("Switch to daily pars").disabled).toBe(true);
});
test("a lost response keeps the exact request for retry through a remount",async()=>{
  await render();await note("Invented switch");api.saveBulkParMode.mockRejectedValueOnce(new Error("Lost response"));await click(button("Switch to daily pars"));
  expect(toast).not.toHaveBeenCalled();expect(input("Bulk par mode reason").disabled).toBe(true);
  await render("remount");api.saveBulkParMode.mockResolvedValue(ack());await click(button("Retry the same Bulk par switch"));
  expect(api.saveBulkParMode.mock.calls[1]).toEqual(api.saveBulkParMode.mock.calls[0]);expect(toast).toHaveBeenCalledTimes(1);
});
test("a refusal clears the pending switch and a mismatched acknowledgement is not success",async()=>{
  await render();await note("Invented switch");api.saveBulkParMode.mockRejectedValueOnce({response:{status:403,data:{detail:"Only an owner or admin can change pars"}}});await click(button("Switch to daily pars"));
  expect(container.textContent).toContain("Only an owner or admin can change pars");expect(button("Switch to daily pars")).toBeDefined();
  api.saveBulkParMode.mockResolvedValue(ack("window"));await click(button("Switch to daily pars"));expect(toast).not.toHaveBeenCalled();expect(button("Retry the same Bulk par switch")).toBeDefined();
});
test("a read for another store is not shown",async()=>{
  api.bulkParMode.mockResolvedValue({...state(),store_id:"rudds"});await render();expect(container.textContent).toContain("Bulk par mode read was not confirmed.");expect(onMode).not.toHaveBeenCalled();
});
test("a replay is confirmed by its own history entry even after the store was switched back",async()=>{
  await render();await note("Invented switch");api.saveBulkParMode.mockRejectedValueOnce(new Error("Lost response"));await click(button("Switch to daily pars"));
  api.saveBulkParMode.mockResolvedValue(ack("window",[entry(1,"daily"),entry(2,"window","Another owner switched back")],true));api.bulkParMode.mockResolvedValue(state("window",[],[entry(1,"daily"),entry(2,"window","Another owner switched back")]));
  await click(button("Retry the same Bulk par switch"));
  expect(toast).toHaveBeenCalledWith("Your switch was saved, but the store has been switched again since; the current mode is shown.");
  expect(button("Switch to daily pars")).toBeDefined();expect(input("Bulk par mode reason").disabled).toBe(false);
});
test("a replay whose history entry is another switch is not confirmed",async()=>{
  await render();await note("Invented switch");api.saveBulkParMode.mockResolvedValue(ack("daily",[entry(1,"daily","Someone else's switch")],true));await click(button("Switch to daily pars"));
  expect(toast).not.toHaveBeenCalled();expect(button("Retry the same Bulk par switch")).toBeDefined();
});test("a stale-version refusal reloads the current setting so the next try uses its version",async()=>{
  await render();await note("Invented switch");api.bulkParMode.mockResolvedValue(state("daily",[],[entry(1,"daily","Another owner")]));
  api.saveBulkParMode.mockRejectedValueOnce({response:{status:409,data:{detail:"Bulk par mode changed. Refresh before switching."}}});await click(button("Switch to daily pars"));
  expect(container.textContent).toContain("Refresh before switching");expect(button("Switch back to weekday / weekend pars")).toBeDefined();
  await note("Back again");api.saveBulkParMode.mockResolvedValue(ack("window",[entry(1,"daily","Another owner"),entry(2,"window","Back again")]));await click(button("Switch back to weekday / weekend pars"));
  expect(api.saveBulkParMode.mock.calls[1].slice(1,3)).toEqual([{mode:"window",note:"Back again"},1]);expect(toast).toHaveBeenCalledWith("Bulk par mode switched.");
});
test("structured validation errors are shown as text, and refresh rereads the mode",async()=>{
  await render();await note("Invented switch");
  api.saveBulkParMode.mockRejectedValueOnce({response:{status:422,data:{detail:[{loc:["body","note"],msg:"String should have at most 2000 characters"}]}}});await click(button("Switch to daily pars"));
  expect(container.textContent).toContain("note: String should have at most 2000 characters");
  await note("x".repeat(2001));await click(button("Switch to daily pars"));expect(api.saveBulkParMode).toHaveBeenCalledTimes(1);expect(container.textContent).toContain("2,000 characters or fewer");
  api.bulkParMode.mockResolvedValue(state("daily",[],[entry(1,"daily")]));await click(button("Refresh Bulk par mode"));expect(onMode).toHaveBeenLastCalledWith("daily");
});
