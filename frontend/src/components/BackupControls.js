import React from "react";
import { Download, Upload } from "lucide-react";

const buttonClass = "flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-semibold border border-[#334155] bg-[#161F30] text-slate-300 hover:border-[var(--acc)] transition disabled:opacity-50";

export function BackupControls({ nativeMode, onBackup, onRestore }) {
  const notice = "Complete inventory backup is awaiting setup. App files omit invoice history, physical counts and closed reports.";
  return <>
    <button disabled={nativeMode} onClick={nativeMode ? undefined : onBackup} title={nativeMode ? notice : undefined} className={buttonClass} data-testid="backup-button"><Download size={13} /> Backup</button>
    <button disabled={nativeMode} onClick={nativeMode ? undefined : onRestore} title={nativeMode ? notice : undefined} className={buttonClass} data-testid="restore-button"><Upload size={13} /> Restore</button>
    {nativeMode && <p role="status" className="text-xs text-amber-200 max-w-xs">{notice}</p>}
  </>;
}
