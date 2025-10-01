# 自动更新系统文件结构说明

本项目包含两个自动更新系统，用于维护不同的词库文件。

## 📁 文件结构

### CustomPinyin 更新系统

- **脚本文件**: `script/update_custom_pinyin.py`
- **工作流文件**: `.github/workflows/update-custom-pinyin.yml`
- **状态文件**: `logs/custom_pinyin_status.json`
- **日志文件**: `logs/custom_pinyin_update.log`
- **目标词库**: `dict/CustomPinyinDictionary_Fcitx.dict`
- **更新频率**: 每天凌晨 2 点
- **源仓库**: https://github.com/wuhgit/CustomPinyinDictionary

### Zhwiki 更新系统

- **脚本文件**: `script/update_zhwiki.py`
- **工作流文件**: `.github/workflows/update-zhwiki.yml`
- **状态文件**: `logs/zhwiki_status.json`
- **日志文件**: `logs/zhwiki_update.log`
- **目标词库**: `dict/zhwiki-YYYYMMDD.dict`
- **更新频率**: 每周日凌晨 3 点
- **源仓库**: https://github.com/felixonmars/fcitx5-pinyin-zhwiki

## 🔧 使用方法

### CustomPinyin 系统

```bash
# 检查更新
python script/update_custom_pinyin.py

# 强制更新
python script/update_custom_pinyin.py --force

# 使用指定token
python script/update_custom_pinyin.py --github-token YOUR_TOKEN
```

### Zhwiki 系统

```bash
# 检查更新
python script/update_zhwiki.py

# 强制更新
python script/update_zhwiki.py --force

# 使用指定token
python script/update_zhwiki.py --github-token YOUR_TOKEN
```

## 🚀 自动化特性

两个系统都支持：

- ✅ 自动版本检测
- ✅ 智能更新判断
- ✅ 完整的错误处理和重试机制
- ✅ 详细的操作日志
- ✅ GitHub Actions 自动化
- ✅ 强制更新选项
- ✅ 手动触发支持

### Zhwiki 系统特有功能：

- ✅ 自动删除旧版本词库文件
- ✅ 基于文件日期的智能更新

## 📝 日志文件

所有操作都会记录到对应的日志文件中：

- `logs/custom_pinyin_update.log` - CustomPinyin 更新日志
- `logs/zhwiki_update.log` - Zhwiki 更新日志

日志包含：

- 详细的操作步骤
- 错误信息和重试记录
- 文件下载和处理过程
- 状态更新记录

## 🔒 权限要求

两个系统都需要：

- `GITHUB_TOKEN` 环境变量或命令行参数
- 对目标仓库的读取权限
- 对工作区的写入权限
