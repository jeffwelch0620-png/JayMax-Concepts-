import { checkedCatalogDecimal } from "./catalogDecimal";
import { catalogDecimal, catalogPrice } from "./api";

test.each(["1e200000", "1e-20000", "0e200000", "0e-20000", "1e512", "1e-513", "9".repeat(2049)])("both catalog validators reject unsupported decimal %s with a range message", value => {
  for (const validate of [catalogDecimal, catalogPrice]) expect(() => validate(value)).toThrow("512 integer digits, 512 decimal places");
});

test.each(["1.123456789012345678", "12345678901234567890.000000000001", "1e511", "1e-512", "9".repeat(512) + "." + "1".repeat(512), "0E-10", "+0.00001", "1e00000000000400"])("valid decimal %s remains exact text in both catalog paths", value => {
  expect(catalogDecimal(value)).toBe(value); expect(catalogPrice(value)).toBe(value);
});

test.each([true, false, {}, [], "NaN", "Infinity", "-1", " "])("invalid decimal %p cannot become a trusted price or quantity", value => {
  expect(() => checkedCatalogDecimal(value)).toThrow("non-negative finite");
});

test("unknown and explicit zero remain distinct", () => {
  expect(catalogPrice(null)).toBeNull(); expect(catalogDecimal("")).toBeNull();
  expect(catalogPrice("0")).toBe("0"); expect(catalogDecimal("0E-10")).toBe("0E-10");
});
