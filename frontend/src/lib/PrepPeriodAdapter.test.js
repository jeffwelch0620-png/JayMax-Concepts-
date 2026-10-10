import axios from "axios";
import * as api from "./api";
jest.mock("axios");
test('prep period requests map the location and retain explicit cutoffs without any save',async()=>{
  axios.get.mockResolvedValue({data:{}});axios.post.mockResolvedValue({data:{}});
  const body={opening_count_id:'a',closing_count_id:'b',opening_cutoff:'before_all',closing_cutoff:'after_all',cutoffs_confirmed:true};
  await api.nativePrepPeriodCounts('papa_leonis');await api.previewNativePrepPeriod('papa_leonis',body);
  expect(axios.get).toHaveBeenCalledWith(expect.stringMatching(/\/purchases\/papa\/prep-periods\/counts$/));
  expect(axios.post).toHaveBeenCalledWith(expect.stringMatching(/\/purchases\/papa\/prep-periods\/preview$/),body);
});
