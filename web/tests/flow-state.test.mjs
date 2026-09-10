import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import ts from 'typescript';

const source = readFileSync(new URL('../src/flow-state.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText;
const { updateEpoch, generationStatus, resolveDrafts } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`);

test('unchanged context preserves epoch; A → B → A rejects old A responses', () => {
  const state = { key: '', epoch: 0 };
  const oldA = updateEpoch(state, 'A');
  assert.equal(updateEpoch(state, 'A'), oldA);
  updateEpoch(state, 'B');
  assert.notEqual(updateEpoch(state, 'A'), oldA);
});

test('preview is never reported as applied or verified', () => {
  assert.equal(generationStatus(), '未生成');
  assert.equal(generationStatus({ applied: false }), '已预览·未应用');
  assert.equal(generationStatus({ applied: true }), '已应用·待验证');
  assert.equal(generationStatus({ applied: false }, true), '处理中');
});

test('save completes before navigation can continue', async () => {
  const events = [];
  await resolveDrafts([{ dirty: true, save: async () => { await Promise.resolve(); events.push('saved'); } }], true);
  events.push('navigate');
  assert.deepEqual(events, ['saved', 'navigate']);
});

test('save failure prevents continuation and does not discard', async () => {
  let discarded = false;
  let navigated = false;
  await assert.rejects(async () => {
    await resolveDrafts([{ dirty: true, save: async () => { throw new Error('disk full'); }, discard: () => { discarded = true; } }], true);
    navigated = true;
  }, /disk full/);
  assert.equal(discarded, false);
  assert.equal(navigated, false);
});

test('discard path does not save; clean guards are ignored', async () => {
  let count = 0;
  await resolveDrafts([{ dirty: true, discard: () => { count++; }, save: async () => { throw new Error('unexpected'); } }, { dirty: false, discard: () => { count++; } }], false);
  assert.equal(count, 1);
});

test('missing save handler rejects navigation', async () => {
  await assert.rejects(resolveDrafts([{ dirty: true }], true), /保存/);
});
