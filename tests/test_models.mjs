import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync, writeFileSync, readFileSync, mkdirSync, rmSync, existsSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {register, declaredModels} from '../.commandcode/mods/cmd-models/models.mjs';

function fixture(t) {
  const cwd = mkdtempSync(join(tmpdir(), 'cmd-models-'));
  t.after(() => rmSync(cwd, {recursive: true, force: true}));
  const providerPath = join(cwd, 'providers.json');
  const config = {provider: {agy: {baseURL: 'http://localhost:1234/v1', models: {'one': {name: 'One'}, 'two': {}}}, goat: {baseURL: 'https://example.com', models: {'vendor/three': {}}}}};
  writeFileSync(providerPath, JSON.stringify(config));
  let command;
  register({addCommand(value) { command = value; }}, {providerPath});
  assert.equal(command.name, 'cmd-models');
  const path = join(cwd, '.cmd/model-overrides.json');
  return {cwd, path, providerPath, config, run: (args, select) => command.handler({args, cwd, ui: {select}})};
}

for (const role of ['planner', 'worker', 'verifier']) test(`${role}: first UI is live model menu; exact selection saved without model turn`, async t => {
  const f = fixture(t);
  mkdirSync(join(f.cwd, '.cmd'));
  writeFileSync(f.path, JSON.stringify({roles: {controller: 'session', other: 'keep'}, extra: 1}));
  const result = await f.run(role, async menu => {
    assert.match(menu.title, new RegExp(role.toUpperCase()));
    assert.deepEqual(menu.options.map(o => o.label), ['agy/one', 'agy/two', 'goat/vendor/three']);
    return 'goat/vendor/three';
  });
  assert.deepEqual(result, {message: `${role}: goat/vendor/three`});
  const state = JSON.parse(readFileSync(f.path));
  assert.equal(state.roles[role], 'goat/vendor/three');
  assert.equal(state.roles.controller, 'session');
  assert.equal(state.roles.other, 'keep');
  assert.equal(state.extra, 1);
  assert.match(state.updated_at, /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\+00:00$/);
});

test('cancel/headless never saves or auto-selects', async t => {
  const f = fixture(t);
  await f.run('planner', async () => undefined);
  assert.equal(existsSync(f.path), false);
});
test('removed model and unrecognized answer never save', async t => {
  const f = fixture(t);
  await f.run('worker', async () => 'invented/model');
  assert.equal(existsSync(f.path), false);
  await f.run('worker', async () => {
    writeFileSync(f.providerPath, '{"provider":{}}');
    return 'agy/one';
  });
  assert.equal(existsSync(f.path), false);
});
test('malformed overrides preserved; no false success', async t => {
  const f = fixture(t);
  mkdirSync(join(f.cwd, '.cmd'));
  writeFileSync(f.path, '{broken');
  const result = await f.run('planner', async () => 'agy/one');
  assert.match(result.message, /chưa lưu/);
  assert.equal(readFileSync(f.path, 'utf8'), '{broken');
});
test('role menu, status, reset and controller do not start an agent', async t => {
  const f = fixture(t);
  const answers = ['verifier', 'agy/two'];
  await f.run('', async () => answers.shift());
  assert.match((await f.run('status')).message, /verifier: agy\/two/);
  await f.run('auto verifier');
  assert.deepEqual(JSON.parse(readFileSync(f.path)).roles, {});
  assert.deepEqual(await f.run('controller'), {message: 'Dùng /model để chọn model controller.'});
  assert.equal((await f.run('unknown')).prompt, undefined);
});
test('native declaration filtering, aliases, invalid entries and duplicate names', () => {
  const config = {providers: {
    a: {options: {baseURL: 'https://a.example'}, models: {same: {name: 'Identical'}}},
    b: {baseURL: 'https://b.example', models: {same: {name: 'Identical'}, invalid: null, badApi: {api: 'bad'}}},
    off: {disabled: true, baseURL: 'https://a.example', models: {x: {}}},
    invalid: {baseURL: 'not a URL', models: {x: {}}},
  }};
  assert.deepEqual(declaredModels(config).map(m => m.id), ['a/same', 'b/same']);
});
test('reread overrides after menu preserves intervening unrelated changes', async t => {
  const f = fixture(t);
  await f.run('planner', async () => {
    mkdirSync(join(f.cwd, '.cmd'));
    writeFileSync(f.path, JSON.stringify({roles: {worker: 'agy/two'}}));
    return 'agy/one';
  });
  assert.deepEqual(JSON.parse(readFileSync(f.path)).roles, {worker: 'agy/two', planner: 'agy/one'});
});
test('empty/malformed provider catalog is concise and never exposes JSON contents', async t => {
  const f = fixture(t);
  writeFileSync(f.providerPath, '{"secret":"PRIVATE" broken');
  const result = await f.run('planner', () => { throw new Error('should not open'); });
  assert.doesNotMatch(result.message, /PRIVATE/);
  assert.equal(existsSync(f.path), false);
});
test('busy guard prevents competing role menus', async t => {
  const f = fixture(t);
  let release;
  const pending = f.run('planner', () => new Promise(resolve => { release = resolve; }));
  const other = await f.run('worker', () => { throw new Error('second menu opened'); });
  assert.match(other.message, /đang mở/);
  release(undefined);
  await pending;
  assert.equal(existsSync(f.path), false);
});
