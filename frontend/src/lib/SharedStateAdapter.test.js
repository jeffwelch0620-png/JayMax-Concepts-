import axios from "axios";
import * as api from "./api";
jest.mock("axios");
beforeEach(()=>{jest.clearAllMocks();});
test("PostgreSQL state merge retains archive capabilities and exact quantities",async()=>{
  const shared={revision:2,areas:[],salesPeriod:{dishSales:{}},adjustments:[{qty:"123456789012345.000000000001"}],reportingPeriods:[{status:"closed"}],legacyStateCapabilities:{inventoryRetired:true,adjustmentsAvailable:false,reportingPeriodsAvailable:false},legacyStateBasis:{adjustments:{basis:"legacy_adjustments",archived:true,operational:false}}};
  axios.get.mockImplementation(url=>Promise.resolve({data:url.includes("/api/state/")?shared:url.includes("/prep/")?{prepStock:null,prepLogs:null}:[]}));
  const result=await api.fetchState("berts");expect(result.adjustments).toBe(shared.adjustments);expect(result.legacyStateCapabilities).toBe(shared.legacyStateCapabilities);expect(result.legacyStateBasis).toBe(shared.legacyStateBasis);
  expect(result.prepStock).toBeNull();expect(result.adjustments[0].qty).toBe("123456789012345.000000000001");
});
test("a failed shared-state read does not become an empty successful inventory load",async()=>{
  axios.get.mockRejectedValue(new Error("Shared state unavailable"));await expect(api.fetchState("berts")).rejects.toThrow("Shared state unavailable");expect(axios.get).toHaveBeenCalledTimes(1);
});
