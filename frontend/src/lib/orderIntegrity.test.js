import {sameOrderDecimal} from "./orderIntegrity";
test("order decimals preserve unknown, zero and precision beyond Number",()=>{
  expect(sameOrderDecimal(null,0)).toBe(false);expect(sameOrderDecimal(null,null)).toBe(true);
  expect(sameOrderDecimal("001.5000","1.5")).toBe(true);expect(sameOrderDecimal("1.","1.00")).toBe(true);
  expect(sameOrderDecimal("0E-18","0")).toBe(true);expect(sameOrderDecimal("1e-3",".001")).toBe(true);
  expect(sameOrderDecimal("99.100000000000000001","99.100000000000000002")).toBe(false);
  expect(sameOrderDecimal("NaN","NaN")).toBe(false);expect(sameOrderDecimal("-1","1")).toBe(false);
});
