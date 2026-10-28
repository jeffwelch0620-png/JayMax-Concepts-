import {overviewDecimal, overviewDifference, decimalText} from "./overviewDecimal";
test.each([
 ["4","3",{remaining:"1",excess:"0"}], ["4","5",{remaining:"0",excess:"1"}],
 ["4.000000000001","3.123456789013",{remaining:"0.876543210988",excess:"0"}],
 ["0","0",{remaining:"0",excess:"0"}], ["9999999999999999999999999999.999999999999","0.000000000001",{remaining:"9999999999999999999999999999.999999999998",excess:"0"}]
])("T04 exact arithmetic %s less %s",(p,r,expected)=>expect(overviewDifference(p,r)).toEqual(expected));
test.each([null,undefined,4,"","-1","NaN","Infinity","1e2","1.0000000000001"," 1","1 lb","1".repeat(29),{},".1"])("T04 invalid/unsupported quantity %#", v=>expect(()=>overviewDecimal(v)).toThrow());
test("T04 decimal formatting preserves value, explicit zero and harmless trailing zeros",()=>{expect(decimalText(overviewDecimal("0004.120000"))).toBe("4.12");expect(decimalText(overviewDecimal("0.000000000000"))).toBe("0");});
