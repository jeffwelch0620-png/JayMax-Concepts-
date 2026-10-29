import {overviewDecimal, overviewDifference, decimalText} from "./overviewDecimal";
test.each([
 ["4","3",{remaining:"1",excess:"0"}], ["4","5",{remaining:"0",excess:"1"}],
 ["4.000000000001","3.123456789013",{remaining:"0.876543210988",excess:"0"}],
 ["0","0",{remaining:"0",excess:"0"}], ["9999999999999999999999999999.999999999999","0.000000000001",{remaining:"9999999999999999999999999999.999999999998",excess:"0"}]
])("T04 exact arithmetic %s less %s",(p,r,expected)=>expect(overviewDifference(p,r)).toEqual(expected));
test.each([null,undefined,4,"","-1","NaN","Infinity","1e2","1.0000000000001"," 1","1 lb","1".repeat(29),{},".1"])("T04 invalid/unsupported quantity %#", v=>expect(()=>overviewDecimal(v)).toThrow());
test("T04 decimal formatting preserves value, explicit zero and harmless trailing zeros",()=>{expect(decimalText(overviewDecimal("0004.120000"))).toBe("4.12");expect(decimalText(overviewDecimal("0.000000000000"))).toBe("0");});
test.each([["0E-12","0"],["0E-13","0"],["1E-12","0.000000000001"],["3.000000000000","3"],["1.5E+3","1500"],["25E-1","2.5"],["9999999999999999999999999999.999999999999","9999999999999999999999999999.999999999999"]])("T04 native Decimal text %s reads exactly as %s",(v,text)=>expect(decimalText(overviewDecimal(v))).toBe(text));
test.each(["1E-13","1E+28","1.5e3","1E","E5","1E-1000"])("T04 exponent form beyond supported precision or malformed is held %#",v=>expect(()=>overviewDecimal(v)).toThrow());
test("T04 zero reviewed output in Python Decimal form still yields remaining",()=>expect(overviewDifference("4.000000000000","0E-12")).toEqual({remaining:"4",excess:"0"}));
