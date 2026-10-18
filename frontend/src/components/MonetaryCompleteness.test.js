import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { AdjustmentsTab } from './AdjustmentsTab';
import { DashboardTab } from './DashboardTab';
jest.mock('./DashboardPrepWindow', () => ({ DashboardPrepWindow: () => null }));

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

test('dashboard names unavailable variance, retains the known row and sorts unknown waste last', async () => {
  const items = ['A1', 'B1'].map(code => ({ ...item, itemCode: code, controlNumber: code, name: code, storageArea: 'Fictional storage', salesTracked: true, portionUOM: 'oz' }));
  const dishes = ['Pizza', 'Salad'].map((id, i) => ({ id, name: id, price: 10, lines: [{ itemCode: items[i].itemCode, qty: 1 }] }));
  const salesPeriod = { periodStart: '2026-10-01', periodEnd: '2026-10-31', dishSales: { Pizza: '5' },
    itemCounts: { A1: { beginning: 10, ending: 5 }, B1: { beginning: 10, ending: 5 } } };
  const adjustments = [
    { ...propsAdjustment(), controlNumber: 'MISSING', reason: 'waste' },
    { ...propsAdjustment(), controlNumber: 'A1', reason: 'spoilage' },
    { ...propsAdjustment(), controlNumber: 'A1', reason: 'comp', qty: 0 },
  ];
  await act(async () => root.render(<DashboardTab rid="fictional" items={items} dishes={dishes} purchases={[]} adjustments={adjustments}
    salesPeriod={salesPeriod} reportingPeriods={[]} onOpenHistory={jest.fn()} setFlaggedOnly={jest.fn()} />));
  expect(container.querySelector('[data-testid="variance-unavailable"]').textContent).toContain('1 item has Unknown variance');
  const variance = container.querySelector('[data-testid="variance-card"]');
  expect(variance.querySelector('tbody').textContent).toContain('A1');
  expect(variance.querySelector('tbody').textContent).not.toContain('B1');
  expect(['#f59e0b', 'rgb(245, 158, 11)']).toContain(container.querySelector('[data-testid="metric-variance"]').style.borderTopColor.toLowerCase());
  const waste = container.querySelector('[data-testid="waste-card"]');
  expect([...waste.querySelectorAll('span')].map(el => el.textContent)).toEqual(['Spoilage', 'Comp / Giveaway', 'Waste']);
  expect(waste.textContent).toContain('$0.00'); expect(waste.textContent).toContain('Unknown');
});
function propsAdjustment() { return { date: '2026-10-10', qty: 1, qtyBasis: 'portion' }; }
