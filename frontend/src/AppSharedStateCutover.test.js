import React, { act } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
jest.mock("./lib/api",()=>({...jest.requireActual("./lib/api"),nativePurchasesEnabled:false,actualInventoryEnabled:false,currentSession:()=>({user:{role:"manager",email:"manager@example.invalid",locations:["berts"]}})}));
jest.mock("./lib/useStoreState",()=>({useStoreState:()=>({state:{revision:0,items:[{controlNumber:"invented",name:"Invented stale balance",currentStock:0,par:10}],purchases:[],dishes:[],adjustments:[],reportingPeriods:[],areas:[],salesPeriod:{dishSales:{},itemCounts:{}},prepStock:null,prepLogs:null,legacyStateCapabilities:{inventoryRetired:true,adjustmentsAvailable:false,reportingPeriodsAvailable:false}},isCurrent:()=>true,refresh:jest.fn(),save:jest.fn(),apply:jest.fn()})}));
test("main app holds legacy accounting views and restore when server inventory is retired",async()=>{
  global.IS_REACT_ACT_ENVIRONMENT=true;const container=document.createElement("div");document.body.appendChild(container);const root=createRoot(container);
  try{
    await act(async()=>root.render(<App/>));expect(container.textContent).toContain("Accounting reports are awaiting Actual Inventory setup");
    expect(container.querySelector('[data-testid="alerts-badge"]')).toBeNull();expect(container.querySelector('input[type="file"]')).toBeNull();
    const nav=container.querySelector('[data-testid="main-nav"]');
    for(const [name,hold] of [["Enter Counts","Legacy count entry is unavailable"],["Price History","Received purchase history is awaiting setup"],["Waste / Adjustments","historical adjustment records are retained"]]){
      const button=[...nav.querySelectorAll("button")].find(b=>b.textContent.trim()===name);expect(button).toBeDefined();await act(async()=>button.click());expect(container.textContent).toContain(hold);
    }
  }finally{await act(async()=>root.unmount());container.remove();}
});
