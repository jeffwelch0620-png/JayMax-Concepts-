import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { CostingTab } from "./CostingTab";

const item = { controlNumber:"F01",itemCode:"fictional_food",name:"Fictional food",packCount:1,unitQty:10,unitUOM:"lb",portionSize:4,portionUOM:"oz",vendorSkus:[{price:null,preferred:true}] };
const recipe = {id:"fictional_recipe",recipeType:"menu",name:"Fictional plate",price:10,targetPct:30,yieldQty:1,yieldUOM:"each",description:"Original note",lines:[{sourceType:"item",controlNumber:"F01",itemCode:"fictional_food",qty:1,uom:"portion"}]};
let root,container,persist,success,error;
const focus = {id:recipe.id};
const find = id => container.querySelector(`[data-testid="${id}"]`);
const click = id => act(async () => find(id).click());
const type = (id,value) => act(async () => {
  const field=find(id); Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,"value").set.call(field,value);
  field.dispatchEvent(new Event("input",{bubbles:true}));
});
function panel(revision=10,dishes=[recipe],extras={}) {
  return <CostingTab rid="berts" revision={revision} items={[item]} dishes={dishes} focusDish={focus} persist={persist} showToast={success} showError={error} {...extras} />;
}
beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT=true;
  container=document.createElement("div");document.body.appendChild(container);root=createRoot(container);
  persist=jest.fn().mockResolvedValue({revision:11});success=jest.fn();error=jest.fn();
});
afterEach(async () => {await act(async () => root.unmount());container.remove();});

test("recipe changed by polling cannot be overwritten by a retained draft",async () => {
  const drafts=new Map();await act(async () => root.render(panel(10,[recipe],{drafts})));
  await type("recipe-name-input","Retained local name");
  await act(async () => root.render(panel(11,[{...recipe,price:20}],{drafts})));
  await click("save-recipe-button");
  expect(persist).not.toHaveBeenCalled();expect(success).not.toHaveBeenCalled();
  expect(drafts.get("recipe:berts").draftRevision).toBe(10);expect(find("recipe-name-input").value).toBe("Retained local name");
});

test("recipe snapshot survives navigation and guards later edits",async () => {
  const drafts=new Map();await act(async () => root.render(panel(10,[recipe],{drafts})));
  await type("recipe-name-input","Retained local name");
  await act(async () => root.render(<p>Different panel</p>));
  await act(async () => root.render(panel(11,[{...recipe,price:20}],{drafts})));
  await type("recipe-price-input","30"); await click("save-recipe-button");
  expect(persist).not.toHaveBeenCalled();expect(drafts.get("recipe:berts").draftBase.price).toBe(10);
});

test("unchanged recipe saves at the latest revision and preserves unrelated recipes",async () => {
  await act(async () => root.render(panel())); await type("recipe-name-input","Local name");
  const other={...recipe,id:"other_recipe",name:"Other saved recipe",price:35};
  await act(async () => root.render(panel(11,[recipe,other]))); await click("save-recipe-button");
  expect(persist).toHaveBeenCalledWith([expect.objectContaining({name:"Local name"}),other],11);
  expect(persist.mock.calls[0][0][0]).not.toHaveProperty("draftBase");
  expect(persist.mock.calls[0][0][0]).not.toHaveProperty("draftRevision");
});

test("explicit recipe recovery stages independent edits and preserves newest metadata",async () => {
  const latest={...recipe,price:20,serverNote:"Latest metadata"};
  const load=jest.fn().mockResolvedValue({revision:11,items:[item],dishes:[latest]});
  await act(async () => root.render(panel(10,[recipe],{loadLatest:load}))); await type("recipe-name-input","Local name");
  await act(async () => root.render(panel(11,[latest],{loadLatest:load}))); await click("review-recipe-draft");
  expect(persist).not.toHaveBeenCalled();expect(find("recipe-price-input").value).toBe("20");
  await click("save-recipe-button");
  expect(persist).toHaveBeenCalledWith([expect.objectContaining({name:"Local name",price:20,serverNote:"Latest metadata"})],11);
});

test("overlapping recipe fields retain the draft and require explicit resolution",async () => {
  await act(async () => root.render(panel())); await type("recipe-price-input","30");
  await act(async () => root.render(panel(11,[{...recipe,price:20}]))); await click("review-recipe-draft");
  expect(error).toHaveBeenLastCalledWith(expect.stringContaining("Conflicting recipe changes: price"));
  expect(find("recipe-price-input").value).toBe("30");await click("save-recipe-button");expect(persist).not.toHaveBeenCalled();
  await type("recipe-price-input","20");await click("review-recipe-draft");await click("save-recipe-button");
  expect(persist).toHaveBeenCalledWith([expect.objectContaining({price:20})],11);
});

