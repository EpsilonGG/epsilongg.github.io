/**
 * 生成 Open Graph 分享图（`public/og/`）。
 *
 * 为什么不做「动态 OG」：M5 那套方案要在构建时排版文字（字体子集、断行、每页一个
 * PNG），成本全在「字」上。现在只做**裁图**——把已有的图按 1200×630 裁一条，
 * 不加任何文字。分享出去照样能看出是哪一篇，而代码只有几十行、没有字体文件。
 *
 * 两级：
 *
 * - `public/og/default.jpg` —— 全站默认。取站点背景图 `images/bg/sky.jpg` 中间那条。
 * - `public/og/blog/<slug>.jpg` —— 每篇文章。取正文**第一张本地图**。
 *
 * 优先级写在 `src/data/og-manifest.json` 里，页面侧按「文章图 → 默认图」退。
 * 清单要提交：CI 只跑 `npm run build`，不跑这个脚本（和 `image-manifest.json` 同理）。
 *
 * 运行：`npm run og`（`npm run images` 会顺带跑它）。
 */
import sharp from 'sharp';
import { mkdirSync, readdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

const W = 1200;
const H = 630;

const BG = 'public/images/bg/sky.jpg';
/**
 * 背景图是 1920×1440（4:3），1200×630 是 1.9:1，必须切掉上下。
 * 切 200 而不是居中：原图最上方有一条深色的屋檐斜边，留着会像一道脏边；
 * 从 200 开始正好保住整团积云，又把它让出去。
 */
const BG_TOP = 200;
const BG_CROP_H = Math.round(1920 / (W / H)); // 1008

const OUT_DIR = 'public/og';
const BLOG_DIR = 'src/content/blog';
const MANIFEST = 'src/data/og-manifest.json';

/** 从正文里取第一张**本地**图；远程图（`http…`）跳过——构建期不联网。 */
function firstLocalImage(markdown) {
  const body = markdown.replace(/^---\n[\s\S]*?\n---\n/, '');
  for (const match of body.matchAll(/!\[[^\]]*\]\((\S+?)(?:\s+"[^"]*")?\)/g)) {
    const src = match[1];
    if (src.startsWith('/images/')) return src;
  }
  return null;
}

function frontmatterValue(markdown, key) {
  const match = markdown.match(new RegExp(`^${key}:\\s*(.+)$`, 'm'));
  return match ? match[1].trim() : '';
}

async function main() {
  mkdirSync(OUT_DIR, { recursive: true });
  mkdirSync(join(OUT_DIR, 'blog'), { recursive: true });

  // 1. 默认图
  await sharp(BG)
    .extract({ left: 0, top: BG_TOP, width: 1920, height: BG_CROP_H })
    .resize(W, H)
    .jpeg({ quality: 82, mozjpeg: true })
    .toFile(join(OUT_DIR, 'default.jpg'));
  console.log(`[og] default.jpg ← ${BG}（top ${BG_TOP}，${W}×${H}）`);

  // 2. 每篇一张
  const manifest = {};
  let made = 0;
  let skipped = 0;

  for (const file of readdirSync(BLOG_DIR).sort()) {
    if (!file.endsWith('.md')) continue;
    const slug = file.slice(0, -3);
    const markdown = readFileSync(join(BLOG_DIR, file), 'utf8');
    if (frontmatterValue(markdown, 'draft') === 'true') continue;

    const source = firstLocalImage(markdown);
    if (!source) {
      skipped += 1;
      console.log(`[og] ${slug} 没有本地配图，用默认图`);
      continue;
    }

    const dest = join(OUT_DIR, 'blog', `${slug}.jpg`);
    // 配图多为 670px 宽，放大到 1200 会发虚，lanczos3 是 sharp 的默认核，够用；
    // 只补一点锐度，不加到会出光晕的程度。
    await sharp(join('public', source))
      .resize(W, H, { fit: 'cover', position: 'attention' })
      .sharpen({ sigma: 0.5 })
      .jpeg({ quality: 82, mozjpeg: true })
      .toFile(dest);
    manifest[slug] = `/og/blog/${slug}.jpg`;
    made += 1;
    console.log(`[og] ${slug}.jpg ← ${source}`);
  }

  writeFileSync(MANIFEST, `${JSON.stringify(manifest, null, 2)}\n`, 'utf8');
  console.log(`[og] 共 ${made} 篇有专属图，${skipped} 篇退默认；清单写入 ${MANIFEST}`);
}

await main();
