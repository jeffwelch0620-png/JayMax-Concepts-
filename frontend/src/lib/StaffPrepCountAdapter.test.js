import axios from "axios";
import * as api from "./api";
jest.mock("axios");
test("prep count requests use canonical PostgreSQL location and retain review bodies and exact retry keys",async()=>{
  axios.get.mockResolvedValue({data:{}});axios.post.mockResolvedValue({data:{}});
  const sheet={performed_at:"2026-10-07T22:00:00-04:00",units:[{profile_id:"verified-profile"}]},quantity={expected_review_hash:"a".repeat(64),lines:[{product_id:"prep",quantity:"2.123456789012"}]};
  await api.staffPrepCountSetup("papa_leonis");await api.previewStaffPrepCountSheet("papa_leonis",sheet);await api.issueStaffPrepCountSheet("papa_leonis",{sheet},"issue-key");
  await api.staffPrepCountDrafts("papa_leonis","4826");await api.submitStaffPrepCountDraft("papa_leonis","sheet",quantity,"submit-key");
  await api.previewStaffPrepCountDecision("papa_leonis","sheet",{decision:"accepted"});await api.decideStaffPrepCountSheet("papa_leonis","sheet",{expected_observation_hash:"b".repeat(64)},"decision-key");
  expect(axios.get.mock.calls[0][0]).toMatch(/\/pg\/purchases\/papa\/staff-prep-counts$/);
  expect(axios.post.mock.calls[1]).toEqual([expect.stringMatching(/\/papa\/staff-prep-counts$/),{sheet},{headers:{"Idempotency-Key":"issue-key"}}]);
  expect(axios.post.mock.calls[2]).toEqual([expect.stringMatching(/\/pg\/staff\/papa\/prep-count-drafts$/),{pin:"4826"}]);
  expect(axios.post.mock.calls[3]).toEqual([expect.stringMatching(/\/papa\/prep-count-drafts\/sheet\/submit$/),quantity,{headers:{"Idempotency-Key":"submit-key"}}]);
  expect(axios.post.mock.calls[5][2]).toEqual({headers:{"Idempotency-Key":"decision-key"}});
});
