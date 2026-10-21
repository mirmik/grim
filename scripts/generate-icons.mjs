import { spawnSync } from 'node:child_process';
import { copyFileSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const icons = join(root, 'src-tauri/icons');
const resources = join(root, 'src-tauri/gen/android/app/src/main/res');
const source = join(icons, 'grimoire-source.png');
const background = '#f1efd9';
const temporary = mkdtempSync(join(tmpdir(), 'grim-icons-'));

try {
  const image = `data:image/png;base64,${readFileSync(source).toString('base64')}`;
  // Android masks a 72dp viewport out of a 108dp foreground. Keep the entire
  // book inside the central 66dp safe circle, including its brass corners.
  const foreground = `<svg xmlns="http://www.w3.org/2000/svg" width="108" height="108" viewBox="0 0 108 108"><image x="26" y="26" width="56" height="56" href="${image}"/></svg>`;
  writeFileSync(join(temporary, 'foreground.svg'), foreground);
  writeFileSync(join(temporary, 'manifest.json'), JSON.stringify({
    default: source,
    bg_color: background,
    android_fg: 'foreground.svg',
  }));

  function generate(input, output, extra = []) {
    const command = spawnSync(process.execPath, [
      join(root, 'node_modules/@tauri-apps/cli/tauri.js'),
      'icon', input, '--output', output, ...extra,
    ], { cwd: root, stdio: 'inherit' });
    if (command.error) throw command.error;
    if (command.status !== 0) throw new Error(`Tauri icon generation failed (${command.status})`);
  }

  const output = join(temporary, 'generated');
  generate(join(temporary, 'manifest.json'), output);

  // Legacy icons have no adaptive viewport: use larger artwork on a finished
  // tile rather than shrinking the padded 108dp foreground a second time.
  const densities = { mdpi: 48, hdpi: 72, xhdpi: 96, xxhdpi: 144, xxxhdpi: 192 };
  const sizes = Object.values(densities).flatMap(size => ['--png', String(size)]);
  for (const kind of ['square', 'round']) {
    const shape = kind === 'round'
      ? `<circle cx="54" cy="54" r="54" fill="${background}"/>`
      : `<rect width="108" height="108" rx="23" fill="${background}"/>`;
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="108" height="108" viewBox="0 0 108 108">${shape}<image x="11" y="11" width="86" height="86" href="${image}"/></svg>`;
    const input = join(temporary, `${kind}.svg`);
    writeFileSync(input, svg);
    generate(input, join(temporary, kind), sizes);
  }

  for (const name of ['icon.png', '32x32.png']) {
    copyFileSync(join(output, name), join(icons, name));
  }
  for (const [density, size] of Object.entries(densities)) {
    const directory = `mipmap-${density}`;
    mkdirSync(join(resources, directory), { recursive: true });
    copyFileSync(join(output, 'android', directory, 'ic_launcher_foreground.png'), join(resources, directory, 'ic_launcher_foreground.png'));
    copyFileSync(join(temporary, 'square', `${size}x${size}.png`), join(resources, directory, 'ic_launcher.png'));
    copyFileSync(join(temporary, 'round', `${size}x${size}.png`), join(resources, directory, 'ic_launcher_round.png'));
  }
  for (const relative of ['values/ic_launcher_background.xml', 'mipmap-anydpi-v26/ic_launcher.xml']) {
    const destination = join(resources, relative);
    mkdirSync(dirname(destination), { recursive: true });
    copyFileSync(join(output, 'android', relative), destination);
  }
  console.log('Updated Grim app icon, web favicon and Android launcher resources.');
} finally {
  rmSync(temporary, { recursive: true, force: true });
}
