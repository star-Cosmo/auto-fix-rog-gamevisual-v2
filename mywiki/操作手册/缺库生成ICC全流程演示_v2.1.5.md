# 缺库生成 ICC 全流程演示（v2.1.5）

> 留档日期：2026-10-08 · 适用版本：v2.1.5 及以上 · 操作人：star / 后续维护者

本文档记录「ICC 库中没有用户面板」时，工具 v2.1.5 的完整交互流程与验证方法，供后来者复现、演示和回归测试。

## 一、背景

换屏后，奥创按 `{机型}_{显卡}_{屏幕硬件ID}.icm` 命名在 `C:\ProgramData\ASUS\GameVisual\` 找校色文件。内置 `color/` 库覆盖不了所有面板，v2.1.5 之前这种情况直接失败（「ICC 库没有你的面板」），用户只能干等库更新。

v2.1.5 起内置 **EDID 校色文件构造器**：读取屏幕 EDID 色度块（色域 xy / 白点 / 伽马）→ 生成最小合法 ICC v2 profile → 让 GameVisual 功能可用。

## 二、涉及组件

| 文件 | 作用 |
|---|---|
| `gamevisual_fixer/edid.py` | 解析 EDID 色度块 → `Chromaticity`（bytes 0x17-0x21） |
| `gamevisual_fixer/iccgen.py` | 色度数据 → ICC v2 profile（9 标签：desc/cprt/wtpt/rXYZ/gXYZ/bXYZ/rTRC/gTRC/bTRC），纯标准库 |
| `gamevisual_fixer/planner.py` | `build_generated_plan()` 产出 `src_dir="generated"` 的动作 |
| `gamevisual_fixer/applier.py` | 处理 generated 动作：调用 `build_icc` 实时生成并写入 GameVisual 目录 |
| `gamevisual_fixer/cli.py` | 缺库时交互引导（选 1 生成 / 选 2 等待）+ 免责声明 + 卸载指引 |
| `uninstall_fix.bat` | 一键删除生成文件并恢复备份（自带 UAC 提权） |
| `tests/test_iccgen.py` / `test_applier_gen.py` | 结构断言 + 生成-落盘-备份回归测试 |

## 三、完整交互流程（用户视角）

```
第 1 步：检测屏幕与机型
  识别到机型: FX507ZM
  检测到屏幕: AOC2270   厂商=AOC   硬件ID=E3052270   ← 外接屏
  检测到屏幕: CSW150F   厂商=CSW   硬件ID=770E150F   ← 笔记本内屏
  检测到多块屏幕，且无法自动判断哪块是笔记本内屏:
    1. ...
    3. 厂商=CSW  硬件ID=770E150F（产品号 150F）
  请选择笔记本内屏对应的序号 [1-4，直接回车=1]: 3
  已自动识别笔记本内屏，硬件 ID: 770E150F

第 2 步：生成修复计划
  未能生成修复计划：ICC 库里没有你这个面板的校色文件。
    检测到的屏幕：厂商=CSW  硬件ID=770E150F  产品号=150F

  请选择（只需输入数字后回车）:
    1. 立即用内置构造器生成校色文件并修复
    2. 暂不修复（ICC 库更新后会包含你的面板，敬请期待）
  请输入 [1 或 2，直接回车=1]: 1

  ════════════════════════════════════════════
    免责声明（请仔细阅读）
  ════════════════════════════════════════════
    1. 生成的校色文件基于屏幕硬件报告的色彩数据构造，能让 GameVisual 识别
       并启用色彩模式，但非官方出厂校色，显示效果可能与原厂略有差异。
    2. 本工具会先完整备份原 GameVisual 配置，随时可一键还原。
    3. 不满意时运行 uninstall_fix.bat 即可完整卸载本次修复。

第 3 步：生成并应用校色文件（无需你操作）
  [非管理员时] 需要管理员权限: 正在弹出 UAC 窗口，请在弹窗中点「是」
  [UAC 成功] 已在新窗口继续修复，本窗口可以直接关闭
  修复完成! 已复制 1 个文件
  修改前的完整备份: C:\ProgramData\ASUS\GameVisual_backup_时间戳
  本次运行日志: C:\Users\xxx\Desktop\GameVisual修复日志_日期_时间.log

接下来请你手动完成（很重要，不做等于白修）:
  1. 断开网络  2. 完全关机  3. 重新开机打开奥创看 GameVisual
