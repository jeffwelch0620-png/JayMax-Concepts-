import { confirmed, confirmSave, saveErrorText } from "./saveIntegrity";

test("structured field validation preserves locations and messages without echoing the submitted input", async () => {
  const error={response:{data:{detail:[{loc:["body","items",0,"par"],msg:"Value exceeds the supported range",input:"fictional private payload"}]}}};
  const report=jest.fn();
  expect(saveErrorText(error,"Fallback")).toBe("items.0.par: Value exceeds the supported range");
  expect(await confirmSave(()=>Promise.reject(error),report)).toBe(false);
  expect(report).toHaveBeenCalledWith("items.0.par: Value exceeds the supported range");
});

test.each([null,{}, {ok:false,errorMessage:{detail:"malformed"},revision:12}, {ok:false,errorMessage:"Refused",revision:12}])("unconfirmed outcome %j never reports success", async result => {
  expect(confirmed(result)).toBe(false);
  const report=jest.fn(); expect(await confirmSave(()=>Promise.resolve(result),report)).toBe(false);
  expect(report).toHaveBeenCalledWith(result?.errorMessage === "Refused" ? "Refused" : "Save was not confirmed. Your draft has been retained.");
});

test("malformed validation details fall back to readable text", () => {
  expect(saveErrorText({response:{data:{detail:[{msg:{bad:true}}]}},message:"Network unavailable"},"Fallback")).toBe("Network unavailable");
  expect(saveErrorText(null,"Fallback")).toBe("Fallback");
});
