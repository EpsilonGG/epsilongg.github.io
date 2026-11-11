"""筛选页生成器：按钮文案 / 顺序 / 行为沿用旧稿，正文按正式版三栏输出。

规格（沿用已归档的 `archive/weekly_studio` 时代 `editor.html`）：
* 工具栏：输出新版周报(primary) / 导出 decisions.json / 恢复默认；输出区：复制正文
* 大单元：↑ ↓ 删除；小单元：源 ↑ ↓ 删除；看点 / 互动：已停用，只留查证
* 拖动排序（把手）、localStorage 保存决策、showSaveFilePicker 覆盖同一 md 文件
* 决策 schema 与旧稿同名同字段，额外保留归栏三值 column 信息
差异只在：`buildMarkdown` 输出 `## 新作 / ## 作品情报 / ## 业界动向`，
且展示栏目由 Python 预先算好（`item["display_column"]`），JS 只读不算。
"""
from __future__ import annotations

import json
from pathlib import Path

from .config import write_text

_CSS = """
:root{--bg:#fafafa;--card:#fff;--ink:#16181d;--muted:#6b7280;--line:#e3e5e9;--accent:#111827}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.75 -apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans CJK SC","Microsoft YaHei",sans-serif}
.wrap{max-width:1080px;margin:0 auto;padding:28px 20px 80px}
header{border-bottom:1px solid var(--line);padding-bottom:18px;margin-bottom:20px}
h1{font-size:24px;margin:0 0 6px}
.sub,.ws-meta{color:var(--muted);font-size:12px}
.badge{display:inline-block;border:1px solid var(--line);border-radius:6px;padding:2px 8px;font-size:12px;color:var(--muted);margin:8px 6px 0 0}
footer{color:var(--muted);font-size:12px;text-align:center;margin-top:26px}
code{background:#f1f2f4;border-radius:4px;padding:1px 5px;font-size:12px}
.ws-toolbar{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin:14px 0}
.ws-toolbar button{font:inherit;font-size:13px;border:1px solid var(--line,#e3e5e9);background:var(--card,#fff);color:var(--ink,#16181d);border-radius:6px;padding:5px 12px;cursor:pointer}
.ws-toolbar button:hover{border-color:var(--accent,#111827)}
.ws-toolbar button.primary{background:var(--accent,#111827);color:#fff;border-color:var(--accent,#111827)}
.ws-toolbar button.mini{padding:2px 8px;font-size:12px}
.ws-status{color:var(--muted,#6b7280);font-size:12px;margin-left:6px}
.ws-note{border-left:3px solid #9ca3af;padding:8px 12px;background:#f6f7f9;border-radius:0 6px 6px 0;font-size:13px;color:#374151;margin:12px 0}
.ws-h3{font-size:15px;margin:20px 0 10px;padding-bottom:8px;border-bottom:1px solid var(--line,#e3e5e9)}
.ws-unit{border:1px solid var(--line,#e3e5e9);border-radius:6px;margin:10px 0;background:#fcfcfd}
.ws-unit-head{display:flex;align-items:center;gap:10px;padding:9px 12px;border-bottom:1px solid var(--line,#e3e5e9)}
.ws-unit-head b{font-size:15px}
.ws-grip{cursor:grab;color:var(--muted,#6b7280);user-select:none;font-size:16px;line-height:1;padding:2px 4px;border-radius:4px}
.ws-grip:active{cursor:grabbing}
.ws-tools{margin-left:auto;display:flex;gap:6px;align-items:center;flex-wrap:wrap}
.ws-tools button{font:inherit;font-size:12px;border:1px solid var(--line,#e3e5e9);background:var(--card,#fff);color:var(--ink,#16181d);border-radius:6px;padding:2px 8px;cursor:pointer}
.ws-tools button:hover{border-color:var(--accent,#111827)}
.ws-tools button[data-act="src"]{border-style:dashed}
.ws-tools button[aria-expanded="true"]{background:#111827;color:#fff;border-color:#111827;border-style:solid}
.ws-items{padding:4px 12px 10px}
.ws-groups{padding:2px 8px 8px}
.ws-group{border:1px solid var(--line,#e3e5e9);border-radius:6px;margin:8px 0;background:#fff}
.ws-group-head{display:flex;align-items:center;gap:8px;padding:6px 10px;background:#f6f7f9;border-bottom:1px solid var(--line,#e3e5e9);border-radius:6px 6px 0 0;flex-wrap:wrap}
.ws-group-head b{font-size:13px}
.ws-group-col{font-size:11px;color:var(--muted,#6b7280);border:1px solid var(--line,#e3e5e9);border-radius:4px;padding:1px 6px;background:#fff}
.ws-group-head .ws-tools{margin-left:auto}
.ws-group-head button[data-act="switch"]{border-style:dashed}
.ws-group .ws-items{padding:2px 10px 8px}
.ws-item{display:flex;gap:10px;align-items:flex-start;border-top:1px dashed var(--line,#e3e5e9);padding:8px 0;flex-wrap:wrap}
.ws-item:first-child{border-top:0}
.ws-item .ws-body{flex:1;min-width:0;font-size:13px}
.ws-item .ws-body b{font-size:14px}
.ws-sentence{display:block;color:#374151;word-break:break-word}
.ws-lines{margin:4px 0 0;padding-left:18px;color:#374151}
.ws-lines li{margin:2px 0;word-break:break-word}
.ws-accounts{margin-top:4px;font-size:12px;color:#111827;background:#f6f7f9;border-left:2px solid #9ca3af;padding:2px 8px;border-radius:3px;word-break:break-word}
.ws-meta{color:var(--muted,#6b7280);font-size:11px;margin-top:2px}
.ws-src-panel{flex-basis:100%;border:1px solid var(--line,#e3e5e9);border-radius:6px;background:#fff;padding:8px 12px;margin:6px 0 2px}
.ws-src-title{font-size:12px;color:var(--muted,#6b7280);margin:8px 0 4px;font-weight:600}
.ws-clause{border-top:1px dashed var(--line,#e3e5e9);padding:6px 0;font-size:12px}
.ws-clause:first-of-type{border-top:0}
.ws-clause .ws-zh{font-size:13px;color:#16181d;margin:2px 0}
.ws-src{color:var(--muted,#6b7280);font-size:12px;word-break:break-all;margin-top:2px}
.ws-src a{color:#1d4ed8;text-decoration:none}
.ws-src a:hover{text-decoration:underline}
.ws-jp{color:#4b5563;font-size:12px;background:#f6f7f9;border-radius:4px;padding:4px 8px;margin-top:3px;word-break:break-word}
.ws-deleted{opacity:.45}
.ws-deleted .ws-body{text-decoration:line-through}
.ws-dragover{outline:2px dashed #6b7280;outline-offset:2px}
.ws-dragging{opacity:.35}
.ws-hl{border-top:1px dashed var(--line,#e3e5e9);padding:6px 0;display:flex;gap:10px;align-items:flex-start}
.ws-hl:first-child{border-top:0}
.ws-hl .ws-body{flex:1;min-width:0;font-size:13px}
.ws-hl .ws-day{color:var(--muted,#6b7280);font-size:12px;margin-right:6px;font-variant-numeric:tabular-nums}
.ws-details{border:1px solid var(--line,#e3e5e9);border-radius:6px;padding:8px 12px;margin:12px 0 0;background:#fcfcfd}
.ws-details summary{cursor:pointer;font-weight:600;font-size:13px}
.ws-details li{font-size:13px;margin:4px 0}
.ws-output pre{white-space:pre-wrap;word-break:break-word;background:#f6f7f9;border:1px solid var(--line,#e3e5e9);border-radius:6px;padding:14px;font:12px/1.7 ui-monospace,Consolas,monospace;max-height:560px;overflow:auto}
"""

