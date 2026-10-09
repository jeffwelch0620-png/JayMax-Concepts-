import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { AdjustmentsTab } from "./AdjustmentsTab";
import { BackupControls } from "./BackupControls";
import { SalesTrackingTab } from "./SalesTrackingTab";
import { nativeStateMode, retainedAdjustments } from "../lib/stateCutover";
let container, root;
const state={legacyStateCapabilities:{inventoryRetired:true,adjustmentsAvailable:false,reportingPeriodsAvailable:false}};
beforeEach(()=>{global.IS_REACT_ACT_ENVIRONMENT=true;container=document.createElement("div");document.body.appendChild(container);root=createRoot(container);});
afterEach(async()=>{await act(async()=>root.unmount());container.remove();});
test("retained adjustments expose no legacy writers or current-price valuations",async()=>{
  const persist=jest.fn();await act(async()=>root.render(<AdjustmentsTab readOnly={retainedAdjustments(state)} adjustments={[{qty:"123456789012345.000000000001"}]} persist={persist}/>));
  expect(container.textContent).toContain("1 historical adjustment records are retained");expect(container.querySelectorAll("button,input,select")).toHaveLength(0);
  expect(container.textContent).not.toContain("123456789012345");expect(persist).not.toHaveBeenCalled();
});
test("installed schema keeps legacy close and incomplete backup disabled with client flags off",async()=>{
  const backup=jest.fn(),restore=jest.fn(),close=jest.fn();const mode=nativeStateMode(state,false);
  const period={periodStart:"2026-10-01",periodEnd:"2026-10-07",dishSales:{},itemCounts:{}};
  const items=[{controlNumber:"invented",name:"Invented food",salesTracked:true,packCount:1,unitQty:1,unitUOM:"lb",portionSize:1,portionUOM:"lb",vendorSkus:[]}];
  await act(async()=>root.render(<><BackupControls nativeMode={mode} onBackup={backup} onRestore={restore}/><SalesTrackingTab rid="berts" actualMode={mode} items={items} dishes={[]} purchases={[]} adjustments={[]} reportingPeriods={[]} salesPeriod={period} persist={jest.fn()} persistReportingPeriods={close} showToast={jest.fn()}/></>));
  expect(container.querySelector('[data-testid="save-period-button"]')).toBeNull();expect(container.textContent).toContain("Expected Usage");
  for(const button of container.querySelectorAll("button")){if(button.textContent.includes("Backup")||button.textContent.includes("Restore")){expect(button.disabled).toBe(true);await act(async()=>button.click());}}
  expect(backup).not.toHaveBeenCalled();expect(restore).not.toHaveBeenCalled();expect(close).not.toHaveBeenCalled();
});
test("precutover and prep-only capabilities keep their distinct sales and backup behavior",async()=>{
  const prepOnly={legacyStateCapabilities:{inventoryRetired:false,adjustmentsAvailable:false,reportingPeriodsAvailable:true}};
  const backup=jest.fn(),restore=jest.fn();await act(async()=>root.render(<BackupControls nativeMode={nativeStateMode(prepOnly,false)} onBackup={backup} onRestore={restore}/>));
  const buttons=container.querySelectorAll("button");await act(async()=>{buttons[0].click();buttons[1].click();});
  expect(backup).toHaveBeenCalledTimes(1);expect(restore).toHaveBeenCalledTimes(1);expect(retainedAdjustments(prepOnly)).toBe(true);
});
