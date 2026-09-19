const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const { spawnSync } = require('node:child_process');

const installer = path.resolve(__dirname, '../scripts/install.js');

function withFolder(t) {
  const folder = fs.mkdtempSync(path.join(os.tmpdir(), 'customer-finder-test-'));
  t.after(() => fs.rmSync(folder, { recursive: true, force: true }));
  return folder;
}

test('fresh install and upgrade preserve custom previous files', (t) => {
  const root = withFolder(t);
  const skills = path.join(root, 'skills');
  const run = () => spawnSync(process.execPath, [installer, '--skills-dir', skills], { encoding: 'utf8' });
  assert.equal(run().status, 0);
  const target = path.join(skills, 'first-customer-finder');
  fs.writeFileSync(path.join(target, 'user-note.txt'), 'preserve me');
  const upgraded = run();
  assert.equal(upgraded.status, 0, upgraded.stderr);
  const backup = upgraded.stdout.match(/Previous installation preserved at: (.+)/)[1];
  assert.equal(fs.readFileSync(path.join(backup, 'user-note.txt'), 'utf8'), 'preserve me');
  assert.ok(fs.existsSync(path.join(target, 'scripts/prospect_history.py')));
  assert.ok(!fs.existsSync(path.join(target, 'scripts/__pycache__')));
});

test('symlink installation is not replaced or followed', (t) => {
  const root = withFolder(t);
  const target = path.join(root, 'first-customer-finder');
  const external = path.join(root, 'external');
  fs.mkdirSync(external);
  fs.symlinkSync(external, target);
  const run = spawnSync(process.execPath, [installer, '--skills-dir', root], { encoding: 'utf8' });
  assert.notEqual(run.status, 0);
  assert.ok(fs.lstatSync(target).isSymbolicLink());
});

test('dangling symlinks are refused', (t) => {
  const root = withFolder(t);
  const target = path.join(root, 'first-customer-finder');
  fs.symlinkSync(path.join(root, 'missing'), target);
  const run = spawnSync(process.execPath, [installer, '--skills-dir', root]);
  assert.notEqual(run.status, 0);
  assert.ok(fs.lstatSync(target).isSymbolicLink());
});

test('help does not install and invalid options fail', (t) => {
  const root = withFolder(t);
  const run = spawnSync(process.execPath, [installer, '--help', '--skills-dir', path.join(root, 'skills')]);
  assert.equal(run.status, 0);
  assert.ok(!fs.existsSync(path.join(root, 'skills')));
  assert.notEqual(spawnSync(process.execPath, [installer, '--bad']).status, 0);
});