_JS = r"""
(function(){
  'use strict';
  var DATA = JSON.parse(document.getElementById('ws-data').textContent);
  var ROOT = document.getElementById('ws-root');
  // 存储命名空间故意保留旧名 `weekly-v2-editor:`：改前缀会让浏览器里已有的
  // 未导出勾选全部失效。它只是 localStorage 的 key，不参与任何版本判定。
  var STORE = 'weekly-v2-editor:' + DATA.id + ':v' + (DATA.schema_version || 3);
  var status = document.getElementById('ws-status');
  var hlList = document.getElementById('ws-highlights');
  var dragging = null, draggingKind = null;
  var NAMES = DATA.account_names || {};
  var colBox = {};
  Array.prototype.forEach.call(ROOT.querySelectorAll('.ws-col'), function(box){
    colBox[box.dataset.column] = box;
  });
  var SWITCH = DATA.switch_columns || [];
  var SEC_COLS = DATA.section_columns || DATA.columns;
  var groupColumn = {}, savedState = null;
  function loadSaved(){ try { return JSON.parse(localStorage.getItem(STORE)||'null'); } catch(e){ return null; } }
  function applyBase(){
    savedState = loadSaved();
    var valid = !!(savedState && savedState.source === DATA.id);
    groupColumn = {};
    var src = (valid && savedState.group_column) ? savedState.group_column : (DATA.group_column || {});
    Object.keys(src || {}).forEach(function(k){ groupColumn[k] = src[k]; });
  }
  function itemRows(unit){ return Array.prototype.slice.call(unit.querySelectorAll('[data-row="item"]')); }
  function defaultDeleted(){
    var out = {items:{}, highlights:{}, interactions:{}};
    (DATA.sections||[]).forEach(function(s){ s.items.forEach(function(i){
      if(i.default_deleted) out.items[i.key]=1; }); });
    (DATA.highlights||[]).forEach(function(h){ if(h.default_deleted) out.highlights[h.key]=1; });
    (DATA.interactions||[]).forEach(function(x){ if(x.default_deleted) out.interactions[x.key]=1; });
    return out;
  }
  function effectiveColumn(gkey, base){
    var c = groupColumn[gkey] || base;
    return SEC_COLS.indexOf(c) >= 0 ? c : base;
  }
  function switchTarget(gkey, base){
    return effectiveColumn(gkey, base) === SWITCH[1] ? SWITCH[0] : SWITCH[1];
  }

  function handleOf(s){
    var m = /(?:x|twitter)\.com\/([A-Za-z0-9_]+)\/status/i.exec(String((s&&s.url)||''));
    if(m) return m[1].toLowerCase();
    var a = String((s&&s.author)||'').replace(/^@/,'').trim();
    return /^[A-Za-z0-9_]{1,15}$/.test(a) ? a.toLowerCase() : '';
  }
  function esc(s){ return String(s == null ? '' : s)
      .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
  function el(tag, cls, html){ var n=document.createElement(tag); if(cls) n.className=cls;
                               if(html!=null) n.innerHTML=html; return n; }
  function rowsIn(box, kind){ return Array.prototype.slice.call(
      box.querySelectorAll(':scope > [data-row="'+kind+'"]')); }
  function unitsIn(){ return Array.prototype.slice.call(
      ROOT.querySelectorAll('[data-row="section"]')); }
  function tools(acts){
    var box = el('span','ws-tools');
    acts.forEach(function(a){
      var b = el('button','mini',a[1]); b.type='button'; b.title=a[2]; b.dataset.act=a[0];
      if(a[0]==='src'){ b.setAttribute('aria-expanded','false'); }
      box.appendChild(b);
    });
    return box;
  }
  function srcPanel(it){
    var out = [];
    if(it.candidates && it.candidates.length){
      out.push('<div class="ws-src-title">候选分句（'+it.candidates.length+' 条，逐字取自日报）</div>');
      var groups = [], byCtx = {};
      it.candidates.forEach(function(c){
        var ctx = c.context || c.text;
        if(!byCtx[ctx]){ byCtx[ctx] = {ctx: ctx, items: []}; groups.push(byCtx[ctx]); }
        byCtx[ctx].items.push(c);
      });
      groups.forEach(function(g){
        out.push('<div class="ws-clause"><div class="ws-zh">'+esc(g.ctx)+'</div>');
        g.items.forEach(function(c){
          out.push('<div class="ws-meta">'+esc(c.clause_id)+' · '+esc(c.day)+
            (c.precision ? ' · M1 '+esc(c.precision) : '')+
            ' · 分句：'+esc(c.text)+
            ' · 出处：'+esc(c.sources.length ? c.sources.join(', ') : '（无出处）')+'</div>');
        });
        out.push('</div>');
      });
    }
    out.push('<div class="ws-src-title">情报源索引（'+(it.sources||[]).length+' 条，重复推文全部保留）</div>');
    if(it.sources && it.sources.length){
      it.sources.forEach(function(s){
        var h = handleOf(s), nm = (NAMES[h] || s.display_name || '');
        out.push('<div class="ws-src">'+esc(s.key)+' → '+
          (s.url ? '<a href="'+esc(s.url)+'" target="_blank" rel="noopener">'+esc(s.url)+'</a>' : '（URL 未解析）')+
          '（'+(nm ? esc(nm)+' · ' : '')+'@'+esc(h || s.author || '?')+
          (s.class ? ' · '+esc(s.class) : '')+(s.promoted ? ' · 转发提升' : '')+'）</div>');
        if(s.text) out.push('<div class="ws-jp">原文：'+esc(s.text)+'</div>');
      });
    } else {
      out.push('<div class="ws-src">（无出处链接）</div>');
    }
    return out.join('');
  }

  var itemOf = {};
  DATA.sections.forEach(function(s){ s.items.forEach(function(i){ itemOf[i.key]=i; }); });

  function render(){
    applyBase();
    Object.keys(colBox).forEach(function(k){ colBox[k].innerHTML=''; });
    DATA.sections.forEach(function(sec){
      var unit = el('div','ws-unit');
      unit.dataset.row='section'; unit.dataset.key=sec.key; unit.dataset.column=sec.column;
      var head = el('div','ws-unit-head');
      var grip = el('span','ws-grip','&#9947;'); grip.draggable=true; grip.title='拖动排序';
      head.appendChild(grip);
      head.appendChild(el('b','',esc(sec.label)));
      head.appendChild(el('span','ws-meta','（'+esc(sec.column)+'）'+
        (has(FMT.flat, sec.column) ? ' · 出稿按品牌铺平，不输出游戏小标题' : '')));
      head.appendChild(tools([['up','↑','上移'],['down','↓','下移'],
                              ['del','删除','从本期稿中剔除（可撤销）']]));
      unit.appendChild(head);
      var groups = el('div','ws-groups');
      var byGroup = {}, order = [];
      sec.items.forEach(function(it){
        var gk = it.group_key || ('g:fallback:'+it.key);
        if(!byGroup[gk]){ byGroup[gk] = {label: it.group_label || '未标注作品', items: []}; order.push(gk); }
        byGroup[gk].items.push(it);
      });
      order.forEach(function(gk){
        var grp = byGroup[gk];
        var gBox = el('div','ws-group');
        gBox.dataset.row='group'; gBox.dataset.key=gk; gBox.dataset.column=sec.column;
        var gHead = el('div','ws-group-head');
        gHead.appendChild(el('b','',esc(grp.label)));
        var colTag = el('span','ws-group-col','归栏 '+esc(effectiveColumn(gk, sec.column)));
        gHead.appendChild(colTag);
        if(grp.items[0] && grp.items[0].new_work){
          gHead.appendChild(el('span','ws-group-col','新作 · 出稿在第一栏'));
        }
        if(SWITCH.length >= 2){
          var sw = el('button','mini','→ '+esc(switchTarget(gk, sec.column)));
          sw.type='button'; sw.dataset.act='switch';
          sw.title='把该游戏整组小条目在「'+SWITCH.join(' / ')+'」之间切换（写入 decisions.group_column）';
          var tbox = el('span','ws-tools'); tbox.appendChild(sw); gHead.appendChild(tbox);
        }
        gBox.appendChild(gHead);
        var gItems = el('div','ws-items');
        grp.items.forEach(function(it){
          var row = el('div','ws-item');
          row.dataset.row='item'; row.dataset.key=it.key;
          var g = el('span','ws-grip','&#9947;'); g.draggable=true; g.title='拖动排序';
          row.appendChild(g);
          var body = el('div','ws-body');
          var meta = [];
          if(it.candidates && it.candidates.length) meta.push('候选分句 '+it.candidates.length+' 条');
          if(it.days && it.days.length) meta.push(it.days.length+' 天');
          meta.push('账号类 '+esc(it.account_class));
          if(it.default_deleted) meta.push(esc(it.default_reason||'默认规则')+' · 默认不入初稿');
          if(it.forced_column) meta.push('强制归 '+esc(it.forced_column));
          var accts = (it.accounts || []).map(function(a){
            return esc(a.name)+(a.mapped ? '' : '（名单外）')+' ['+esc(a.class)+']'; }).join('、');
          body.innerHTML =
            '<span class="ws-sentence">'+esc(it.sentence)+'</span>'+
            (accts ? '<div class="ws-accounts">来源账号：'+accts+'</div>' : '')+
            (meta.length ? '<div class="ws-meta">'+meta.join(' · ')+'</div>' : '');
          row.appendChild(body);
          row.appendChild(tools([['src','源','展开 / 收起候选分句与出处链接'],
                                 ['up','↑','上移'],['down','↓','下移'],
                                 ['del','删除','从本期稿中剔除（可撤销）']]));
          gItems.appendChild(row);
        });
        gBox.appendChild(gItems);
        groups.appendChild(gBox);
      });
      unit.appendChild(groups);
      (colBox[sec.column] || colBox[DATA.columns[0]]).appendChild(unit);
    });

    hlList.innerHTML = '';
    (DATA.highlights || []).forEach(function(h){
      var row = el('div','ws-hl');
      row.dataset.row='highlight'; row.dataset.key=h.key;
      var g = el('span','ws-grip','&#9947;'); g.draggable=true; g.title='拖动排序';
      row.appendChild(g);
      var body = el('div','ws-body');
      body.innerHTML = '<span class="ws-day">'+esc(h.day)+'</span>'+esc(h.text)+
        '<div class="ws-meta">归栏 → '+esc(h.column)+' · 账号类 '+esc(h.account_class)+'</div>';
      row.appendChild(body);
      row.appendChild(tools([['up','↑','上移'],['down','↓','下移'],
                             ['del','删除','从本期稿中剔除（可撤销）']]));
      hlList.appendChild(row);
    });

    var indList = document.getElementById('ws-interactions');
    indList.innerHTML = '';
    (DATA.interactions || []).forEach(function(it){
      var row = el('div','ws-hl');
      row.dataset.row='interaction'; row.dataset.key=it.key;
      var body = el('div','ws-body');
      body.innerHTML = '<span class="ws-day">'+esc(it.day||'')+'</span>'+esc(it.text)+
        '<div class="ws-meta">归栏 → '+esc(it.column)+' · 账号类 '+esc(it.account_class)+'</div>';
      row.appendChild(body);
      row.appendChild(tools([['src','源','展开该条的原推出处'],
                             ['del','删除','从本期稿中剔除（可撤销）']]));
      indList.appendChild(row);
    });
    if(!(DATA.interactions||[]).length){
      indList.innerHTML = '<div class="ws-meta">（无行业 / 动态条目）</div>';
    }

    var rep = document.getElementById('ws-repeats');
    var items = DATA.repeats || [];
    rep.innerHTML = '<summary>跨日重复扫描（'+items.length+' 组原推正文完全相同，只显示最新、源索引全留）</summary>' +
      (items.length ? '<ul>' + items.map(function(r){
          return '<li>'+esc(r.title)+'：<span class="ws-meta">'+esc((r.days||[]).join(', '))+
            ' · '+r.keys+' 键</span></li>';
        }).join('') + '</ul>'
        : '<p class="ws-meta">未发现重复。</p>');
    restore();
    say('已载入 '+DATA.sections.length+' 个大单元 / '+(DATA.highlights||[]).length+
        ' 条看点；按住把手拖动或点 ↑↓ 调序，点「删除」做筛选，点「源」看候选分句与出处。');
  }

  function decisions(){
    var ds=[], di=[], dhl=[], dind=[], so=[], io={}, ho=[], gc={};
    unitsIn().forEach(function(u){
      var key=u.dataset.key; so.push(key);
      if(u.classList.contains('ws-deleted')) ds.push(key);
      var order=[];
      itemRows(u).forEach(function(i){ order.push(i.dataset.key);
        if(i.classList.contains('ws-deleted')) di.push(i.dataset.key); });
      io[key]=order;
    });
    rowsIn(hlList,'highlight').forEach(function(h){ ho.push(h.dataset.key);
      if(h.classList.contains('ws-deleted')) dhl.push(h.dataset.key); });
    var indBox = document.getElementById('ws-interactions');
    rowsIn(indBox,'interaction').forEach(function(r){
      if(r.classList.contains('ws-deleted')) dind.push(r.dataset.key); });
    Object.keys(groupColumn).forEach(function(k){ gc[k]=groupColumn[k]; });
    return {schema_version:DATA.schema_version||7, generator:'weekly/selection/7',
            source:DATA.id, deleted_sections:ds, deleted_items:di, deleted_highlights:dhl,
            deleted_interactions:dind,
            section_order:so, item_order:io, highlight_order:ho, group_column:gc};
  }
  function save(){
    try { localStorage.setItem(STORE, JSON.stringify(decisions())); } catch(e) {}
  }
  function restore(){
    var d = defaultDeleted();
    var saved = savedState;
    var valid = !!(saved && saved.source === DATA.id);
    function setOf(list){ var o={}; (list||[]).forEach(function(k){ o[k]=1; }); return o; }
    var ds  = valid ? setOf(saved.deleted_sections)    : {};
    var di  = valid ? setOf(saved.deleted_items)       : d.items;
    var dhl = valid ? setOf(saved.deleted_highlights)  : d.highlights;
    var dind= valid ? setOf(saved.deleted_interactions): d.interactions;
    var byKey={};
    unitsIn().forEach(function(u){ byKey[u.dataset.key]=u;
      itemRows(u).forEach(function(i){ byKey[i.dataset.key]=i; }); });
    rowsIn(hlList,'highlight').forEach(function(h){ byKey[h.dataset.key]=h; });
    rowsIn(document.getElementById('ws-interactions'),'interaction').forEach(function(r){
      byKey[r.dataset.key]=r; });
    if(valid){
      (saved.section_order||[]).forEach(function(k){
        var u=byKey[k]; if(u && u.dataset.row==='section')
          (colBox[u.dataset.column]||colBox[DATA.columns[0]]).appendChild(u); });
      Object.keys(saved.item_order||{}).forEach(function(sk){
        (saved.item_order[sk]||[]).forEach(function(k){
          var row=byKey[k]; if(row && row.dataset.row==='item') row.parentElement.appendChild(row); });
      });
      (saved.highlight_order||[]).forEach(function(k){ if(byKey[k]) hlList.appendChild(byKey[k]); });
    }
    unitsIn().forEach(function(u){
      mark(u, !!ds[u.dataset.key]);
      itemRows(u).forEach(function(i){ mark(i, !!di[i.dataset.key]); });
    });
    rowsIn(hlList,'highlight').forEach(function(h){ mark(h, !!dhl[h.dataset.key]); });
    rowsIn(document.getElementById('ws-interactions'),'interaction').forEach(function(r){
      mark(r, !!dind[r.dataset.key]); });
  }
  function mark(row, on){
    row.classList.toggle('ws-deleted', on);
    var b=row.querySelector('button[data-act="del"]');
    if(b){ b.textContent=on?'恢复':'删除'; b.title=on?'恢复该条目':'从本期稿中剔除（可撤销）'; }
  }
  function say(text){ status.textContent=text; }

  var FMT={flat:[],official_first:[],official_no_prefix:[],official_space_prefix:[]};
  (function(){ var f=DATA.format||{}; Object.keys(FMT).forEach(function(k){
    if(f[k] instanceof Array) FMT[k]=f[k]; }); })();
  function has(list,c){ return list.indexOf(c)>=0; }
  function ordered(arr,c){
    if(!has(FMT.official_first,c)) return arr;
    var a=[],b=[]; arr.forEach(function(x){ (x.official?a:b).push(x); });
    return a.concat(b);
  }

  function buildMarkdown(d){
    var bySection={}, itOf={}, cols=DATA.columns;
    DATA.sections.forEach(function(s){ bySection[s.key]=s;
      s.items.forEach(function(i){ itOf[i.key]=i; }); });
    var ds={}, di={}, dhl={}, dind={}, gc={};
    (d.deleted_sections||[]).forEach(function(k){ds[k]=1;});
    (d.deleted_items||[]).forEach(function(k){di[k]=1;});
    (d.deleted_highlights||[]).forEach(function(k){dhl[k]=1;});
    (d.deleted_interactions||[]).forEach(function(k){dind[k]=1;});
    Object.keys(d.group_column||{}).forEach(function(k){
      if(cols.indexOf(d.group_column[k])>=0) gc[k]=d.group_column[k]; });
    var lines=[];
    lines.push('# '+DATA.title,'', '> '+DATA.stage);
    if(DATA.note) lines.push('> '+DATA.note);
    lines.push('', '**导语**：'+DATA.lead, '', '---', '');
    var buckets={}, counts={}, order={}, brandUrl={};
    cols.forEach(function(c){ buckets[c]={}; order[c]=[]; counts[c]={sections:0,items:0}; brandUrl[c]={}; });
    function register(column, brand, gkey, glabel){
      if(!buckets[column][brand]){ buckets[column][brand]={}; order[column].push(brand); }
      if(!buckets[column][brand][gkey]) buckets[column][brand][gkey]={label:glabel,lines:[]};
      return buckets[column][brand][gkey].lines;
    }
    // 品牌中标题挂官号主页链接：同一品牌在两栏各有一节，各算各的官号。
    function heading(column, brand){
      var u=brandUrl[column][brand];
      return u ? '### ['+brand+']('+u+')' : '### '+brand;
    }
    (d.section_order||[]).forEach(function(key){
      if(ds[key]) return;
      var sec=bySection[key]; if(!sec) return;
      ((d.item_order||{})[key]||[]).forEach(function(k){
        var it=itOf[k];
        if(di[k] || !it || !String(it.sentence||'').trim()) return;
        // 展示栏目由 Python 算好（品牌动向并入作品情报 + 新作整组上提），这里照读。
        var column=it.display_column||sec.column;
        if(cols.indexOf(column)<0) column=sec.column;
        var off=!!it.is_official;
        var pref=it.prefix_md||it.subject_prefix||'';
        var sent=it.sentence_md||it.sentence;
        // 新作是作品情报的子集，版式规则按作品情报读（与 render.line 同口径）。
        var ruleCol=column===cols[0]?cols[1]:column;
        var body;
        if(off && has(FMT.official_no_prefix,ruleCol)) body=sent;
        else if(off && has(FMT.official_space_prefix,ruleCol)) body=(pref?pref+' ':'')+sent;
        else body=(pref?pref+'：':'')+sent;
        register(column, sec.label, it.group_key, it.group_label)
          .push({text:'- '+body, official:off});
        counts[column].items++;
        if(sec.brand_url && !brandUrl[column][sec.label]) brandUrl[column][sec.label]=sec.brand_url;
      });
    });
    cols.forEach(function(c){
      var body=[];
      order[c].forEach(function(brand){
        body.push(heading(c,brand),''); counts[c].sections++;
        var groups=buckets[c][brand], gkeys=Object.keys(groups);
        gkeys.forEach(function(gk){
          body.push('#### '+groups[gk].label,'');
          ordered(groups[gk].lines,c).forEach(function(l){ body.push(l.text); });
          body.push('');
        });
      });
      while(body.length && body[body.length-1]==='') body.pop();
      // 空栏整节省略：没有条目就不写 `## ` 标题，与 Python 端同口径。
      if(body.length) lines=lines.concat(['## '+c,''],body,['']);
    });
    lines.push('---','',
      '> 本稿由周报选材输出：'+cols.filter(function(c){
        return counts[c].items>0;
      }).map(function(c){
        return c+' '+counts[c].sections+' 个品牌大单元 / '+counts[c].items+' 条';
      }).join('；')+'。候选分句与出处链接在选材区的「源」里，不写进正文。',
      '> 工作台选材稿；四套筛选的证据见 material.md 与 evidence/。对外正本由 weekly publish 出到 data/weekly/。','');
    return lines.join('\n');
  }

  function download(name, text, mime){
    var blob=new Blob([text],{type:mime||'text/plain;charset=utf-8'});
    var a=document.createElement('a');
    a.href=URL.createObjectURL(blob); a.download=name;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(function(){ URL.revokeObjectURL(a.href); }, 1500);
  }
  var lastDraft='';
  var draftHandle=null;
  function draftFileName(){
    var base=String(DATA.id||'weekly').replace(/[^\w\u4e00-\u9fa5\-]+/g,'-');
    return base+'-draft-selected.md';
  }
  function saveDraftFile(text){
    if(!window.showSaveFilePicker){ return Promise.resolve(false); }
    var chain = draftHandle ? Promise.resolve(draftHandle) : window.showSaveFilePicker({
      suggestedName: draftFileName(),
      types:[{description:'Markdown', accept:{'text/markdown':['.md']}}]
    });
    return chain.then(function(handle){
      draftHandle = handle;
      return handle.createWritable();
    }).then(function(writable){
      return writable.write(text).then(function(){ return writable.close(); });
    }).then(function(){ return true; }).catch(function(){ return false; });
  }

  ROOT.addEventListener('click', function(e){
    var btn=e.target.closest('button[data-act]'); if(!btn) return;
    var row=btn.closest('[data-row]'); if(!row) return;
    var act=btn.dataset.act;
    if(act==='switch'){
      var gk=row.dataset.key, base=row.dataset.column;
      var target=switchTarget(gk, base);
      groupColumn[gk]=target;
      var tag=row.querySelector('.ws-group-col');
      if(tag) tag.textContent='归栏 '+target;
      btn.textContent='→ '+switchTarget(gk, base);
      var title=row.querySelector('b');
      save();
      say('小标题「'+(title?title.textContent:'')+'」整组切到「'+target+'」；点「输出新版周报」后写入新稿。');
      return;
    }
    if(act==='del'){ mark(row, !row.classList.contains('ws-deleted')); }
    else if(act==='src'){
      var panel = row.querySelector('.ws-src-panel');
      if(!panel){
        var it = itemOf[row.dataset.key];
        if(!it && row.dataset.row === 'interaction'){
          var list2 = DATA.interactions || [];
          for(var i2=0;i2<list2.length;i2++){ if(list2[i2].key===row.dataset.key){ it=list2[i2]; break; } }
          if(it){ it = {label:'', sentence:it.text, draft:true, candidates:[],
                        sources:it.sources||[], accounts:[], days:[it.day||''],
                        statements_dropped:0, lines:[], line_subjects:[]}; }
        }
        if(!it) return;
        panel = el('div','ws-src-panel'); panel.hidden = true;
        panel.innerHTML = srcPanel(it);
        row.appendChild(panel);
      }
      panel.hidden = !panel.hidden;
      btn.setAttribute('aria-expanded', panel.hidden ? 'false' : 'true');
      btn.textContent = panel.hidden ? '源' : '收起';
      return;
    }
    else {
      var siblings=rowsIn(row.parentElement, row.dataset.row);
      var at=siblings.indexOf(row), to=at+(act==='up'?-1:1);
      if(to<0 || to>=siblings.length) return;
      if(act==='up') row.parentElement.insertBefore(row, siblings[to]);
      else row.parentElement.insertBefore(row, siblings[to].nextSibling);
    }
    save();
    var d=decisions();
    say('已更新：删除 '+d.deleted_sections.length+' 个大单元 / '+d.deleted_items.length+
        ' 个小单元 / '+d.deleted_highlights.length+' 条看点 / '+d.deleted_interactions.length+
        ' 条行业动态；顺序已保存。');
  });

  ROOT.addEventListener('dragstart', function(e){
    var grip=e.target.closest('.ws-grip'); if(!grip) { e.preventDefault(); return; }
    var row=grip.closest('[data-row]'); if(!row) return;
    dragging=row; draggingKind=row.dataset.row;
    row.classList.add('ws-dragging');
    e.dataTransfer.effectAllowed='move';
    e.dataTransfer.setData('text/plain', row.dataset.key);
  });
  ROOT.addEventListener('dragover', function(e){
    var target=e.target.closest('[data-row]');
    if(!dragging || !target || target===dragging || target.dataset.row!==draggingKind) return;
    if(draggingKind!=='section' && target.parentElement!==dragging.parentElement) return;
    if(draggingKind==='section' && target.dataset.column!==dragging.dataset.column) return;
    e.preventDefault();
    target.classList.add('ws-dragover');
  });
  ROOT.addEventListener('dragleave', function(e){
    var target=e.target.closest('[data-row]'); if(target) target.classList.remove('ws-dragover');
  });
  ROOT.addEventListener('drop', function(e){
    var target=e.target.closest('[data-row]');
    if(!dragging || !target || target===dragging || target.dataset.row!==draggingKind) return;
    if(draggingKind!=='section' && target.parentElement!==dragging.parentElement) return;
    if(draggingKind==='section' && target.dataset.column!==dragging.dataset.column) return;
    e.preventDefault();
    target.classList.remove('ws-dragover');
    var rect=target.getBoundingClientRect();
    var after=(e.clientY-rect.top)>rect.height/2;
    target.parentElement.insertBefore(dragging, after ? target.nextSibling : target);
    dragging.classList.remove('ws-dragging'); dragging=null;
    save(); say('顺序已保存。');
  });
  ROOT.addEventListener('dragend', function(){
    if(dragging) dragging.classList.remove('ws-dragging');
    dragging=null;
    Array.prototype.forEach.call(ROOT.querySelectorAll('.ws-dragover'),function(n){n.classList.remove('ws-dragover');});
  });

  document.getElementById('ws-out').addEventListener('click', function(){
    lastDraft=buildMarkdown(decisions());
    document.getElementById('ws-output-text').textContent=lastDraft;
    document.getElementById('ws-output-panel').hidden=false;
    document.getElementById('ws-output-panel').scrollIntoView({behavior:'smooth',block:'start'});
    var lines=lastDraft.split('\n').length;
    saveDraftFile(lastDraft).then(function(saved){
      if(saved){
        say('已输出新版周报：'+lines+' 行；已写入 '+draftFileName()+'（再次点选会覆盖同一文件）。');
      } else {
        download('draft-selected.md', lastDraft, 'text/markdown;charset=utf-8');
        say('已输出新版周报：'+lines+' 行；draft-selected.md 已下载。');
      }
    });
  });
  document.getElementById('ws-export').addEventListener('click', function(){
    download('decisions.json', JSON.stringify(decisions(),null,2), 'application/json;charset=utf-8');
    say('decisions.json 已下载；可用 python -m weekly_v2 apply-decisions 落成磁盘文件。');
  });
  document.getElementById('ws-copy').addEventListener('click', function(){
    if(!lastDraft){ say('请先点「输出新版周报」。'); return; }
    if(navigator.clipboard && navigator.clipboard.writeText){
      navigator.clipboard.writeText(lastDraft).then(function(){say('已复制。');},function(){say('复制失败，请手动选中文本。');});
    } else { say('浏览器不支持自动复制，请手动选中文本。'); }
  });
  document.getElementById('ws-reset').addEventListener('click', function(){
    try { localStorage.removeItem(STORE); } catch(e) {}
    render();
    document.getElementById('ws-output-panel').hidden=true;
    say('已恢复生成时的默认顺序与全部条目。');
  });

  render();
})();
"""


