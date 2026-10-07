import axios from "axios";
import * as api from "./api";
jest.mock("axios");
test("container requests preserve decimal strings and retry keys on canonical PostgreSQL routes",async()=>{
  axios.get.mockResolvedValue({data:{}});axios.post.mockResolvedValue({data:{}});
  const body={action:"fill",quantity:"2.123456789012",profile_id:"verified"},command={body,expected_review_hash:"a".repeat(64),reviewed:true};
  await api.prepContainers("papa_leonis");await api.previewPrepContainer("papa_leonis",body);await api.savePrepContainer("papa_leonis",command,"unchanged-key");
  expect(axios.get.mock.calls[0][0]).toMatch(/\/pg\/purchases\/papa\/prep-containers$/);
  expect(axios.post.mock.calls[1]).toEqual([expect.stringMatching(/\/papa\/prep-containers\/commands$/),command,{headers:{"Idempotency-Key":"unchanged-key"}}]);
});
