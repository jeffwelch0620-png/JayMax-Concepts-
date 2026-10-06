import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { StaffCountDrafts, StaffQuantityForm } from "./StaffCountDrafts";
import { StaffCountReview, StaffSubmissionReview } from "./StaffCountReview";
import * as api from "../lib/api";

jest.mock("../lib/api", () => ({ __esModule:true,staffCountDrafts:jest.fn(),staffCountSheets:jest.fn(),issueStaffCountSheet:jest.fn(),decideStaffCountSheet:jest.fn(),submitStaffCountDraft:jest.fn() }));
const item={item_code:"food",name_snapshot:"Invented food",location_notes:"Walk-in and freezer",counted_unit:"case",base_unit:"lb",base_units_per_counted_unit:"20.000000000001"};
const review={sheet:{id:"sheet-1",store_id:"berts",scope_id:"scope-1",count_date:"2026-10-05",timing:"before_receipts",note:"Measure all raw locations",issued_by:"Manager",sheet_snapshot:{scope_revision:1,items:[item]}},reviewHash:"a".repeat(64),latest:{id:"submission-1",revision:1,counter_name:"Counter",credential_kind:"shared_pin",note:"Measured all storage",quantities:[{item_code:"food",counted_quantity:"3.0000000001",note:"All locations"}]},history:[],errors:[],decision:null};
review.history=[review.latest];
let root,container;
beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT=true; Object.defineProperty(global,"crypto",{configurable:true,value:{randomUUID:()=>"stable-count-key"}});
  root=createRoot(container=document.createElement("div"));document.body.appendChild(container);jest.clearAllMocks();
  api.staffCountDrafts.mockResolvedValue([review]);api.staffCountSheets.mockResolvedValue([review]);
});
afterEach(async()=>{await act(async()=>root.unmount());container.remove();});
const render=el=>act(async()=>root.render(el));
const click=el=>act(async()=>el.click());
const button=text=>[...container.querySelectorAll("button")].find(b=>b.textContent===text);
async function input(label,value){const el=container.querySelector(`[aria-label="${label}"]`);await act(async()=>{Object.getOwnPropertyDescriptor(el.tagName==="SELECT"?HTMLSelectElement.prototype:HTMLInputElement.prototype,"value").set.call(el,value);el.dispatchEvent(new Event(el.tagName==="SELECT"?"change":"input",{bubbles:true}));});}
const staffAck=body=>({submission:{id:"saved-submission",sheet_id:"sheet-1"},review:{history:[{id:"saved-submission"}]}});
const managerAck=body=>({review:{sheet:review.sheet,decision:{id:"decision",decision:body.decision,snapshot_id:body.decision==="accepted"?"count-1":null,review_snapshot:{reviewHash:review.reviewHash}}},count:body.decision==="accepted"?{header:{id:"count-1",status:"complete"}}:null});
async function staffInputs(quantity="0") {await input("Draft counter name","Invented Counter");await input("Draft measurement note","Measured all locations");await input("Draft quantity food",quantity);}
async function managerInputs(){await input("Review value food","45.00");await input("Review evidence food","Confirmed measured quantity and explicit value");await click(container.querySelector('[aria-label="Review confirm food"]'));await input("Manager count decision note","Reviewed complete count");await click(container.querySelector('[aria-label="Manager quantities reviewed"]'));}

