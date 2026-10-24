#!/usr/bin/env node
/**
 * 文章图片的构建前处理：生成 WebP 多尺寸变体 + 尺寸清单。
 *
 * 为什么要有这一步
 * ----------------
 * `public/` 目录下的文件是**原样拷贝**进产物的，Astro 的图片管线完全不参与。
 * 所以文章插图既没有被压缩、也没有 `width`/`height`，浏览器要等图片下完才知道
 * 它多大，页面就会跳一下（CLS）。这个脚本补上这两件事：
 *
 * 1. 为每张图生成 WebP 变体（同一张图按宽度出 1–3 个文件）；
 * 2. 把原始尺寸和变体清单写进 `src/data/image-manifest.json`，
 *    供 `src/lib/markdown-images.mjs` 在构建时读出来拼 `<picture>` / `<img>`。
 *
 * 产物是**派生文件**，已加进 `.gitignore`：每次 `npm run dev` / `npm run build`
 * 都会先跑一遍。已经生成过且比源图新的文件直接跳过，所以第二次运行很快。
 *
 * 用法
 * ----
 *   node scripts/optimize_images.mjs          正常生成（增量）
 *   node scripts/optimize_images.mjs --force  忽略缓存，全部重做
 *   node scripts/optimize_images.mjs --dry    只报告，不写文件
 */

import { readdir, stat, writeFile, mkdir } from 'node:fs/promises';
import path from 'node:path';
import sharp from 'sharp';

const ROOT = path.resolve(import.meta.dirname, '..');
const SOURCE_DIR = path.join(ROOT, 'public', 'images', 'blog');
const MANIFEST_PATH = path.join(ROOT, 'src', 'data', 'image-manifest.json');

/** 原图之外的备选宽度。只有比原图窄 25% 以上才值得单独出一份。 */
const CANDIDATE_WIDTHS = [600, 960];
const SHRINK_RATIO = 0.75;
const WEBP_QUALITY = 80;
const SOURCE_EXT = new Set(['.jpg', '.jpeg', '.png']);

const args = new Set(process.argv.slice(2));
const FORCE = args.has('--force');
const DRY = args.has('--dry');

/** 递归收集源图，按路径排序保证输出稳定 */
async function collect(dir) {
  const out = [];
  let entries;
  try {
    entries = await readdir(dir, { withFileTypes: true });
  } catch {
    return out;
  }
  for (const entry of entries.sort((a, b) => a.name.localeCompare(b.name))) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      out.push(...(await collect(full)));
    } else if (SOURCE_EXT.has(path.extname(entry.name).toLowerCase())) {
      out.push(full);
    }
  }
  return out;
}

/** 这张图应该出哪几个宽度：先挑明显更窄的档位，最后补上原图宽度。 */
function planWidths(nativeWidth) {
  const widths = CANDIDATE_WIDTHS.filter((w) => w <= nativeWidth * SHRINK_RATIO);
  widths.push(nativeWidth);
  return [...new Set(widths)].sort((a, b) => a - b);
}

/** 站内绝对路径：public 下的文件在产物里就是根路径 */
function publicUrl(absPath) {
  const rel = path.relative(path.join(ROOT, 'public'), absPath).split(path.sep).join('/');
  return `/${rel}`;
}

function formatKb(bytes) {
  return `${(bytes / 1024).toFixed(0)} KB`;
}

async function main() {
  const sources = await collect(SOURCE_DIR);
  if (sources.length === 0) {
    console.log('[images] 没有找到文章图片，跳过。');
    return;
  }

  /** @type {Record<string, { w: number, h: number, bytes: number, variants: { w: number, src: string, bytes: number }[] }>} */
  const manifest = {};
  let written = 0;
  let skipped = 0;
  let sourceBytes = 0;
  let variantBytes = 0;

  for (const file of sources) {
    const srcStat = await stat(file);
    sourceBytes += srcStat.size;

    let meta;
    try {
      meta = await sharp(file).metadata();
    } catch (error) {
      console.warn(`[images] 跳过无法解析的文件 ${publicUrl(file)}：${error.message}`);
      continue;
    }
    if (!meta.width || !meta.height) {
      console.warn(`[images] 跳过读不到尺寸的文件 ${publicUrl(file)}`);
      continue;
    }

    const variants = [];
    for (const width of planWidths(meta.width)) {
      const outPath = file.replace(/\.(jpe?g|png)$/i, `-${width}.webp`);
      const outUrl = publicUrl(outPath);

      let needsBuild = FORCE;
      if (!needsBuild) {
        try {
          const outStat = await stat(outPath);
          needsBuild = outStat.mtimeMs < srcStat.mtimeMs;
        } catch {
          needsBuild = true;
        }
      }

      if (needsBuild) {
        if (DRY) {
          console.log(`[images] 待生成 ${outUrl}`);
          continue;
        }
        await sharp(file)
          .resize({ width, withoutEnlargement: true })
          .webp({ quality: WEBP_QUALITY, effort: 5 })
          .toFile(outPath);
        written += 1;
      } else {
        skipped += 1;
      }

      try {
        const outStat = await stat(outPath);
        variantBytes += outStat.size;
        variants.push({ w: width, src: outUrl, bytes: outStat.size });
      } catch {
        // dry 模式下文件还不存在，只记尺寸
        variants.push({ w: width, src: outUrl, bytes: 0 });
      }
    }

    manifest[publicUrl(file)] = {
      w: meta.width,
      h: meta.height,
      bytes: srcStat.size,
      variants,
    };
  }

  const payload = {
    $comment: '由 scripts/optimize_images.mjs 生成，请勿手改。',
    generatedAt: new Date().toISOString(),
    images: manifest,
  };

  if (!DRY) {
    await mkdir(path.dirname(MANIFEST_PATH), { recursive: true });
    await writeFile(MANIFEST_PATH, `${JSON.stringify(payload, null, 2)}\n`, 'utf8');
  }

  const count = Object.keys(manifest).length;
  const saving = sourceBytes > 0 ? (1 - variantBytes / sourceBytes) * 100 : 0;
  console.log(
    `[images] ${count} 张源图（${formatKb(sourceBytes)}）· ` +
      `生成 ${written} 个变体 / 命中缓存 ${skipped} 个 · ` +
      `变体合计 ${formatKb(variantBytes)}（相对原图 ${saving >= 0 ? '-' : '+'}${Math.abs(saving).toFixed(0)}%）`,
  );
  if (!DRY) console.log(`[images] 清单写入 ${path.relative(ROOT, MANIFEST_PATH)}`);
}

await main();
