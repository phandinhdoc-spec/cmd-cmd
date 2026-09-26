import {readFileSync, mkdirSync, lstatSync, writeFileSync, renameSync, unlinkSync} from 'node:fs';
import {homedir} from 'node:os';
import {join} from 'node:path';
import {randomUUID} from 'node:crypto';

const roles = ['controller', 'planner', 'worker', 'verifier'];
const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const apis = ['openai-completions', 'openai-responses', 'anthropic-messages'];
const validApi = value => value === undefined || apis.includes(value);
const validUrl = value => { try { return typeof value === 'string' && Boolean(new URL(value)); } catch { return false; } };
const reserved = new Set(['command-code', 'anthropic', 'github-copilot', 'openai', 'copilot', 'codex', 'apiKey', 'userId', 'userName', 'keyName', 'authenticatedAt']);
const clean = value => String(value).replace(/[\x00-\x1f\x7f-\x9f]/g, '');

// Metadata only: never resolve credentials, execute key commands, or read auth.json.
export function declaredModels(config) {
  const providers = config?.provider ?? config?.providers ?? {};
  if (!object(config) || !object(providers)) throw new Error('providers.json không hợp lệ.');
  const result = [];
  for (const [provider, entry] of Object.entries(providers)) {
    if (!object(entry) || entry.disabled === true || entry.enabled === false) continue;
    if (!/^[a-z0-9][a-z0-9_.-]{0,63}$/.test(provider) || reserved.has(provider)) continue;
    const base = typeof entry.baseURL === 'string' && entry.baseURL ? entry.baseURL : entry.options?.baseURL;
    if (!validUrl(base) || !validApi(entry.api) || !object(entry.models)) continue;
    for (const [id, model] of Object.entries(entry.models)) {
      if (!id.trim() || clean(id) !== id || !object(model) || !validApi(model.api)) continue;
      if (model.baseURL !== undefined && !validUrl(model.baseURL)) continue;
      result.push({id: `${provider}/${id}`, name: clean(model.name || id)});
    }
  }
  return result;
}

function readJson(path, missing) {
  try { return JSON.parse(readFileSync(path, 'utf8')); }
  catch (error) {
    if (error.code === 'ENOENT' && missing !== undefined) return missing;
    // Do not echo JSON parser errors: provider configuration may contain secrets.
    throw new Error('Không đọc được JSON cấu hình; chưa lưu thay đổi.');
  }
}

function readOverrides(path) {
  const value = readJson(path, {roles: {}});
  if (!object(value) || !object(value.roles) || Object.values(value.roles).some(v => typeof v !== 'string')) {
    throw new Error('model-overrides.json không hợp lệ; chưa lưu thay đổi.');
  }
  return value;
}

function rejectSymlink(path) {
  try { if (lstatSync(path).isSymbolicLink()) throw new Error('Không ghi cấu hình qua symlink.'); }
  catch (error) { if (error.code !== 'ENOENT') throw error; }
}

function save(cwd, role, id) {
  const dir = join(cwd, '.cmd');
  const path = join(dir, 'model-overrides.json');
  rejectSymlink(dir);
  rejectSymlink(path);
  // Synchronous read/merge/rename: no await between reading and committing state.
  const value = readOverrides(path);
  if (id === undefined) delete value.roles[role];
  else value.roles[role] = id;
  value.updated_at = new Date().toISOString().replace(/\.\d{3}Z$/, '+00:00');
  mkdirSync(dir, {recursive: true});
  const temp = join(dir, `.model-overrides-${randomUUID()}.tmp`);
  try {
    writeFileSync(temp, `${JSON.stringify(value, null, 2)}\n`, {flag: 'wx', mode: 0o600});
    renameSync(temp, path);
  } finally {
    try { unlinkSync(temp); } catch (error) { if (error.code !== 'ENOENT') throw error; }
  }
}

export function register(cmd, {providerPath = join(homedir(), '.commandcode', 'providers.json')} = {}) {
  let busy = false;
  cmd.addCommand({
    name: 'cmd-models',
    description: 'Chọn model BYOK cho planner/worker/verifier',
    argumentHint: '[planner|worker|verifier|controller|status|auto [role]]',
    handler: async ({args, ui, cwd}) => {
      if (busy) return {message: 'Menu chọn model đang mở.'};
      busy = true;
      try {
        const parts = args.trim().split(/\s+/).filter(Boolean);
        let role = parts[0];
        if (role === 'status' && parts.length === 1) {
          const value = readOverrides(join(cwd, '.cmd', 'model-overrides.json'));
          return {message: roles.map(r => `${r}: ${clean(value.roles[r] ?? 'auto')}`).join('\n')};
        }
        if (role === 'auto' && parts.length <= 2) {
          role = parts[1] ?? 'controller';
          if (!roles.includes(role)) return {message: 'Role không hợp lệ.'};
          save(cwd, role);
          return {message: `${role}: auto`};
        }
        if (parts.length > 1 || (role && !roles.includes(role))) return {message: 'Dùng /cmd-models planner|worker|verifier|controller|status|auto [role].'};
        if (!role) role = await ui.select({title: 'Chọn role', options: roles.map(label => ({label}))});
        if (!roles.includes(role)) return {message: 'Đã hủy; giữ nguyên cấu hình.'};
        if (role === 'controller') return {message: 'Dùng /model để chọn model controller.'};
        const models = declaredModels(readJson(providerPath, {provider: {}}));
        if (!models.length) return {message: 'Chưa có model BYOK đã đăng ký. Mở /connect để thêm/cập nhật provider.'};
        const options = models.map(m => ({label: m.id, description: m.name}));
        const selected = await ui.select({title: `Chọn model BYOK cho ${role.toUpperCase()}`, options});
        if (selected === undefined) return {message: 'Đã hủy; giữ nguyên cấu hình.'};
        if (!models.some(m => m.id === selected)) return {message: 'Lựa chọn không hợp lệ; chưa lưu.'};
        // A /connect update while the menu was open may have removed the choice.
        if (!declaredModels(readJson(providerPath)).some(m => m.id === selected)) return {message: 'Model đã bị gỡ; mở lại /cmd-models.'};
        save(cwd, role, selected);
        return {message: `${role}: ${selected}`};
      } catch (error) {
        return {message: error.code ? 'Không thể ghi/đọc cấu hình; chưa lưu thay đổi.' : error.message};
      } finally { busy = false; }
    },
  });
}
