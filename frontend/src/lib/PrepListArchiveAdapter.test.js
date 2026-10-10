import axios from "axios";
import * as api from "./api";
jest.mock("axios");
test("archive uses canonical PostgreSQL location and preserves filters and raw values",async()=>{
  const data={records:[{countType:null,lines:[{yield_qty:"123456789012345.000000000001"}]}]};axios.get.mockResolvedValue({data});
  const params={classification:"unclassified",date_from:"2026-10-01",date_through:"2026-10-08",after_date:"2026-10-03",after_id:"11111111-1111-4111-8111-111111111111",limit:50};
  const result=await api.prepListArchive("papa_leonis",params);
  expect(axios.get).toHaveBeenCalledWith(expect.stringMatching(/\/api\/pg\/prep-list-archive\/papa$/),{params});expect(result).toBe(data);
});
