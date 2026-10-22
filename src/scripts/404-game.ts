/*
 * 404 页面小游戏 —— 跳跃跑酷彩蛋
 *
 * 基于 Pixel Horse Runner 修改集成：
 *   原作者 : chigerartem
 *   源码   : https://github.com/chigerartem/pixel-horse-runner
 *   许可证 : MIT  (Copyright (c) 2026 chigerartem)
 *
 * 相对原作的修改点（仅改外围行为，未重写绘制引擎）：
 *   - 状态机保持 INTRO / PLAY / OVER；待机(INTRO)与结束(OVER)不再持续运行
 *     requestAnimationFrame 循环，仅在游戏进行(PLAY)时运行，减轻待机负担。
 *   - 页面不可见(visibilitychange)时暂停循环，可见且处于 PLAY 时恢复。
 *   - 键盘输入只在「非编辑元素、非链接/按钮」上生效，避免劫持页面滚动与表单输入。
 *   - 增加指针(鼠标 / 触摸)开始与跳跃支持，移动端可点击游玩。
 *   - 绘制颜色改为读取站点浅/深主题的设计变量，与主页黑白灰风格协调。
 *   - 启动 / 结束提示与最高分标签中文化。
 *   - 为 Canvas 增加 role="img" 与 aria-label，Canvas 不可用时 404 文本与导航仍正常。
 */

