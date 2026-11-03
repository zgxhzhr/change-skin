# 异世界商城 · Change Skin

一个纯静态的二次元幻想主题商城演示页，核心看点是**同一套页面结构下的多套完全不同的视觉风格**，以及可实时切换的 5 色主题系统。

不含构建工具，无后端依赖，双击 `index.html` 即可运行。

## 功能

**多套并行视觉风格**（右上角切换，选择记入 localStorage）

| 风格 | 视觉方向 |
|---|---|
| 漫画 | 网点纸底 + 粗黑描边 + 硬边投影 + 速度线 |
| 杂志 | 12 列错位编排 + 超大衬线标题 + 打破规整网格 |
| 扭蛋 | 塑料金属材质 + 机器按键 + 货架陈列 |
| 书脊 | **结构型**：左侧 sticky 书脊跨满全页，banner 与 hero 同格叠放，商品为价目台账 |

**5 色主题系统**：炽热红 / 森绿 / 深空蓝 / 活力橙 / 紫晶，切换时所有风格同步换色。

**技术演示元素**

- 三级下拉菜单（支持移动端汉堡菜单展开）
- Banner 轮播（自动播放、悬停暂停、箭头与圆点导航）
- 图片走马灯（横向无缝滚动，悬停暂停）
- 内容标签栏（全部 / 最新上架 / 热销排行 / 限时特惠）
- 4 个模态弹窗（主题确认、图片预览、联系表单、结算表单）
- 响应式布局 + 竖屏调试模式

**可访问性**

- 键盘焦点环（`:focus-visible`）
- 跳转链接（skip link）
- 支持 `prefers-reduced-motion`
- 深色风格使用高对比焦点色

## URL 参数

便于分享和调试特定组合：

```
?visual=manga|editorial|gacha|spine   选择视觉风格
?theme=red|green|blue|orange|purple             选择配色主题
```

例如：`index.html?visual=spine&theme=blue`

## 本地运行

需要一个静态服务器（直接双击 `file://` 打开也可以，但推荐用服务器避免缓存问题）：

```bash
python -m http.server 8777
```

然后访问 `http://127.0.0.1:8777/index.html`。

修改 CSS/JS 后如果页面没更新，按 `Ctrl+Shift+R` 强制刷新，或递增 `index.html` 里资源引用的 `?v=` 版本号。

## 目录结构

```
.
├── index.html
├── css/
│   ├── style.css              基础布局与交互样式
│   ├── modal.css              弹窗
│   ├── banner.css             轮播
│   ├── visual-manga.css       风格：漫画分镜
│   ├── visual-stationery.css  风格：手帐文具
│   ├── visual-editorial.css   风格：编辑排版
│   ├── visual-gacha.css       风格：扭蛋商店
│   └── visual-flow.css        通用层：消除区块割裂感
├── js/
│   ├── main.js                交互主逻辑
│   ├── banner-carousel.js     轮播实现
│   └── mulModal.base.js       弹窗基类
└── img/
    └── products/              商品图（31 张）
```

## 商品图

31 张商品图为 AI 生成（MOSS-Image / Qwen-Image-2.1），统一浅粉紫渐变背景 + 白色圆台，商品为二次元幻想品类：电磁炮、手办、痛车、魔法杖、能量光剑、JK 制服、巫女服、机甲模型等。

## 许可

本项目采用 [CC0 1.0 Universal](LICENSE) 协议，即**放弃全部著作权，进入公有领域**。

你可以任意复制、修改、分发、商用，无需署名。
