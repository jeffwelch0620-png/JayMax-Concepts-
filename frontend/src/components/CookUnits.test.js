import {madeSoFar} from "./StaffPrepTasks";
import {inTaskUnit} from "./PrepExecution";

jest.mock("../lib/api",()=>({}));
jest.mock("../lib/push",()=>({pushSupported:()=>false}));

// Step E: cooks and managers read amounts in the task's own unit, not the base unit or an ID.
test("a cook sees what has been accepted in the task's unit",()=>{
  const t={source_unit:"gal",base_unit:"fl_oz",factor:"128",progress:{reviewed_base_quantity:"0"}};
  expect(madeSoFar(t)).toBe("Nothing accepted yet.");
  expect(madeSoFar({...t,progress:{reviewed_base_quantity:"256"}})).toBe("Accepted so far: 2 gal.");
  expect(madeSoFar({...t,factor:undefined,progress:{reviewed_base_quantity:"256"}})).toBe("Accepted so far: 256 fl_oz.");
});
test("the release card shows planned and reviewed amounts in the task's unit, base after",()=>{
  const t={factor:"128",task_snapshot:{source_unit:"gal",base_unit:"fl_oz"}};
  expect(inTaskUnit(t,{planned_base_quantity:"256",effective_base_quantity:"0",reviewed_base_quantity:"128"}))
    .toBe("planned 2 gal, recorded 0 gal, reviewed 1 gal (base: 256 fl_oz planned)");
  expect(inTaskUnit({factor:"1",task_snapshot:{source_unit:"lb",base_unit:"lb"}},{planned_base_quantity:"6",effective_base_quantity:"0",reviewed_base_quantity:"0"}))
    .toBe("planned 6 lb, recorded 0 lb, reviewed 0 lb");
  expect(inTaskUnit({task_snapshot:{base_unit:"lb"}},{planned_base_quantity:null,effective_base_quantity:"0",reviewed_base_quantity:"0"})).toBe("planned Unknown, current recorded 0, reviewed 0 lb");
});
