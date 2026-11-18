# 翻译与推送的默认工作流

[← 返回仓库首页](../README.md) ｜ [写作指南](blog-guide.md) ｜ [译文口径](translation-style.md) ｜ [项目说明](project.md)

这份文档只回答一件事：**拿到一篇外文报道，从抓原文到站点上线、再到 B 站专栏，默认按什么顺序做。**

格式细节（frontmatter、图注、脚注）在 [博客写作指南](blog-guide.md)；用词口径在 [译文口径](translation-style.md)。
这里是把两者串起来的那条线，加上 2026-11 那次「文章上线了但和 B 站版本对不上、图也没同步」之后补的检查点。

---

## 0. 一分钟版

```text
判定来源 → 抓原文（含图片 URL 与段序） → 同步图片 → 按已发布版本逐段落文本
      → 出席者/脚注 → 构建自查 → push_site.py 一次带上 md + 图 + manifest → B 站回填链接
```

| 步骤 | 一句话判据 |
| --- | --- |
| 来源 | 给的是 B 站链接 → `original`；其它网址 → `ai`（见 [blog-guide §2.1](blog-guide.md)） |
| 文本 | **以已经发出去的那一版为准**，不用早期草稿 |
| 图片 | 原文正文有几张，站点就要有几张，位置对齐原段序 |
| 推送 | 文章、图片目录、`src/data/image-manifest.json` 必须同一个 commit |

---

## 1. 先判定来源，`source` 跟着来源走

| 输入 | `source` | 说明 |
| --- | --- | --- |
| B 站链接（`bilibili.com` / `b23.tv`）的专栏 / opus / 动态 | 不写（默认 `original`） | 这批是自己译、自己发的，不打 AI 标 |
| 其它任何网址 | `ai` | 翻译这一步经过 AI，打标记做披露 |
| 用户直接粘一段中文长文 | 先问一句 | 草稿与已发布版本常常不是一个东西（见 §4） |

「除非额外说明」的意思是：用户在当次明确要求打标时才写 `source: ai`，并且开头引用块加一句 AI 参与说明。

---

## 2. 抓原文

### 2.1 普通网页

1. 找正文容器（`<article class="…body">`、`class="…content…"`）。
2. 按顺序取 `<figure>` 里的 `img`；`<iframe>` 不当图，按 [blog-guide §3.2](blog-guide.md) 用 `:::video` 搬。
3. 图片带桌面 UA + 原站 `Referer` 下载（防盗链站点不带就 403）；懒加载站点还要试 `data-src` / `data-original`。
4. 细节与远程图取舍见 [blog-guide §4.4 / §4.5](blog-guide.md)。

### 2.2 B 站专栏（opus）

opus 页是前端渲染的，正文不在 HTML 的可见文本里，藏在 `window.__INITIAL_STATE__` 的 JSON 中：

- 正文：`detail.modules[]` 里 `module_type == "MODULE_TYPE_CONTENT"` 的那一项，取 `module_content.paragraphs`。
- `para_type`：`1` 正文段、`2` 图、`3` 分隔线、`8` 标题（`heading.level` 1 是文章标题，站点已由 frontmatter 生成，丢弃）。
- 文字：`paragraphs[n].text.nodes[].word.words`；**发言人名的粗体**在 `word.style.bold`，转成 `**名字**`。
- 图片：`paragraphs[n].pic.pics[0].url`，`width` / `height` / `size` 一并带着，方便核对是否下载成功。

**不要直接打 API。** `api.bilibili.com/x/polymer/web-dynamic/v1/opus/detail?id=…` 会返回 `-352`（风控），页面内联的 JSON 反而是完整的。

```bash
# 1) 存页面
curl -sL -A "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131.0" \
     -H "Referer: https://www.bilibili.com/" \
     "https://www.bilibili.com/opus/<opus_id>" -o opus.html
```

```python
# 2) 解析（Windows 上用 C:/Users/.../Temp/opus.html 这种真实路径，别用 /tmp）
import io, json
s = io.open('opus.html', encoding='utf-8').read()
i = s.find('window.__INITIAL_STATE__=')
# 后面还跟着别的脚本，json.loads 会报 Extra data，必须用 raw_decode
d = json.JSONDecoder().raw_decode(s[i + len('window.__INITIAL_STATE__='):])[0]
paras = next(m for m in d['detail']['modules']
             if m['module_type'] == 'MODULE_TYPE_CONTENT')['module_content']['paragraphs']
```

---

## 3. 图片必须同步

**规则：原文正文里有的图，译文里要有，位置跟着原段序。** 只留一张题图是最容易偷的懒，也是读者最直接能看出来的缺失。

### 3.1 下载

B 站图片在 `i0.hdslb.com/bfs/new_dyn/…`，必须带 `Referer: https://www.bilibili.com/`，否则拿不到。页面上 `img` 标签里的 `@1416w_798h_1c` 只是显示尺寸后缀，**去掉后缀就是原图**。

**图注在 `pics[].comment` 里，不在 `alt` / `title`。** 这两个字段常年是 `None`，光看它们会误判成「原图没图注」；
`comment` 为空串才是真没有。神絵祭那批 18 张里有 7 张带 `comment`，5 张只是「画师＋『作品名』」（按 3.3 视同标题，不写）。

