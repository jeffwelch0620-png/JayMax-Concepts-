import { storeMark } from "./storeMark";
import { RESTAURANTS, OWNER } from "../lib/calc";

test("every store and the owner view has its own mark token", () => {
  expect([...RESTAURANTS, OWNER].map(r => storeMark(r.id))).toEqual(
    ["var(--jm-store-berts)", "var(--jm-store-rudds)", "var(--jm-store-papa)", "var(--jm-store-owner)"]);
  expect(storeMark("papa")).toBe("var(--jm-store-papa)");          // the database store id
  expect(storeMark("unknown")).toBe("var(--jm-store-owner)");
});
