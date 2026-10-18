import { expectedSalesUsage } from './expectedSalesUsage';

const food={itemCode:'global_food',controlNumber:'LOCAL',name:'Fictional food',salesTracked:true};
const other={itemCode:'global_other',controlNumber:'OTHER',name:'Other fictional food',salesTracked:true};
const line={sourceType:'item',itemCode:food.itemCode,qty:2,uom:'portion'};
const menu={id:'menu',name:'Fictional dish',recipeType:'menu',lines:[line]};
const prep={id:'prep',name:'Fictional prep',recipeType:'prep',yieldQty:4,yieldUOM:'lb',lines:[{...line,qty:8}]};
const nested={...menu,lines:[{sourceType:'prep',recipeId:prep.id,qty:2,uom:'lb'}]};
const result=(recipes=[menu],sales={menu:3},items=[food])=>expectedSalesUsage(items,recipes,sales);
const portions=r=>r.rows.map(row=>row.portions);

test('canonical identity overrides a stale alias without needing price or physical pack metadata',()=>{
  expect(portions(result([{...menu,lines:[{...line,controlNumber:'OLD-ALIAS'}]}]))).toEqual([6]);
  expect(result().complete).toBe(true);
  expect(food).not.toHaveProperty('vendorSkus');
});
test('legacy alias-only lines work only when uniquely linked to this restaurant',()=>{
  expect(portions(result([{...menu,lines:[{sourceType:'item',controlNumber:'LOCAL',qty:2}]}]))).toEqual([6]);
  expect(result([{...menu,lines:[{...line,itemCode:'foreign',controlNumber:'LOCAL'}]}]).complete).toBe(false);
});
test('nested prep expands positive verified recipe quantities per yield unit',()=>{
  expect(portions(result([nested,prep],{menu:3}))).toEqual([12]);
});
test.each([null,undefined,'','  ',-1,true,[2],{},'NaN','1e400','1e-400'])('unknown/invalid sales %p never becomes zero',quantity=>{
  const r=result([menu],{menu:quantity},[food,other]);
  expect(portions(r)).toEqual([null,0]);expect(r.complete).toBe(false);
  expect(r.rows[0].issues.join()).toContain('confirmed nonnegative sales quantity');
});
test('an omitted quantity is distinct from an explicit zero, including decimal zero',()=>{
  expect(portions(result([menu],{}))).toEqual([null]);
  for(const zero of [0,'0','0E-10']) expect(portions(result([menu],{menu:zero}))).toEqual([0]);
});
test('explicit zero does not require expanding an unused malformed definition',()=>{
  expect(result([{...menu,lines:[]}],{menu:0}).complete).toBe(true);
});
test.each([
  ['missing inventory', [{...menu,lines:[{...line,itemCode:'absent'}]}]],
  ['missing prep',[{...nested,lines:[{sourceType:'prep',recipeId:'missing',qty:2}]}]],
  ['zero yield',[nested,{...prep,yieldQty:0}]],
  ['missing yield',[nested,{...prep,yieldQty:null}]],
  ['unsupported yield',[nested,{...prep,yieldUOM:'scoop'}]],
  ['inherited unit key',[nested,{...prep,yieldUOM:'toString'}]],
  ['wrong yield unit',[{...nested,lines:[{...nested.lines[0],uom:'oz'}]},prep]],
  ['physical ingredient unit',[{...menu,lines:[{...line,uom:'lb'}]}]],
  ['mixed source',[{...menu,lines:[{...line,recipeId:'prep'}]},prep]],
  ['bad source',[{...menu,lines:[{...line,sourceType:'unknown'}]}]],
  ['empty recipe',[{...menu,lines:[]}]],
  ['null line',[{...menu,lines:[null]}]],
  ['invalid menu yield',[{...menu,yieldQty:2}]],
])('%s makes usage unavailable rather than a partial or zero total',(_,recipes)=>{
  const r=result(recipes,{menu:3},[food,other]);
  expect(portions(r)).toEqual([null,null]);expect(r.issues.length).toBeGreaterThan(0);
});
test.each([0,-1,'',true,[2],{},'1e400','1e-400'])('invalid ingredient quantity %p stays unavailable',qty=>{
  expect(portions(result([{...menu,lines:[{...line,qty}]}]))).toEqual([null]);
});
test('missing graph coverage is conservative even alongside valid sold dishes',()=>{
  const bad={id:'bad',name:'Broken dish',lines:[{sourceType:'prep',recipeId:'missing',qty:1}]};
  expect(portions(result([menu,bad],{menu:2,bad:1},[food,other]))).toEqual([null,null]);
});
test('cycles and duplicate recipe identities cannot produce known zero usage',()=>{
  const cyclic={...prep,lines:[{sourceType:'prep',recipeId:'prep',qty:1}]};
  expect(result([nested,cyclic]).issues.join()).toContain('Circular');
  expect(result([menu,{...menu}]).issues.join()).toContain('ambiguous');
  expect(result([nested,prep,{...prep}]).issues.join()).toContain('retained prep');
});
test('duplicate item identities are refused instead of selecting the first match',()=>{
  expect(result([menu],{menu:2},[food,{...food,name:'Duplicate'}]).complete).toBe(false);
  const legacy={...menu,lines:[{sourceType:'item',controlNumber:'LOCAL',qty:2}]};
  expect(result([legacy],{menu:2},[food,{...other,controlNumber:'LOCAL'}]).complete).toBe(false);
});
test('unmapped sales entries cannot be silently dropped, but confirmed orphan zero adds no usage',()=>{
  expect(portions(result([menu],{menu:2,orphan:1}))).toEqual([null]);
  expect(portions(result([menu],{menu:2,orphan:0}))).toEqual([4]);
  expect(portions(result([],{}))).toEqual([null]);
});
test.each([['empty',''],['whitespace','  '],['null',null],['undefined',undefined]])('a %s unmatched quantity carries no evidence and is not erased',(_,value)=>{
  const sales={menu:2,retired:value};const r=result([menu],sales);
  expect(portions(r)).toEqual([4]);expect(r.complete).toBe(true);expect(r.unmatchedSales).toEqual([]);
  expect(Object.hasOwn(sales,'retired')).toBe(true);expect(sales.retired).toBe(value);
  expect(portions(result([menu],{menu:value}))).toEqual([null]);
});
test.each([['nonzero','5'],['negative',-1],['malformed','invalid'],['boolean',false],['array',[0]],['object',{}]])('%s unmatched quantities stay held and identify the stored entry',(_,value)=>{
  const r=result([menu],{menu:2,retired:value});
  expect(portions(r)).toEqual([null]);expect(r.complete).toBe(false);
  expect(r.unmatchedSales).toEqual([{id:'retired',quantity:value}]);
  expect(r.issues.join()).toContain('Sales entry retired:');
});
test('broken blank-menu guidance offers confirmed zero without suggesting zero for positive sales',()=>{
  const broken={...menu,lines:[]};
  expect(result([broken],{}).issues.join()).toContain('If this menu had no sales, enter a confirmed 0');
  expect(result([broken],{menu:3}).issues.join()).not.toContain('enter a confirmed 0');
  expect(result([broken],{menu:0}).complete).toBe(true);
});
test.each([
  ['product', [{...menu,lines:[{...line,qty:1e308}]}],{menu:2}],
  ['sum', [{...menu,lines:[{...line,qty:1e308},{...line,qty:1e308}]}],{menu:1}],
  ['underflow',[{...menu,lines:[{...line,qty:1e-308}]}],{menu:1e-308}],
])('nonrepresentable %s is unknown without Infinity or false zero',(_,recipes,sales)=>{
  expect(portions(result(recipes,sales))).toEqual([null]);
});
test('nesting limits hold even when a deep sub-recipe was already cached',()=>{
  const chain=[{...prep,id:'p0',yieldQty:1}];
  for(let i=1;i<100;i++) chain.push({...prep,id:`p${i}`,yieldQty:1,lines:[{sourceType:'prep',recipeId:`p${i-1}`,qty:1}]});
  const first={...menu,id:'first',lines:[{sourceType:'prep',recipeId:'p98',qty:1}]};
  const second={...menu,id:'second',lines:[{sourceType:'prep',recipeId:'p99',qty:1}]};
  const r=result([first,second,...chain],{first:1,second:1});
  expect(r.issues.join()).toContain('depth of 100');expect(portions(r)).toEqual([null]);
});
test('calculation never mutates recipes, quantities, counts or inventory metadata',()=>{
  const inputs=JSON.parse(JSON.stringify({items:[food,other],recipes:[nested,prep],sales:{menu:2}}));
  const before=JSON.stringify(inputs);
  expectedSalesUsage(inputs.items,inputs.recipes,inputs.sales);
  expect(JSON.stringify(inputs)).toBe(before);
});