(() => {
  'use strict';

  const canvas = document.getElementById('dino-game') as HTMLCanvasElement | null;
  // 防御：避免开发模式热更新重复初始化；Canvas 不可用时直接退出，保留原始 404 文本与导航。
  if (!canvas || canvas.dataset.dinoReady === '1') return;
  const ctx = canvas.getContext('2d');
  if (!ctx) return;
  canvas.dataset.dinoReady = '1';

  const W = canvas.width; // 800
  const H = canvas.height; // 300
  const PIXEL = 2;
  const GROUND_Y = 240;

  // 颜色随主题读取；默认回退为灰阶，保证浅/深主题都清晰可见。
  let COLOR = '#555555';
  let COLOR_LIGHT = '#767676';
  // 等宽字体栈，包含中文回退，保证「按空格开始」等中文提示可正常渲染。
  const FONT_STACK = 'ui-monospace, "Courier New", "PingFang SC", "Microsoft YaHei", monospace';

  function readThemeColors(): void {
    const cs = getComputedStyle(document.documentElement);
    const main = cs.getPropertyValue('--color-text-secondary').trim();
    const light = cs.getPropertyValue('--color-text-muted').trim();
    if (main) COLOR = main;
    if (light) COLOR_LIGHT = light;
  }

  // ------------ Pixel sprites ------------
  // 'X' = 实心像素，'.' = 空。每个精灵像素在画布上的真实尺寸 = PIXEL (2)

  // 马 - 奔跑帧 A（前腿向前，后腿向后）
  const HORSE_RUN_A = [
    '..........................',
    '.......................XXX',
    '......................XXXX',
    '.......................XXX',
    '.X.....................XXXX',
    '.XX...................XXXXX',
    '.XXX................XXXXX..',
    '.XXXX..............XXXXX...',
    '..XXXX.........XXXXXXXX....',
    '...XXXXXXXXXXXXXXXXXXXX....',
    '...XXXXXXXXXXXXXXXXXXX.....',
    '....XXXXXXXXXXXXXXXXX......',
    '....XXXXXXXXXXXXXXXXX......',
    '.....XX..XX....XX..XX......',
    '.....XX..XX....XX..XX......',
    '......X..X......X..XX......',
    '......X..X......X..X.......',
    '......X..X......X..X.......',
    '......X..X......X..X.......',
    '.....XX..X......X..X.......',
    '....XXX..XX....XX..XXX.....',
  ];

  // 马 - 奔跑帧 B（腿部姿势不同）
  const HORSE_RUN_B = [
    '..........................',
    '.......................XXX',
    '......................XXXX',
    '.......................XXX',
    '.X.....................XXXX',
    '.XX...................XXXXX',
    '.XXX................XXXXX..',
    '.XXXX..............XXXXX...',
    '..XXXX.........XXXXXXXX....',
    '...XXXXXXXXXXXXXXXXXXXX....',
    '...XXXXXXXXXXXXXXXXXXX.....',
    '....XXXXXXXXXXXXXXXXX......',
    '....XXXXXXXXXXXXXXXXX......',
    '.....XX..X......X..XX......',
    '......X..X......X..XX......',
    '......X..XX....XX..X.......',
    '......X..XX....XX..X.......',
    '.....XX...X....X...X.......',
    '....XXX...X....X...XX......',
    '...XXX....X....X...XXX.....',
    '...XX.....XX..XX....XX.....',
  ];

  // 马 - 跳跃（腿部收起，身体拉长）
  const HORSE_JUMP = [
    '..........................',
    '.......................XXX',
    '......................XXXX',
    '.......................XXX',
    '.X.....................XXXX',
    '.XX...................XXXXX',
    '.XXX................XXXXX..',
    '.XXXX..............XXXXX...',
    '..XXXX.........XXXXXXXX....',
    '...XXXXXXXXXXXXXXXXXXXX....',
    '...XXXXXXXXXXXXXXXXXXX.....',
    '....XXXXXXXXXXXXXXXXX......',
    '....XXXXXXXXXXXXXXXXX......',
    '.....XXXX...XX...XXXX......',
    '......XXX..XXXX..XXX.......',
    '.......XXXXX..XXXXX........',
    '..........................',
    '..........................',
    '..........................',
    '..........................',
    '..........................',
  ];

  // 马 - 倒地（眼睛处为 X）
  const HORSE_DEAD = [
    '..........................',
    '.......................XXX',
    '......................X.XX',
    '.......................X.X',
    '.X.....................XXXX',
    '.XX...................XXXXX',
    '.XXX................XXXXX..',
    '.XXXX..............XXXXX...',
    '..XXXX.........XXXXXXXX....',
    '...XXXXXXXXXXXXXXXXXXXX....',
    '...XXXXXXXXXXXXXXXXXXX.....',
    '....XXXXXXXXXXXXXXXXX......',
    '....XXXXXXXXXXXXXXXXX......',
    '.....XX..XX....XX..XX......',
    '.....XX..XX....XX..XX......',
    '......X..X......X..XX......',
    '......X..X......X..X.......',
    '......X..X......X..X.......',
    '......X..X......X..X.......',
    '.....XX..X......X..X.......',
    '....XXX..XX....XX..XXX.....',
  ];

  // 马 - 下蹲（身体压低，头颈前伸）
  const HORSE_DUCK_A = [
    '..........................',
    '..........................',
    '..........................',
    '..........................',
    '..........................',
    '..........................',
    '..........................',
    '..........................',
    '..........................',
    '.X.....................XXX',
    '.XX...................XXXX',
    '.XXX.................XXXX.',
    '.XXXX..............XXXXX..',
    '..XXXXXXXXXXXXXXXXXXXXX...',
    '..XXXXXXXXXXXXXXXXXXXXX...',
    '...XXXXXXXXXXXXXXXXXXX....',
    '....XX..XX....XX..XX......',
    '....X...X......X...X......',
    '....X...X......X...X......',
    '...XX...X......X...XX.....',
    '...XX...XX....XX...XX.....',
  ];

  const HORSE_DUCK_B = [
    '..........................',
    '..........................',
    '..........................',
    '..........................',
    '..........................',
    '..........................',
    '..........................',
    '..........................',
    '..........................',
    '.X.....................XXX',
    '.XX...................XXXX',
    '.XXX.................XXXX.',
    '.XXXX..............XXXXX..',
    '..XXXXXXXXXXXXXXXXXXXXX...',
    '..XXXXXXXXXXXXXXXXXXXXX...',
    '...XXXXXXXXXXXXXXXXXXX....',
    '....X...X......X...X......',
    '....X...XX....XX...X......',
    '...XX...XX....XX...XX.....',
    '..XXX....X....X....XXX....',
    '..XX.....XX..XX.....XX....',
  ];

  // 小障碍 - 栏架（12×14 掩码 → 24×28 像素）
  const BARRIER_S = [
    '..XX....XX..',
    '..XX....XX..',
    '..XX....XX..',
    'XXXXXXXXXXXX',
    'XXXXXXXXXXXX',
    '..XX....XX..',
    '..XX....XX..',
    '..XX....XX..',
    'XXXXXXXXXXXX',
    'XXXXXXXXXXXX',
    '..XX....XX..',
    '..XX....XX..',
    '..XX....XX..',
    '..XX....XX..',
  ];

  // 大障碍 - 栏架（14×18 掩码 → 28×36 像素）
  const BARRIER_L = [
    '..XX......XX..',
    '..XX......XX..',
    'XXXXXXXXXXXXXX',
    'XXXXXXXXXXXXXX',
    '..XX......XX..',
    '..XX......XX..',
    'XXXXXXXXXXXXXX',
    'XXXXXXXXXXXXXX',
    '..XX......XX..',
    '..XX......XX..',
    '..XX......XX..',
    'XXXXXXXXXXXXXX',
    'XXXXXXXXXXXXXX',
    '..XX......XX..',
    '..XX......XX..',
    '..XX......XX..',
    '..XX......XX..',
    '..XX......XX..',
  ];

  // 鸟 - 两帧（18×10 掩码 → 36×20 像素）
  const BIRD_A = [ // 翅膀向上
    '...X..............',
    '...XX.............',
    '...XXX............',
    '...XXXX..XXXXX....',
    'XXXXXXXXXXXXXXXX..',
    '.XXXXXXXXXXXXX....',
    '...XXXXXXXX.......',
    '.....XXXX.........',
    '......X...........',
    '..................',
  ];

  const BIRD_B = [ // 翅膀向下
    '..................',
    '..................',
    '........XXXX......',
    '.....XXXXXXXXX....',
    'XXXXXXXXXXXXXXXX..',
    'XXXXXXXXXXXXX.....',
    '..XXXXXXXXX.......',
    '..XXXXXXX.........',
    '...XXXX...........',
    '.....X............',
  ];

  // 云 - 14×6
  const CLOUD = [
    '....XXXXX.....',
    '..XXXXXXXXXX..',
    '.XXXXXXXXXXXX.',
    'XXXXXXXXXXXXXX',
    '.XXXXXXXXXXXX.',
    '...XXXXXXXX...',
  ];

  function drawPixels(mask: string[], x: number, y: number, scale = PIXEL): void {
    for (let r = 0; r < mask.length; r++) {
      const row = mask[r];
      for (let c = 0; c < row.length; c++) {
        if (row[c] === 'X') {
          ctx!.fillRect(x + c * scale, y + r * scale, scale, scale);
        }
      }
    }
  }

  // ------------ Game state ------------
  const STATE = { INTRO: 0, PLAY: 1, OVER: 2 } as const;
  let state: number = STATE.INTRO;

  let score = 0;
  let hi = parseInt(localStorage.getItem('dinoRunnerHi') || '0', 10);
  let isNewRecord = false;

  const SPEED_START = 6;
  const SPEED_MAX = 13;
  const SPEED_ACCEL = 0.0012;
  let speed = SPEED_START;

  const GRAVITY = 0.62;
  const JUMP_V = -11.5;
  const JUMP_HOLD_BONUS = -0.35;

  const HORSE_W = 26 * PIXEL; // 52
  const HORSE_H = 21 * PIXEL; // 42

  const horse = {
    x: 60,
    y: GROUND_Y - HORSE_H,
    vy: 0,
    grounded: true,
    ducking: false,
    frame: 0,
    holdingJump: false,
  };

  let obstacles: Array<{
    type: string;
    x: number;
    y: number;
    w: number;
    h: number;
    frame?: number;
  }> = [];
  let clouds: Array<{ x: number; y: number; speed: number }> = [];
  const groundDecor: Array<{ x: number; offsetY: number; width: number }> = [];
  let groundOffset = 0;
  let frameCounter = 0;
  let spawnTimer = 80;
  let scoreSubcounter = 0;
  let flashTimer = 0;

  // 地面装饰 —— 随机短划痕
  for (let i = 0; i < 100; i++) {
    groundDecor.push({
      x: Math.random() * W * 2,
      offsetY: Math.random() < 0.5 ? 6 : 12,
      width: 4 + Math.floor(Math.random() * 8),
    });
  }

  // 云 —— 初始散布
  for (let i = 0; i < 3; i++) {
    clouds.push({
      x: Math.random() * W,
      y: 30 + Math.random() * 80,
      speed: 0.5 + Math.random() * 0.6,
    });
  }

  // ------------ Spawning ------------
  function spawnObstacle(): void {
    const r = Math.random();
    let o: { type: string; x: number; y: number; w: number; h: number; frame?: number };
    if (r < 0.5) {
      const w = BARRIER_S[0].length * PIXEL;
      const h = BARRIER_S.length * PIXEL;
      o = { type: 'barrier_s', x: W + 10, y: GROUND_Y - h, w, h };
    } else if (r < 0.72) {
      const w = BARRIER_L[0].length * PIXEL;
      const h = BARRIER_L.length * PIXEL;
      o = { type: 'barrier_l', x: W + 10, y: GROUND_Y - h, w, h };
    } else if (r < 0.88) {
      const w = BIRD_A[0].length * PIXEL;
      const h = BIRD_A.length * PIXEL;
      o = { type: 'bird_low', x: W + 10, y: GROUND_Y - 28, w, h, frame: 0 };
    } else {
      const w = BIRD_A[0].length * PIXEL;
      const h = BIRD_A.length * PIXEL;
      o = { type: 'bird_high', x: W + 10, y: GROUND_Y - HORSE_H + 2, w, h, frame: 0 };
    }
    obstacles.push(o);
  }

  function spawnCloud(): void {
    clouds.push({
      x: W + 20,
      y: 20 + Math.random() * 100,
      speed: 0.5 + Math.random() * 0.6,
    });
  }

  // ------------ Input helpers ------------
  // 不劫持输入框、文本域、下拉框，以及链接 / 按钮（保留其原生空格/回车行为）。
  function isInteractiveTarget(target: EventTarget | null): boolean {
    const el = target as HTMLElement | null;
    if (!el || !el.tagName) return false;
    const tag = el.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || tag === 'BUTTON' || tag === 'A') {
      return true;
    }
    if (el.isContentEditable) return true;
    return false;
  }

  function jump(): void {
    if (!horse.grounded) return;
    horse.vy = JUMP_V;
    horse.grounded = false;
    horse.holdingJump = true;
    horse.ducking = false;
  }

  function startGame(): void {
    state = STATE.PLAY;
    startLoop();
  }

  function reset(): void {
    score = 0;
    speed = SPEED_START;
    obstacles = [];
    horse.y = GROUND_Y - HORSE_H;
    horse.vy = 0;
    horse.grounded = true;
    horse.ducking = false;
    horse.frame = 0;
    frameCounter = 0;
    spawnTimer = 80;
    flashTimer = 0;
    isNewRecord = false;
  }

  function gameOver(): void {
    state = STATE.OVER;
    stopLoop();
    if (score > hi) {
      hi = score;
      localStorage.setItem('dinoRunnerHi', hi.toString());
      isNewRecord = true;
    }
    render(); // 结束画面只需绘制一次
  }

  // ------------ Update ------------
  function update(): void {
    if (state !== STATE.PLAY) return;

    frameCounter++;

    speed = Math.min(SPEED_MAX, SPEED_START + frameCounter * SPEED_ACCEL);

    scoreSubcounter++;
    if (scoreSubcounter >= 6) {
      scoreSubcounter = 0;
      score++;
      if (score > 0 && score % 100 === 0) {
        flashTimer = 24;
      }
    }
    if (flashTimer > 0) flashTimer--;

    if (horse.holdingJump && horse.vy < 0 && horse.vy > -14) {
      horse.vy += JUMP_HOLD_BONUS;
    }
    horse.vy += GRAVITY;
    horse.y += horse.vy;
    if (horse.y >= GROUND_Y - HORSE_H) {
      horse.y = GROUND_Y - HORSE_H;
      horse.vy = 0;
      horse.grounded = true;
    }

    if (horse.grounded && frameCounter % 6 === 0) {
      horse.frame = 1 - horse.frame;
    }

    groundOffset = (groundOffset + speed) % (W * 2);

    spawnTimer--;
    if (spawnTimer <= 0) {
      const last = obstacles[obstacles.length - 1];
      const minGap = 220 + Math.random() * 120;
      if (!last || W - last.x > minGap) {
        spawnObstacle();
      }
      const base = 80 * (SPEED_START / speed);
      spawnTimer = Math.floor(base + Math.random() * 60);
    }

    if (Math.random() < 0.004 && clouds.length < 4) {
      spawnCloud();
    }

    for (const o of obstacles) {
      o.x -= speed;
      if (o.type.startsWith('bird') && frameCounter % 8 === 0) {
        o.frame = 1 - (o.frame ?? 0);
      }
    }
    obstacles = obstacles.filter((o) => o.x + o.w > 0);

    for (const c of clouds) c.x -= c.speed;
    clouds = clouds.filter((c) => c.x + 14 * PIXEL > 0);

    const hb = horseHitbox();
    for (const o of obstacles) {
      const ob = obstacleHitbox(o);
      if (aabb(hb, ob)) {
        gameOver();
        break;
      }
    }
  }

  function horseHitbox(): { x: number; y: number; w: number; h: number } {
    if (horse.ducking && horse.grounded) {
      return {
        x: horse.x + 8,
        y: horse.y + 18 * PIXEL,
        w: HORSE_W - 16,
        h: 3 * PIXEL,
      };
    }
    return {
      x: horse.x + 6,
      y: horse.y + 4 * PIXEL,
      w: HORSE_W - 14,
      h: HORSE_H - 6 * PIXEL,
    };
  }

  function obstacleHitbox(o: { x: number; y: number; w: number; h: number }): {
    x: number;
    y: number;
    w: number;
    h: number;
  } {
    const inset = 4;
    return {
      x: o.x + inset,
      y: o.y + inset,
      w: o.w - inset * 2,
      h: o.h - inset * 2,
    };
  }

  function aabb(a: { x: number; y: number; w: number; h: number }, b: { x: number; y: number; w: number; h: number }): boolean {
    return a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
  }

  // ------------ Render ------------
  function render(): void {
    ctx!.clearRect(0, 0, W, H);
    ctx!.fillStyle = COLOR;

    ctx!.fillStyle = COLOR_LIGHT;
    for (const c of clouds) {
      drawPixels(CLOUD, c.x, c.y);
    }

    ctx!.fillStyle = COLOR;
    ctx!.fillRect(0, GROUND_Y, W, 2);

    for (const d of groundDecor) {
      const x = (((d.x - groundOffset) % (W * 2)) + W * 2) % (W * 2);
      if (x < W) {
        ctx!.fillRect(x, GROUND_Y + d.offsetY, d.width, 2);
      }
    }

    for (const o of obstacles) {
      if (o.type === 'barrier_s') {
        drawPixels(BARRIER_S, o.x, o.y);
      } else if (o.type === 'barrier_l') {
        drawPixels(BARRIER_L, o.x, o.y);
      } else {
        const mask = (o.frame ?? 0) === 0 ? BIRD_A : BIRD_B;
        drawPixels(mask, o.x, o.y);
      }
    }

    let horseMask: string[];
    if (state === STATE.OVER) {
      horseMask = HORSE_DEAD;
    } else if (!horse.grounded) {
      horseMask = HORSE_JUMP;
    } else if (horse.ducking && state === STATE.PLAY) {
      horseMask = (horse.frame === 0) ? HORSE_DUCK_A : HORSE_DUCK_B;
    } else if (state === STATE.PLAY) {
      horseMask = (horse.frame === 0) ? HORSE_RUN_A : HORSE_RUN_B;
    } else {
      horseMask = HORSE_RUN_A;
    }
    drawPixels(horseMask, horse.x, horse.y);

    ctx!.font = `bold 18px ${FONT_STACK}`;
    ctx!.fillStyle = COLOR;
    ctx!.textAlign = 'right';
    const scoreStr = String(score).padStart(5, '0');
    const hiStr = '最高 ' + String(hi).padStart(5, '0');
    const blink = flashTimer > 0 && Math.floor(flashTimer / 4) % 2 === 0;
    if (!blink && hi > 0) ctx!.fillText(hiStr, W - 110, 36);
    ctx!.fillText(scoreStr, W - 20, 36);
    ctx!.textAlign = 'left';

    if (state === STATE.INTRO) {
      ctx!.textAlign = 'center';
      ctx!.font = `bold 22px ${FONT_STACK}`;
      ctx!.fillText('按空格或点击开始游戏', W / 2, 130);
      ctx!.textAlign = 'left';
    }
    if (state === STATE.OVER) {
      ctx!.textAlign = 'center';
      ctx!.font = `bold 26px ${FONT_STACK}`;
      ctx!.fillText('游戏结束', W / 2, 110);
      ctx!.font = `bold 14px ${FONT_STACK}`;
      ctx!.fillText('按空格重新开始', W / 2, 140);
      if (isNewRecord) {
        ctx!.fillText('★ 新纪录 ★', W / 2, 166);
      }
      ctx!.textAlign = 'left';
    }
  }

  // ------------ Main loop (只在 PLAY 运行) ------------
  let rafId: number | null = null;
  let running = false;

  function startLoop(): void {
    if (running) return;
    running = true;
    rafId = requestAnimationFrame(tick);
  }

  function stopLoop(): void {
    running = false;
    if (rafId !== null) {
      cancelAnimationFrame(rafId);
      rafId = null;
    }
  }

  function tick(): void {
    if (!running) return;
    update();
    render();
    // 游戏结束后 update() 内会调用 gameOver() 停掉循环，这里不再续帧
    if (state === STATE.PLAY && running) {
      rafId = requestAnimationFrame(tick);
    }
  }

  // ------------ Listeners ------------
  window.addEventListener('keydown', (e: KeyboardEvent) => {
    if (e.code !== 'Space' && e.code !== 'ArrowUp' && e.code !== 'ArrowDown') return;
    // 不劫持编辑 / 链接 / 按钮等元素上的按键
    if (isInteractiveTarget(e.target)) return;
    // 仅对游戏用到的按键阻止默认行为（避免空格滚动页面、方向键滚动）
    if (e.code === 'Space' || e.code === 'ArrowUp') {
      e.preventDefault();
    } else if (e.code === 'ArrowDown' && state === STATE.PLAY) {
      e.preventDefault();
    }
    if (e.repeat) return;

    if (state === STATE.INTRO) {
      if (e.code === 'Space' || e.code === 'ArrowUp') startGame();
      return;
    }
    if (state === STATE.OVER) {
      if (e.code === 'Space' || e.code === 'ArrowUp') {
        reset();
        startGame();
      }
      return;
    }
    // PLAY
    if ((e.code === 'Space' || e.code === 'ArrowUp')) {
      jump();
    }
    if (e.code === 'ArrowDown') {
      horse.ducking = true;
      if (!horse.grounded) {
        horse.vy = Math.max(horse.vy + 4, 6);
      }
    }
  });

  window.addEventListener('keyup', (e: KeyboardEvent) => {
    if (e.code === 'Space' || e.code === 'ArrowUp') {
      horse.holdingJump = false;
    }
    if (e.code === 'ArrowDown') {
      horse.ducking = false;
    }
  });

  // 指针（鼠标 / 触摸）开始与跳跃
  canvas.addEventListener('pointerdown', (e: PointerEvent) => {
    e.preventDefault();
    if (state === STATE.INTRO) {
      startGame();
      return;
    }
    if (state === STATE.OVER) {
      reset();
      startGame();
      return;
    }
    jump();
  });

  // 页面不可见时暂停，可见且进行中时恢复
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
      stopLoop();
    } else if (state === STATE.PLAY) {
      startLoop();
    }
  });

  // 主题切换时重绘当前帧（待机 / 结束为静态，需手动重绘）
  const themeObserver = new MutationObserver(() => {
    readThemeColors();
    if (!running) render();
  });
  themeObserver.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ['data-theme'],
  });

  // ------------ Boot（待机，不自动运行循环） ------------
  readThemeColors();
  render(); // 静态绘制待机画面一次
})();
