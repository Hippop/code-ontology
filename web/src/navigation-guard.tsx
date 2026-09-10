import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { resolveDrafts } from "./flow-state";

type Guard = { label: string; dirty: boolean; busy?: boolean; save?: () => Promise<void>; discard?: () => void };
type Navigation = { register: (read: () => Guard) => () => void; navigate: (action: () => void) => void };
const Context = createContext<Navigation>({ register: () => () => {}, navigate: action => action() });

export function NavigationProvider({ children }: { children: React.ReactNode }) {
  const guards = useRef(new Set<() => Guard>());
  const [pending, setPending] = useState<{ action: () => void; guards: Guard[] }>();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const dialog = useRef<HTMLDialogElement>(null);
  const register = useCallback((read: () => Guard) => { guards.current.add(read); return () => { guards.current.delete(read); }; }, []);
  const navigate = useCallback((action: () => void) => {
    const active = [...guards.current].map(read => read()).filter(g => g.dirty || g.busy);
    if (!active.length) { action(); return; }
    setError(""); setPending({ action, guards: active });
  }, []);
  const api = useMemo(() => ({ register, navigate }), [register, navigate]);
  useEffect(() => {
    if (!pending) return;
    const previous = document.activeElement as HTMLElement | null;
    dialog.current?.showModal();
    return () => { dialog.current?.close(); previous?.focus(); };
  }, [pending]);
  const blocked = pending?.guards.some(g => g.busy);
  async function leave(save: boolean) {
    if (!pending || blocked || saving) return;
    setSaving(true); setError("");
    try {
      await resolveDrafts(pending.guards, save);
      const action = pending.action; setPending(undefined); action();
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setSaving(false); }
  }
  return <Context.Provider value={api}>{children}
    {pending && <dialog ref={dialog} className="navigation-dialog" aria-labelledby="leave-title" onCancel={e => { e.preventDefault(); if (!saving) setPending(undefined); }}>
      <h2 id="leave-title">{blocked ? "当前操作尚未完成" : "离开前处理未保存修改"}</h2>
      <p>{pending.guards.map(g => g.label).join("、")}</p>
      <p>{blocked ? "请等待操作结束，再取消此提示并重新导航。离开不会取消后端执行。" : "保存失败时会留在当前页面，未保存内容不会被清除。"}</p>
      {error && <p role="alert" className="error">{error}</p>}
      <div className="button-row">
        <button type="button" disabled={saving} autoFocus onClick={() => setPending(undefined)}>取消，继续编辑</button>
        {!blocked && <><button type="button" disabled={saving} onClick={() => leave(false)}>放弃修改并离开</button><button type="button" disabled={saving || pending.guards.some(g => g.dirty && !g.save)} onClick={() => leave(true)}>{saving ? "保存中…" : "保存后离开"}</button></>}
      </div>
    </dialog>}
  </Context.Provider>;
}

export function useNavigation() { return useContext(Context).navigate; }

export function useLeaveGuard(guard: Guard) {
  const { register } = useContext(Context);
  const current = useRef(guard); current.current = guard;
  useEffect(() => register(() => current.current), [register]);
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => { if (current.current.dirty || current.current.busy) { event.preventDefault(); event.returnValue = ""; } };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, []);
}