def render_html(data: dict, path: Path) -> str:
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    columns_html = "".join(
        f'<h3 class="ws-h3">{col}（归栏）</h3><div class="ws-col" data-column="{col}"></div>'
        for col in data.get("section_columns") or data["columns"]
    )
    column_note = " / ".join(data["columns"])
    switch_text = " / ".join(data.get("switch_columns") or [])
    badges = "".join(
        f'<span class="badge">{label}</span>' for label in (
            "四类筛选 + 三栏展示", "品牌动向并入作品情报", "新作整组提到第一栏", "官号条目前置",
            "未标注作品默认不入初稿", "名单外原推链接", "生日词默认不入初稿",
            "只读旁路", "日报正本只读", "状态只存本机浏览器",
            f"{len(data['issues'])} 期 Galgame 全集",
        )
    )
    html = (
        '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{data["title"]} · 周报选材</title><style>{_CSS}</style></head>'
        '<body><div class="wrap"><header><h1>周报选材</h1>'
        f'<div class="sub">{data["title"]} · 本地交互页 · 只读旁路</div>{badges}</header>'
        '<div class="ws" id="ws-root"><div class="ws-toolbar">'
        '<button id="ws-out" class="primary" type="button">输出新版周报</button>'
        '<button id="ws-export" type="button">导出 decisions.json</button>'
        '<button id="ws-reset" type="button">恢复默认</button>'
        '<span class="ws-status" id="ws-status"></span></div>'
        '<div class="ws-note">出稿层级：栏目（大标题）→ 品牌（中标题）→ 游戏（小标题）→ '
        '短横线后的小条目。正式版三栏＝新作 / 作品情报 / 业界动向：品牌动向并入作品情报，'
        '品牌级条目落在该品牌下的「品牌动向」小标题里；带新作标签的游戏整组提到第一栏。'
        '官号（manufacturer 自发布）条目只写正文、不写账号名或品牌名（品牌名已是中标题）；'
        '非官号保留「前缀：」，名单外账号用 <code>@handle</code> 并挂原推链接（URL 取自源索引，不拼造）。'
        '品牌大单元、小条目都能「删除」做筛选（可撤销）；「未标注作品」与生日词条目'
        '默认已勾删、点「恢复」即可入稿；按住左侧 &#9947; 拖动或点 ↑↓ 调序。'
        '点小条目的「源」展开候选分句与情报源索引（默认折叠，重复推文全部保留在索引里）。'
        '点「输出新版周报」得到筛选后的新稿，同时下载 <code>draft-selected.md</code>；'
        '导出 <code>decisions.json</code> 后可交给命令行落成文件。'
        f'初稿正文不带出处键；除名单外原推链接外不带链接。展示固定三栏：{column_note}。</div>'
        f'{columns_html}'
        '<h3 class="ws-h3">看点（已停用 · 不进稿，只留查证）</h3><div id="ws-highlights"></div>'
        '<details class="ws-details" id="ws-repeats"></details>'
        '<h3 class="ws-h3">行业 / 动态（已停用 · 不进稿，只留查证）</h3>'
        '<div id="ws-interactions"></div>'
        '<div class="ws-meta">这两块按 2026-11-10 裁决从周报里删除，数据保留在这里供查证；'
        '对它们点删除只影响 decisions.json，不再影响出稿。</div>'
        '<div class="ws-output" id="ws-output-panel" hidden><h3 class="ws-h3">新版周报（筛选稿）</h3>'
        '<div class="ws-toolbar"><button id="ws-copy" type="button">复制正文</button>'
        '<span class="ws-meta">正文不写出处键；名单外账号保留一条原推链接，官号条目不写账号名。</span></div>'
        '<pre id="ws-output-text"></pre></div></div>'
        f'<script id="ws-data" type="application/json">{payload}</script>'
        f'<script>{_JS}</script>'
        '<footer>weekly-v2 / editor · 全部产物位于 weekly_v2/out/，不是发布出口</footer>'
        '</div></body></html>'
    )
    write_text(Path(path), html)
    return html
