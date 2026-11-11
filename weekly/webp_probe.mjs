// 试验性 · 存储量探针：把本地样本图按站点规范转 WebP，回报各档字节数。
// 由 weekly/media_backfill.py:estimate_webp() 调用，stdout 是 JSON。
import fs from 'node:fs';
import path from 'node:path';
import sharp from 'sharp';

const rows = [];
for (const file of process.argv.slice(2)) {
  try {
    const meta = await sharp(file).metadata();
    const original = fs.statSync(file).size;
    const sizes = {};
    for (const width of [600, 960]) {
      const buf = await sharp(file)
        .resize({ width, withoutEnlargement: true })
        .webp({ quality: 80 })
        .toBuffer();
      sizes[String(width)] = buf.length;
    }
    sizes.original_width = (await sharp(file).webp({ quality: 80 }).toBuffer()).length;
    rows.push({ file: path.basename(file), width: meta.width, height: meta.height, original, sizes });
  } catch (error) {
    rows.push({ file: path.basename(file), error: String(error).slice(0, 120) });
  }
}
process.stdout.write(JSON.stringify(rows));
