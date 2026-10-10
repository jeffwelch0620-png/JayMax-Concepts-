import axios from 'axios';
import * as api from './api';
jest.mock('axios');
test('opening requests preserve canonical store, exact key and separate void path',async()=>{axios.get.mockResolvedValue({data:{}});axios.post.mockResolvedValue({data:{}});
  await api.nativePrepOpeningSetup('papa_leonis');await api.previewNativePrepOpening('papa_leonis',{count_id:'count'});await api.saveNativePrepOpening('papa_leonis',{reviewed:true},'key');await api.previewNativePrepOpeningVoid('papa_leonis','event',{reason:'Correction'});await api.voidNativePrepOpening('papa_leonis','event',{reviewed:true},'voidkey');
  expect(axios.get).toHaveBeenCalledWith(expect.stringMatching(/\/purchases\/papa\/prep-openings\/setup$/));expect(axios.post.mock.calls[1]).toEqual([expect.stringMatching(/\/purchases\/papa\/prep-openings$/),{reviewed:true},{headers:{'Idempotency-Key':'key'}}]);expect(axios.post.mock.calls[3]).toEqual([expect.stringMatching(/\/prep-openings\/event\/void$/),{reviewed:true},{headers:{'Idempotency-Key':'voidkey'}}]);});
