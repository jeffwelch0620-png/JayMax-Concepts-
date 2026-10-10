import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { HistoricalPrepLists } from "./HistoricalPrepLists";
import { PrepTab } from "./PrepTab";
import * as api from "../lib/api";
jest.mock("../lib/api", () => ({ isPostgres:true, prepDayTasksEnabled:true, prepListArchive:jest.fn(), listPrepItems:jest.fn(), generatePrepList:jest.fn(), updatePrepList:jest.fn() }));
jest.mock("./PrepDayDrafts", () => ({ PrepDayDrafts:() => <p>Current dated prep plan</p> }));
let container,root;
const id = "11111111-1111-4111-8111-111111111111", second="22222222-2222-4222-8222-222222222222";
const metadata={basis:"legacy_prep_archive",archived:true,operational:false};
const row=(identity=id,date="2026-10-01",store="berts")=>({ ...metadata,id:identity,storeId:store,date,countType:null,classification:"unclassified",track:null,
  header:{id:identity,store_id:store,prep_date:date,count_type:null,status:"draft"},
  lines:[{id:"33333333-3333-4333-8333-333333333333",list_id:identity,name:"Invented historical line",yield_qty:"123456789012345.000000000001",par:null,on_hand:null,needed_units:"0",batches_planned:null,batches_done:"0",make_qty:"1E-12",note:"Invented <note>\nsecond line"}]});
