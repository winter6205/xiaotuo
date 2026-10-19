// 逐页调用 Course.inventory()（与 build-manifest.js 同法），把结果以 JSON 打到 stdout。
// 用法：node inventory.cjs <课程根目录> <课程子目录>（需 <课程根目录>/shared/tools/lib.js）
const path = require('path');
const base = path.resolve(process.argv[2]);
process.argv.splice(2, 1);                       // 剩下 --course 由 lib.js 解析
const course = process.argv[2];
process.argv.splice(2, 1, '--course');
process.argv.splice(3, 0, course);
const { allPages, launch, url, isSub } = require(path.join(base, 'shared/tools/lib.js'));
(async () => {
  const b = await launch(); const out = [];
  for (const f of allPages()) {
    const p = await b.newPage(); const errs = [];
    p.on('pageerror', e => errs.push(e.message));
    await p.goto(url(f), { waitUntil: 'load' });
    await p.evaluate(() => localStorage.clear()); await p.reload({ waitUntil: 'load' });
    const r = await p.evaluate(() => window.Course && Course.inventory ? Course.inventory() : null);
    const tracks = await p.evaluate(() => [...document.querySelectorAll('input.track[data-id]')].map(e => e.getAttribute('data-id')));
    await p.close();
    out.push({ file: f, sub: isSub(f), errors: errs, inv: r, tracks });
  }
  await b.close();
  process.stdout.write(JSON.stringify(out));
})().catch(e => { console.error(e); process.exit(1); });