```

### 选择分支汇总

| 用户输入 | 结果 |
|---|---|
| `1`（或直接回车） | 生成校色文件并修复 → 自动备份 → 断网关机开机验证 |
| `2` | 跳过，提示可发屏幕信息到 chenbin2004sz@163.com 优先补库 |
| EDID 缺色度数据 | 提示无法生成，请发屏幕信息给作者 |
| 目标文件已存在 | 提示「目标校色文件已存在」，跳过生成 |

### 效果不满意时

运行解压目录里的 `uninstall_fix.bat`：
1. 自动请求管理员权限（UAC 点「是」）
2. 找到最新的 `GameVisual_backup_时间戳` 备份
3. 删除 GameVisual 中被修复工具放入的文件 → 从备份完整恢复
4. 提示断网 → 关机 → 开机验证

## 四、开发者复现 / 回归验证（不碰真实系统）

以下命令在 PowerShell 执行，全程不修改 `C:\ProgramData\ASUS\GameVisual`，可安全验证各环节。

### 1. dry-run 交互流程（只读）

```powershell
python -m gamevisual_fixer --dry-run --gamevisual-dir "$env:TEMP\opencode\fake_gv"
```

- 会真实检测本机面板（识别机型 + 多屏选择）
- 输入序号选内屏 → 缺库 → 输入 1 → 展示免责声明 → 「试运行结束：本可生成校色文件，本次没有修改任何文件」
- 全部打印输出可用 `Out-File -Encoding utf8` 落盘后查看，避免管道乱码

### 2. 真实生成 + LittleCMS 验证（写入临时目录）

```python
# e2e_demo.py（已留档于本目录）
import sys, tempfile
from pathlib import Path
sys.path.insert(0, r"E:\Workstation\Github-starCosmo\auto-fix-gamevisual-v2")
from gamevisual_fixer.applier import apply
from gamevisual_fixer.edid import Chromaticity
from gamevisual_fixer.planner import build_generated_plan
from PIL import ImageCms  # 仅验证用，非项目依赖

ch = Chromaticity(0.648, 0.330, 0.325, 0.602, 0.151, 0.068, 0.313, 0.329, 2.2)
work = Path(tempfile.mkdtemp(prefix="gvf-e2e-"))
gv = work / "GameVisual"
plan = build_generated_plan("FX507ZM", "770E150F", "10DE")
report = apply(plan, gv, work / "lib", work / "spool", chromaticity=ch)
assert report.copied == 1
dst = gv / "FX507ZM_10DE_770E150F.icm"
assert dst.is_file() and dst.stat().st_size > 100
p = ImageCms.getOpenProfile(str(dst))          # LittleCMS 加载
ImageCms.buildTransformFromOpenProfiles(p, ImageCms.createProfile("sRGB"), "RGB", "RGB")
assert list(work.glob("GameVisual_backup_*"))  # 备份已创建
```

预期输出（2026-10-08 实测通过）：

```
== 1. 生成修复计划 ==  计划动作: FX507ZM_10DE_770E150F.icm (src=generated)
== 2. 执行 ==          复制: 1  跳过: 0  备份: ...\GameVisual_backup_20261008_063302
== 3. 生成文件 ==      472 bytes
== 4. LittleCMS 验证 == ✅ 文件可被加载，色彩转换正常
== 5. 备份目录确认 ==  ✅
```

### 3. 单元测试

```powershell
python -m pytest tests/ -q   # 34 项全绿（含 test_iccgen.py 9 项、test_applier_gen.py 3 项）
```

## 五、关键设计约束（改动时务必保持）

1. **零第三方依赖**：`iccgen.py` 只用 `struct`；`Pillow/ImageCms` 仅在测试验证脚本里出现，绝不进入生产依赖
2. **ICC 必须合法**：9 标签是 matrix display profile 的底线（缺 TRC 会被 Windows 拒收），改动后必须过 LittleCMS 验证
3. **纯函数分层**：planner 产出纯动作（不碰文件系统），实际生成/写入在 applier；用户交互全在 cli
4. **可回退**：任何生成前必须自动备份；uninstall_fix.bat 必须能完整还原
5. **免责声明不可删**：生成策略非官方校色，交互层必须展示免责声明

## 六、已知边界

- **手动 `--panel-hwid` 指定无法生成**：手动指定时拿不到 EDID 色度数据 → 走「缺少色彩数据」提示，需联系作者。正常双击自动检测不受影响
- **虚拟机无法演示真实效果**：虚拟显卡无真实面板 EDID，也无法验证奥创接受；真机验证步骤：管理员运行 → 断网 → 关机 → 开机 → 看奥创
- 生成的 ICC 为「接近面板物理特性」的近似校色，非官方出厂文件；官方 ICC 入库后优先级更高（planner 先匹配库）