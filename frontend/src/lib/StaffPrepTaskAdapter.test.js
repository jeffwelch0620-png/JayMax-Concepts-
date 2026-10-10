import axios from "axios";
import * as api from "./api";
jest.mock("axios");
test("staff prep assignment and read adapters preserve stable IDs, explicit date and retry key",async()=>{
  axios.get.mockResolvedValue({data:{}});axios.post.mockResolvedValue({data:{}});
  const b={task_id:"stable-task",expected_revision:2,staff_member_id:"stable-member",note:"Reviewed"},save={assignment:b,expected_review_hash:"a".repeat(64),reviewed:true};
  await api.staffPrepTaskSetup("papa_leonis","2026-10-08","bulk");await api.previewStaffPrepAssignment("papa_leonis","2026-10-08","bulk",b);await api.saveStaffPrepAssignment("papa_leonis","2026-10-08","bulk",save,"same-key");await api.staffPrepTaskPlan("papa_leonis",{pin:"4826",day:"2026-10-08",track:"bulk",staff_member_id:null});
  expect(axios.get.mock.calls[0]).toEqual([expect.stringMatching(/\/purchases\/papa\/staff-prep-tasks\/2026-10-08$/),{params:{track:"bulk"}}]);
  expect(axios.post.mock.calls[1]).toEqual([expect.stringMatching(/\/assignments$/),save,{params:{track:"bulk"},headers:{"Idempotency-Key":"same-key"}}]);
  expect(axios.post.mock.calls[2][0]).toMatch(/\/staff\/papa\/prep-task-plan$/);
});
