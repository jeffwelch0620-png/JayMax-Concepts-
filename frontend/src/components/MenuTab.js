import React, { useMemo } from "react";
import { Plus } from "lucide-react";
import { MENU_CATEGORIES, fmtMoney } from "../lib/calc";
import { PageTitle, EmptyState, Banner, Pill, cardCls, btnAcc } from "./common";

export function MenuTab({ dishes, onAddNew, onOpenDish }) {
  const menuDishes = useMemo(() => dishes.filter((d) => (d.recipeType || "menu") !== "prep"), [dishes]);
  const grouped = useMemo(() => {
    const map = {};
    MENU_CATEGORIES.forEach((c) => { map[c.name] = []; });
    menuDishes.forEach((d) => { (map[d.menuCategory] = map[d.menuCategory] || []).push(d); });
    Object.values(map).forEach((list) => list.sort((a, b) => (a.menuCode || "").localeCompare(b.menuCode || "")));
    return map;
  }, [menuDishes]);

  return (
    <div className="fade-slide-in" data-testid="menu-tab">
      <PageTitle right={<button className={btnAcc} onClick={onAddNew} data-testid="add-menu-item-button"><Plus size={15} /> Add New Item</button>}>
        Menu ({menuDishes.length} items)
      </PageTitle>
      {menuDishes.length === 0 ? <EmptyState text="No menu items yet. Build one in Menu Costing." /> : MENU_CATEGORIES.map((cat) => {
        const list = grouped[cat.name] || [];
        if (!list.length) return null;
        return (
          <div key={cat.code} className="mb-6">
            <Banner title={cat.name} right={<Pill color="var(--acc)" bg="#1E293B">{list.length}</Pill>} />
            <div className={`${cardCls} overflow-hidden`}>
              <table className="ops-table">
                <thead><tr><th>Code</th><th>Item</th><th>Description</th><th>Price</th></tr></thead>
                <tbody>
                  {list.map((d) => (
                    <tr key={d.id} data-testid={`menu-row-${d.menuCode || d.id}`}>
                      <td className="font-bold" style={{ color: "var(--acc)" }}>{d.menuCode || "—"}</td>
                      <td><button onClick={() => onOpenDish(d.id)} className="font-bold hover:underline text-left" style={{ color: "var(--acc)" }} data-testid={`menu-open-${d.id}`}>{d.name}</button></td>
                      <td className="text-slate-400">{d.description || "—"}</td>
                      <td className="num">{fmtMoney(d.price)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        );
      })}
    </div>
  );
}