test("staff sheet fixes date, locations and exact units and exposes quantities without value editing",async()=>{
  await render(<StaffQuantityForm review={review} onSubmit={jest.fn()} />);
  expect(container.textContent).toContain("20.000000000001 lb");expect(container.textContent).toContain("Walk-in and freezer");
  expect(container.querySelector('input[type="date"]')).toBeNull();expect(container.querySelector('[aria-label="Review value food"]')).toBeNull();
  expect(container.textContent).toContain("does not change accounting inventory");
});
test.each([["",null],["0","0"]])("staff preserves blank versus measured zero (%s)",async(q,expected)=>{
  const submit=jest.fn().mockImplementation(body=>Promise.resolve(staffAck(body)));
  await render(<StaffQuantityForm review={{...review,latest:null,history:[]}} onSubmit={submit} pin="4826" />);await staffInputs(q);await click(button("Submit quantities for review"));
  expect(submit.mock.calls[0][0].lines[0].counted_quantity).toBe(expected);expect(submit.mock.calls[0][0].lines[0]).not.toHaveProperty("inventory_value");expect(container.textContent).toContain("Quantities submitted and confirmed");
});
test("interrupted staff save freezes fields and retries identical payload and request key",async()=>{
  const submit=jest.fn().mockRejectedValueOnce(new Error("Interrupted")).mockImplementation(body=>Promise.resolve(staffAck(body)));
  await render(<StaffQuantityForm review={review} onSubmit={submit} />);await staffInputs("2");await click(button("Submit quantities for review"));
  expect(container.querySelector("fieldset").disabled).toBe(true);await click(button("Retry same quantity submission"));expect(submit.mock.calls[1]).toEqual(submit.mock.calls[0]);
});
test("wrong-sheet acknowledgment cannot claim submitted quantities",async()=>{
  const submit=jest.fn().mockResolvedValue({submission:{id:"wrong",sheet_id:"other"},review:{history:[{id:"wrong"}]}});
  await render(<StaffQuantityForm review={review} onSubmit={submit} />);await staffInputs();await click(button("Submit quantities for review"));
  expect(container.textContent).toContain("was not confirmed");expect(container.querySelector('[role="status"]')).toBeNull();
});
test("staff failed reads show an error and cannot announce no open count sheets",async()=>{
  api.staffCountDrafts.mockRejectedValue(new Error("Database unavailable"));await render(<StaffCountDrafts restaurantId="berts" pin="4826" />);
  expect(container.textContent).toContain("Database unavailable");expect(container.textContent).not.toContain("No open count sheets");
});
test("wrong-location count response is held",async()=>{
  api.staffCountDrafts.mockResolvedValue([{...review,sheet:{...review.sheet,store_id:"rudds"}}]);await render(<StaffCountDrafts restaurantId="berts" />);
  expect(container.textContent).toContain("were not confirmed");expect(container.querySelector('[aria-label="Draft quantity food"]')).toBeNull();
});
test("late staff location response cannot replace the selected location",async()=>{
  let resolve;api.staffCountDrafts.mockReturnValueOnce(new Promise(r=>{resolve=r;})).mockResolvedValueOnce([]);
  await render(<StaffCountDrafts restaurantId="berts" />);await render(<StaffCountDrafts restaurantId="rudds" />);await act(async()=>resolve([review]));
  expect(container.textContent).toContain("No open count sheets");expect(container.textContent).not.toContain("Invented food");
});
test("manager acceptance requires explicit values and quantity review and leaves staff quantity fixed",async()=>{
  const decide=jest.fn().mockImplementation(body=>Promise.resolve(managerAck(body)));await render(<StaffSubmissionReview review={review} onDecide={decide} />);
  expect(button("Accept reviewed quantities and values").disabled).toBe(true);expect(container.textContent).toContain("3.0000000001 case");expect(container.querySelector('[aria-label="Draft quantity food"]')).toBeNull();
  await managerInputs();await click(button("Accept reviewed quantities and values"));
  expect(decide.mock.calls[0][0]).toMatchObject({decision:"accepted",expected_review_hash:review.reviewHash,quantities_reviewed:true,values:[{item_code:"food",inventory_value:"45.00",confirmed:true}]});expect(container.textContent).toContain("Manager decision confirmed: accepted");
});
test("partial or stale quantities hold acceptance while manager rejection stays available",async()=>{
  const decide=jest.fn().mockImplementation(body=>Promise.resolve(managerAck(body)));
  await render(<StaffSubmissionReview review={{...review,errors:["Units changed"],latest:{...review.latest,quantities:[{item_code:"food",counted_quantity:null}]}}} onDecide={decide} />);
  await managerInputs();expect(button("Accept reviewed quantities and values").disabled).toBe(true);await click(button("Reject sheet without accounting changes"));
  expect(decide.mock.calls[0][0].values).toEqual([]);expect(container.textContent).toContain("No accounting count created");
});
test("unconfirmed manager response holds success and retries the same decision",async()=>{
  const decide=jest.fn().mockResolvedValue({review:{sheet:review.sheet,decision:{id:"decision",decision:"accepted",snapshot_id:"different",review_snapshot:{reviewHash:review.reviewHash}}},count:{header:{id:"count-1",status:"complete"}}});
  await render(<StaffSubmissionReview review={review} onDecide={decide} />);await managerInputs();await click(button("Accept reviewed quantities and values"));
  expect(container.textContent).toContain("was not confirmed");expect(container.querySelector('[role="status"]')).toBeNull();await click(button("Retry same manager decision"));expect(decide.mock.calls[1]).toEqual(decide.mock.calls[0]);
});
test("manager issuance uses current scope and stable retries after interrupted response",async()=>{
  api.staffCountSheets.mockResolvedValue([]);api.issueStaffCountSheet.mockRejectedValueOnce(new Error("Interrupted")).mockImplementation((rid,body)=>Promise.resolve({sheet:{id:"issued",...body}}));
  await render(<StaffCountReview restaurantId="berts" scope={{header:{id:"scope-1",revision:1}}} />);
  await input("Staff sheet physical date","2026-10-05");await input("Staff sheet receipt timing","before_receipts");await input("Staff sheet instructions","All raw storage");await click(button("Issue staff count sheet"));
  await click(button("Retry same sheet issue"));expect(api.issueStaffCountSheet.mock.calls[1]).toEqual(api.issueStaffCountSheet.mock.calls[0]);
  expect(api.issueStaffCountSheet.mock.calls[0][1]).toMatchObject({scope_id:"scope-1",count_date:"2026-10-05",timing:"before_receipts"});expect(container.textContent).toContain("Count sheet issued and confirmed");
});
