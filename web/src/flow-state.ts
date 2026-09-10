// Monotonic epochs also reject an old A response after A -> B -> A navigation.
export function updateEpoch(state: { key: string; epoch: number }, key: string) {
  if (state.key !== key) { state.key = key; state.epoch += 1; }
  return state.epoch;
}

export function generationStatus(result?: { applied: boolean }, running = false) {
  if (running) return "处理中";
  if (!result) return "未生成";
  return result.applied ? "已应用·待验证" : "已预览·未应用";
}

export async function resolveDrafts(guards: { dirty: boolean; save?: () => Promise<void>; discard?: () => void }[], save: boolean) {
  for (const guard of guards) {
    if (!guard.dirty) continue;
    if (save) {
      if (!guard.save) throw new Error("请回到编辑页保存修改。");
      await guard.save();
    } else guard.discard?.();
  }
}