```bash
# URL 列表一行一个；注意 Windows 下写文件容易带 CRLF，先 tr 掉，否则 curl 静默失败
tr -d '\r' < urls.txt > urls2.txt
n=0; while read -r u; do n=$((n+1))
  curl -sS --max-time 90 -A "Mozilla/5.0 Chrome/131.0" \
       -H "Referer: https://www.bilibili.com/" "$u" -o "$(printf %02d $n).bin"
done < urls2.txt
```

### 3.2 落盘

编号即段序：`public/images/blog/<slug>/01.jpg`、`02.jpg`…

原图多是 PNG，动辄 5–7 MB，直接进仓库会把 `public/images` 撑爆。压到宽 ≤1600、质量 82 存成 jpg（站内源图统一是 jpg）：

```bash
node -e "const sharp=require('sharp');(async()=>{
  const m=await sharp(src).metadata(), w=Math.min(1600,m.width);
  await sharp(src).resize({width:w,withoutEnlargement:true})
    .jpeg({quality:82,mozjpeg:true}).toFile(out+'/'+n+'.jpg');
})()"
```

然后生成响应式变体，并**提交 manifest**：

```bash
node scripts/optimize_images.mjs          # 出 600/960/1600 webp + 写 src/data/image-manifest.json
```

### 3.3 图注

- **原图有图注才写**：照抄或翻译原图注。原图没有就省掉 `title` 参数，**不要自己形容画面**。
- 原图注只是**标题、文件名**，或「图像」「写真」这类无意义词 → 同样不写。
- 判断标准：这句话有没有告诉读者画面上是什么。只点名作品名不算。
- 不加 `▲`、不加「图：」前缀。
- **不在图注里断言作者**。图上确实有版权水印（`©夜ノみつき`、`アールビバン` 这类）时也不靠图注交代，
  图注只做原图注的搬运。

---

## 4. 文本以「已发布版本」为准

这是 2026-11-18 那次的直接教训：站点上线的是早期整理稿，B 站专栏发的是另一版——措辞、段合并、甚至小节名（`尾声` vs `活动结束`）都不一样，读者一眼能看出对不上。

所以：

1. **先确认哪一份是终版。** 用户给的是草稿、还是已经发出去的版本？不确定就问，别默认。
2. 站点正文**逐段照抄终版**，只做站点需要的格式转换（`##` 标题、`**人名**：`、段间空行、脚注），不改词。
3. 段序即图序：`PIC` 出现在哪一段之后，图就插在哪一段之后。
4. 文末版权行统一改成斜体一行。

自查办法：把站点正文去掉 Markdown 标记后与原文做字符级比对，差异应当只剩分隔线和你自己加的区块。

```python
import difflib
sm = difflib.SequenceMatcher(None, src_no_markup, md_no_markup, autojunk=False)
print([o for o in sm.get_opcodes() if o[0] != 'equal'])
```

---

## 5. 落地到站点

1. `src/content/blog/<英文短横线 slug>.md`，frontmatter：`title` / `description` / `pubDate` / `tags`（六选一），B 站来源不写 `source`。
2. 开头引用块：刊载出处（刊名、期号、日期、发行人、编辑人）→ 原载链接 → 版权提示 → 「本站仅作个人存档」。
3. 题图放引用块之后，随后 `## 出席者` 名单；每位画师一句定位，代表作与名词解释进脚注（`[^n]`），脚注渲染出来是文章末尾的「注释」。
4. 正文从 `##` 开始，一人一段，段间空行；场面提示（`（全场掌声）`）单独成行。

---

## 6. 构建自查

```bash
npm run build          # frontmatter / 图注 / 脚注有问题会在这里暴露
npm run check:prose    # 落单的 ** 与误渲染的 <del>
grep -c '<figure' dist/blog/<slug>/index.html      # 应等于插图数
grep -c 'footnote-ref' dist/blog/<slug>/index.html # 脚注有没有挂上
```

预期：`<figure>` 数 = 图片数，`<del>` = 0，`check:prose` 无报错。

---

## 7. 推送

```bash
python scripts/push_site.py -m "blog: <一句话说清改了什么>" \
  --path src/content/blog/<slug>.md \
  --path public/images/blog/<slug> \
  --path src/data/image-manifest.json
```

- **三类文件必须同一批**：只提交 md，线上就是 18 个 404。
- **必须带 `--path`**：工作区常备几十处 README / reports 的未提交改动，不带就会全卷进同一个 commit。
- 本机 push 走 `push_site.py` 的 askpass 流程；直接 `git push` 会被 `git-credential-manager` 卡住。

> 本机默认 `node` 版本可能低于 astro 7.4 要求的 22.23.4，构建前先
> `export PATH="/c/Program Files/nodejs:$PATH"`（系统 node 24）。构建末尾 astro 清
> `dist/.prerender/.vite` 会被沙箱的 safe-delete 拦一次，页面已经生成，不影响产物。

---

## 8. B 站与站点之间

- 两边**同一份文本、同一个图序**；站点只是加上了出席者、脚注、图注这些站内格式。
- B 站先发、站点后发时，把已发布链接回填进站点开头的引用块（`原载于 B 站专栏：…`）。
- 站点先发、B 站后发时，改稿只改一处，另一处必须同步——两份不一致比少发一篇更难看。

---

## 9. 这次之后要记住的

写进 `.workbuddy/memory/MEMORY.md` 的只有三条硬规则：

1. B 站来源不打 AI 标（除非当次另有说明）。
2. 原文的图必须同步，位置对齐段序；**图注只在原图有图注时写，没有就不写，不自己形容画面**。
3. 文本以已发布版本为准；站点正文与终版逐段一致。
