import axios from "axios";
import * as api from "./api";
jest.mock("axios");
test("staff production adapters bind explicit date track scope key and current credentials",async()=>{
  axios.get.mockResolvedValue({data:{}});axios.post.mockResolvedValue({data:{}});
  const b={submission:{root_id:"stable-root"}},d={submission_id:"stable-revision",decision:"accepted",task_complete:false};
  await api.staffProductionSetup("papa_leonis","2026-10-08","bulk","member","4826");await api.previewStaffProduction("papa_leonis","2026-10-08","bulk",b,"4826");await api.submitStaffProduction("papa_leonis","2026-10-08","bulk",b,"same-key","new-pin");await api.staffProductionReviewSetup("papa_leonis","2026-10-08","bulk");await api.previewStaffProductionDecision("papa_leonis","2026-10-08","bulk",d);await api.decideStaffProduction("papa_leonis","2026-10-08","bulk",d,"decision-key");
  expect(axios.post.mock.calls[0]).toEqual([expect.stringMatching(/\/staff\/papa\/prep-production\/2026-10-08\/setup$/),{pin:"4826"},{params:{track:"bulk",staff_member_id:"member"}}]);
  expect(axios.post.mock.calls[2]).toEqual([expect.stringMatching(/\/submissions$/),{...b,pin:"new-pin"},{params:{track:"bulk"},headers:{"Idempotency-Key":"same-key"}}]);
  expect(axios.get.mock.calls[0]).toEqual([expect.stringMatching(/\/purchases\/papa\/staff-prep-production\/2026-10-08$/),{params:{track:"bulk"}}]);
  expect(axios.post.mock.calls[4]).toEqual([expect.stringMatching(/\/decisions$/),d,{params:{track:"bulk"},headers:{"Idempotency-Key":"decision-key"}}]);
});
