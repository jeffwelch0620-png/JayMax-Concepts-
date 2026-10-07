import axios from "axios";
import * as api from "./api";
jest.mock("axios");
test("execution requests retain canonical location, track, observed version and exact key",async()=>{
  axios.get.mockResolvedValue({data:{}});axios.post.mockResolvedValue({data:{}});
  await api.prepExecution("papa_leonis","2026-10-08","bulk");
  await api.previewPrepExecution("papa_leonis","2026-10-08","bulk",{action:"complete",batch_event_id:"batch"},3);
  await api.savePrepExecution("papa_leonis","2026-10-08","bulk",{command:{action:"complete",batch_event_id:"batch"}},3,"exact-key");
  expect(axios.get.mock.calls[0]).toEqual([expect.stringMatching(/\/pg\/purchases\/papa\/prep-execution\/2026-10-08$/),{params:{track:"bulk"}}]);
  expect(axios.post.mock.calls[0][2]).toEqual({params:{track:"bulk"},headers:{"If-Match":'"3"'}});
  expect(axios.post.mock.calls[1]).toEqual([expect.stringMatching(/\/prep-execution\/2026-10-08\/commands$/),{command:{action:"complete",batch_event_id:"batch"}},{params:{track:"bulk"},headers:{"If-Match":'"3"',"Idempotency-Key":"exact-key"}}]);
});