const page=(records=[row()],nextCursor=null,store="berts",classification="all")=>({ ...metadata,storeId:store,dateFrom:null,dateThrough:null,classification,records,nextCursor });
beforeEach(()=>{global.IS_REACT_ACT_ENVIRONMENT=true;container=document.createElement("div");document.body.appendChild(container);root=createRoot(container);jest.resetAllMocks();api.isPostgres=true;api.prepDayTasksEnabled=true;api.listPrepItems.mockResolvedValue([]);});
afterEach(async()=>{await act(async()=>root.unmount());container.remove();});
const render=element=>act(async()=>root.render(element));
const button=text=>[...container.querySelectorAll("button")].find(b=>b.textContent===text);
const click=element=>act(async()=>element.click());
async function input(label,value){const element=container.querySelector(`[aria-label="${label}"]`);const prototype=element.tagName==="SELECT"?HTMLSelectElement.prototype:HTMLInputElement.prototype;await act(async()=>{Object.getOwnPropertyDescriptor(prototype,"value").set.call(element,value);element.dispatchEvent(new Event(element.tagName==="SELECT"?"change":"input",{bubbles:true}));});}
test("unclassified raw records retain nulls and precision without becoming operational prep",async()=>{
  api.prepListArchive.mockResolvedValue(page());await render(<HistoricalPrepLists rid="berts"/>);
  expect(container.querySelector("summary").textContent).toBe("2026-10-01 — Unclassified — draft");
  expect(container.textContent).toContain("123456789012345.000000000001");expect(container.textContent).toContain("Not recorded");expect(container.textContent).toContain("1E-12");
  expect(container.textContent).toContain("Invented <note>");expect(container.querySelector("note")).toBeNull();
  expect([...container.querySelectorAll("button")].map(b=>b.textContent)).toEqual(["Apply / Refresh history"]);
  expect(api.generatePrepList).not.toHaveBeenCalled();expect(api.updatePrepList).not.toHaveBeenCalled();
});
test("failed and wrong-location reads cannot appear as a confirmed empty archive",async()=>{
  api.prepListArchive.mockRejectedValueOnce(new Error("Offline")).mockResolvedValueOnce(page([row(id,"2026-10-01","rudds")],null,"rudds"));
  await render(<HistoricalPrepLists rid="berts"/>);expect(container.querySelector('[role="alert"]').textContent).toContain("Offline");expect(container.textContent).not.toContain("No historical lists");
  await click(button("Apply / Refresh history"));expect(container.textContent).toContain("was not confirmed");expect(container.querySelector("summary")).toBeNull();
});
test("pagination rejects repeated records, retains the first page and supports exact retry",async()=>{
  const cursor={after_date:"2026-10-01",after_id:id};
  api.prepListArchive.mockResolvedValueOnce(page([row()],cursor)).mockResolvedValueOnce(page([row()],cursor)).mockResolvedValueOnce(page([row(second,"2026-10-02")]));
  await render(<HistoricalPrepLists rid="berts"/>);await click(button("Load more history"));
  expect(container.querySelector('[role="alert"]').textContent).toContain("additional history is not confirmed");expect(container.querySelectorAll("summary")).toHaveLength(1);
  await click(button("Load more history"));expect(container.querySelectorAll("summary")).toHaveLength(2);expect(button("Load more history")).toBeUndefined();
  expect(api.prepListArchive.mock.calls[1]).toEqual(["berts",{classification:"all",limit:50,...cursor}]);expect(api.prepListArchive.mock.calls[2]).toEqual(api.prepListArchive.mock.calls[1]);
});
test("filter changes clear prior results and explicitly request unclassified history",async()=>{
  api.prepListArchive.mockResolvedValueOnce(page()).mockResolvedValueOnce(page([row()],null,"berts","unclassified"));
  await render(<HistoricalPrepLists rid="berts"/>);await input("History recorded type","unclassified");expect(container.querySelector("summary")).toBeNull();
  await click(button("Apply / Refresh history"));expect(api.prepListArchive.mock.calls[1][1].classification).toBe("unclassified");expect(container.querySelector("summary")).not.toBeNull();
});
test("late location responses cannot replace the newly selected archive",async()=>{
  let resolve;api.prepListArchive.mockReturnValueOnce(new Promise(done=>{resolve=done;})).mockResolvedValueOnce(page([row(second,"2026-10-02","rudds")],null,"rudds"));
  await render(<HistoricalPrepLists rid="berts"/>);await render(<HistoricalPrepLists rid="rudds"/>);await act(async()=>resolve(page()));
  expect(container.textContent).toContain(second);expect(container.textContent).not.toContain(id);
});
test("floating-point quantities and operational or mislabeled snapshots are held",async()=>{
  const floating=row();floating.lines[0].yield_qty=123456789012345;
  api.prepListArchive.mockResolvedValueOnce(page([floating])).mockResolvedValueOnce(page([{...row(),track:"daily",classification:"daily"}])).mockResolvedValueOnce({...page(),operational:true});
  await render(<HistoricalPrepLists rid="berts"/>);
  for(let i=0;i<3;i++){if(i)await click(button("Apply / Refresh history"));expect(container.textContent).toContain("was not confirmed");expect(container.querySelector("summary")).toBeNull();}
});
test("confirmed empty history differs from validation failures",async()=>{
  api.prepListArchive.mockResolvedValueOnce(page([]));await render(<HistoricalPrepLists rid="berts"/>);expect(container.textContent).toContain("No historical lists match");
  await input("History from date","2026-10-02");await input("History through date","2026-10-01");await click(button("Apply / Refresh history"));
  expect(container.textContent).toContain("Start date must not follow end date");expect(api.prepListArchive).toHaveBeenCalledTimes(1);expect(container.textContent).not.toContain("No historical lists match");
});
test("manager History remains reachable alongside native dated prep work",async()=>{
  api.prepListArchive.mockResolvedValue(page());await render(<PrepTab rid="berts" items={[]} dishes={[]} prepCapabilities={{listsAvailable:false}}/>);
  expect(container.textContent).toContain("Current dated prep plan");await click(container.querySelector('[data-testid="prep-subtab-history"]'));expect(container.querySelector('[data-testid="historical-prep-lists"]')).not.toBeNull();
  expect(api.prepListArchive).toHaveBeenCalledTimes(1);expect(api.generatePrepList).not.toHaveBeenCalled();
});
