import axios from 'axios';
import * as api from './api';
jest.mock('axios');
test('saved analytical journal maps location and preserves exact reviewed request keys',async()=>{
  axios.get.mockResolvedValue({data:{}});axios.post.mockResolvedValue({data:{}});const body={submission:{reason:'Reviewed'},expected_review_hash:'hash',reviewed:true};
  await api.nativePrepPeriodJournal('papa_leonis');await api.previewNativePrepPeriodClose('papa_leonis',body.submission);await api.saveNativePrepPeriodClose('papa_leonis',body,'close-key');await api.previewNativePrepPeriodReopen('papa_leonis',body.submission);await api.saveNativePrepPeriodReopen('papa_leonis',body,'reopen-key');
  expect(axios.get).toHaveBeenCalledWith(expect.stringMatching(/\/purchases\/papa\/prep-period-journal$/));
  expect(axios.post).toHaveBeenCalledWith(expect.stringMatching(/\/prep-period-journal$/),body,{headers:{'Idempotency-Key':'close-key'}});
  expect(axios.post).toHaveBeenCalledWith(expect.stringMatching(/\/prep-period-journal\/reopen$/),body,{headers:{'Idempotency-Key':'reopen-key'}});
});
