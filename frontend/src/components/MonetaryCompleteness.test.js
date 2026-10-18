import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { AdjustmentsTab } from './AdjustmentsTab';

const item = { controlNumber: 'TEST', name: 'Fictional mismatch', packCount: 1, unitQty: 5, unitUOM: 'lb',
  portionSize: 4, portionUOM: 'fl oz', vendorSkus: [{ price: 20 }] };
let root, container, persist;
beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container);
  persist = jest.fn();
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); });
const view = readOnly => <AdjustmentsTab rid="fictional" items={[item]} persist={persist} showToast={jest.fn()} readOnly={readOnly}
  adjustments={[{ id: 'fictional', controlNumber: 'TEST', qty: 1, qtyBasis: 'purchase', reason: 'waste', date: '9999-01-01' }]} />;

test('legacy adjustment summaries, preview and history display unknown instead of free waste', async () => {
  await act(async () => root.render(view(false)));
  expect(container.textContent.match(/Unknown/g)).toHaveLength(4);
  expect(container.querySelector('[data-testid="adj-row-fictional"]').textContent).toContain('Unknown');
  expect(container.textContent).not.toContain('$0.00');
  expect(persist).not.toHaveBeenCalled();
});

test('native retained adjustments stay unvalued and do not expose legacy writes', async () => {
  await act(async () => root.render(view(true)));
  expect(container.querySelector('[data-testid="retained-adjustments"]').textContent).toContain('cannot be added, deleted or valued');
  expect(container.querySelector('[data-testid="log-adjustment-button"]')).toBeNull();
  expect(persist).not.toHaveBeenCalled();
});