test("ingredients and batch yield form a coupled conflict group",async () => {
  const prep={...recipe,recipeType:"prep",yieldQty:8,yieldUOM:"lb"};
  await act(async () => root.render(panel(10,[prep])));await type("recipe-yield-input","10");
  const latest={...prep,lines:[{...prep.lines[0],qty:2}]};
  await act(async () => root.render(panel(11,[latest])));await click("review-recipe-draft");
  expect(error).toHaveBeenLastCalledWith(expect.stringContaining("recipe type, ingredients and yield"));
  expect(find("recipe-yield-input").value).toBe("10");expect(persist).not.toHaveBeenCalled();
});

test("recipe recovery revalidates the latest ingredient catalog",async () => {
  const load=jest.fn().mockResolvedValue({revision:11,items:[],dishes:[recipe]});
  await act(async () => root.render(panel(10,[recipe],{loadLatest:load}))); await type("recipe-name-input","Local name");
  await click("review-recipe-draft");
  expect(error).toHaveBeenCalled();expect(find("recipe-name-input").value).toBe("Local name");expect(persist).not.toHaveBeenCalled();
});

test.each([true,false])("409 retry after polling distinguishes same-recipe from unrelated changes (%s)",async same => {
  await act(async () => root.render(panel()));await type("recipe-name-input","Local name");
  persist.mockRejectedValueOnce({response:{status:409,data:{detail:"Changed elsewhere"}}});await click("save-recipe-button");
  const latest=same?[{...recipe,price:20}]:[recipe,{...recipe,id:"other_recipe",price:20}];
  await act(async () => root.render(panel(11,latest)));await click("save-recipe-button");
  expect(persist).toHaveBeenCalledTimes(same?1:2);expect(success).toHaveBeenCalledTimes(same?0:1);
  if(!same)expect(persist.mock.calls[1][1]).toBe(11);
});

test("deleted recipes cannot be silently recreated",async () => {
  await act(async () => root.render(panel()));await type("recipe-name-input","Retained name");
  await act(async () => root.render(panel(11,[])));await click("review-recipe-draft");await click("save-recipe-button");
  expect(persist).not.toHaveBeenCalled();expect(find("recipe-name-input").value).toBe("Retained name");
});

test("new recipe drafts append to refreshed recipes using the latest revision",async () => {
  await act(async () => root.render(panel(10,[recipe],{focusDish:null})));
  await type("recipe-name-input","New fictional plate"); await type("recipe-price-input","12");
  await click("ingredient-add");
  const other={...recipe,id:"other_recipe",name:"Latest other recipe"};
  await act(async () => root.render(panel(11,[recipe,other],{focusDish:null})));await click("save-recipe-button");
  expect(persist).toHaveBeenCalledWith([recipe,other,expect.objectContaining({name:"New fictional plate"})],11);
});

test("a failed fresh read leaves the recipe draft and base intact",async () => {
  const drafts=new Map(),load=jest.fn().mockResolvedValue(undefined);
  await act(async () => root.render(panel(10,[recipe],{drafts,loadLatest:load})));await type("recipe-name-input","Local name");
  await click("review-recipe-draft");
  expect(error).toHaveBeenLastCalledWith(expect.stringContaining("could not be confirmed"));
  expect(drafts.get("recipe:berts").draftRevision).toBe(10);expect(find("recipe-name-input").value).toBe("Local name");
  expect(persist).not.toHaveBeenCalled();
});

test("typing during a recipe save survives its acknowledgement and needs review against the new base",async () => {
  let complete;
  persist.mockImplementationOnce(()=>new Promise(resolve=>{complete=resolve;}));
  await act(async () => root.render(panel()));await type("recipe-name-input","Submitted name");
  act(()=>find("save-recipe-button").click());await type("recipe-name-input","Later typing");
  const saved=persist.mock.calls[0][0][0];
  await act(async()=>complete({revision:11,dishes:[saved]}));
  await act(async()=>root.render(panel(11,[saved])));
  expect(find("recipe-name-input").value).toBe("Later typing");
  await click("save-recipe-button");expect(persist).toHaveBeenCalledTimes(1);
});

test("a recovery read cannot replace newer typing or modify a remounted retained editor",async () => {
  let complete;const load=jest.fn().mockImplementation(()=>new Promise(resolve=>{complete=resolve;}));
  const drafts=new Map();await act(async () => root.render(panel(10,[recipe],{loadLatest:load,drafts})));
  act(()=>find("review-recipe-draft").click());await type("recipe-name-input","Newer typing");
  await act(async()=>complete({revision:11,items:[item],dishes:[{...recipe,price:20}]}));
  expect(find("recipe-name-input").value).toBe("Newer typing");expect(find("recipe-price-input").value).toBe("10");
  act(()=>find("review-recipe-draft").click());await act(async()=>root.render(<p>Other panel</p>));
  await act(async()=>root.render(panel(11,[{...recipe,price:20}],{loadLatest:load,drafts})));
  await act(async()=>complete({revision:11,items:[item],dishes:[{...recipe,price:20}]}));
  expect(find("recipe-name-input").value).toBe("Newer typing");expect(find("recipe-price-input").value).toBe("10");
});
