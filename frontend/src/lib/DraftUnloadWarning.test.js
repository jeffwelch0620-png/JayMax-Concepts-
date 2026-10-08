import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { hasUnsavedDrafts, useDraftUnloadWarning } from "./saveIntegrity";

test("saved recipe focus does not warn, cached edits on another tab do, and cleanup removes the warning", async () => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  const drafts = { current: new Map([["recipe-focus:berts", { id: "saved-recipe" }]]) };
  function Screen() { useDraftUnloadWarning(drafts); return <p>Another tab</p>; }
  const container = document.createElement("div"); const root = createRoot(container);
  const unload = () => window.dispatchEvent(new Event("beforeunload", { cancelable: true }));
  try {
    await act(async () => root.render(<Screen />));
    expect(hasUnsavedDrafts(drafts.current)).toBe(false); expect(unload()).toBe(true);
    drafts.current.set("recipe:berts", { name: "Edited recipe" });
    expect(hasUnsavedDrafts(drafts.current)).toBe(true); expect(unload()).toBe(false);
    drafts.current.delete("recipe:berts"); expect(unload()).toBe(true);
    drafts.current.set("sales:rudds", { data: {} }); expect(unload()).toBe(false);
  } finally { await act(async () => root.unmount()); }
  expect(unload()).toBe(true);
});
