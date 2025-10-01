#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自动更新 zhwiki-*.dict 文件
从 https://github.com/felixonmars/fcitx5-pinyin-zhwiki 下载最新版本
"""

# 关联文件
# 目标词典文件：dict/zhwiki-YYYYMMDD.dict
# 状态文件：logs/zhwiki_status.json
# 日志文件：logs/zhwiki_update.log

### 使用说明

# - 无参数: 检查更新，仅在有新版本或更新的词库文件时更新
# - `--force`: 强制更新，即使版本和文件日期都相同
# - `--github-token TOKEN`: 指定 GitHub Token（可选，优先级高于环境变量）
# - `GITHUB_TOKEN=TOKEN`: 设置环境变量，推荐使用

import os
import sys
import time
import requests
import json
from pathlib import Path
from typing import Optional, List
import logging
import glob
import re

# ================================ 配置常量 ================================
# 目标 GitHub 仓库信息
GITHUB_REPO_OWNER = "felixonmars"
GITHUB_REPO_NAME = "fcitx5-pinyin-zhwiki"

# 文件路径配置
PROJECT_ROOT = Path(__file__).parent.parent
DICT_DIR = PROJECT_ROOT / "dict"
STATUS_FILE = PROJECT_ROOT / "logs" / "zhwiki_status.json"
LOG_FILE = PROJECT_ROOT / "logs" / "zhwiki_update.log"

# 网络请求配置
MAX_RETRIES = 3  # 最大重试次数
RETRY_DELAY = 5  # 重试延迟（秒）
REQUEST_TIMEOUT = 60  # 请求超时（秒）

# GitHub API 配置
GITHUB_API_ACCEPT = "application/vnd.github.v3+json"
USER_AGENT = "ZhwikiUpdater/1.0"

# 最大历史记录数
MAX_HISTORY_RECORDS = 50

# 文件匹配模式
TARGET_FILE_PREFIX = "zhwiki-"
TARGET_FILE_SUFFIX = ".dict"
DATE_PATTERN = r'zhwiki-(\d{8})\.dict'  # 匹配zhwiki-YYYYMMDD.dict格式

# ================================ 状态结构体定义 ================================
# 默认状态结构体模板
DEFAULT_STATUS = {
    "version": None,
    "latest_dict_date": None,
    "latest_dict_name": None,
    "update_history": []
}

# 新状态结构体模板（不包含历史记录，避免覆盖）
NEW_STATUS_TEMPLATE = {
    "version": None,
    "latest_dict_date": None,
    "latest_dict_name": None
}

# ================================ 日志配置 ================================
logging.basicConfig(
    level=logging.INFO,  # 日志级别：DEBUG、INFO、WARNING、ERROR、CRITICAL
    format='%(asctime)s - %(levelname)s - %(message)s',  # 日志格式：时间 - 级别 - 消息
    handlers=[
        # 日志文件路径，确保logs目录存在
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        # 控制台输出
        logging.StreamHandler()
    ])
logger = logging.getLogger(__name__)


def get_github_token() -> str:
  """获取GitHub token并进行非空验证
    
    优先级：命令行参数 > 环境变量
    
    Returns:
        str: 非空的GitHub token
        
    Raises:
        ValueError: 当无法获取有效token时
    """
  # 检查命令行参数
  github_token = None
  for i, arg in enumerate(sys.argv):
    if arg == '--github-token' and i + 1 < len(sys.argv):
      github_token = sys.argv[i + 1]
      logger.debug("使用命令行参数提供的GitHub token")
      break

  # 如果命令行没有提供，尝试环境变量
  if github_token is None:
    github_token = os.getenv('GITHUB_TOKEN')
    if github_token is not None:
      logger.debug("使用环境变量GITHUB_TOKEN")

  # 验证token存在
  if github_token is None:
    raise ValueError(
        "必须提供GitHub token！请设置GITHUB_TOKEN环境变量或使用 --github-token 参数")

  # 检查token格式（基本验证）
  github_token = github_token.strip()
  if not github_token:
    raise ValueError("GitHub token不能为空")

  return github_token


class ZhwikiUpdater:

  def __init__(self, github_token: str):
    self.repo_owner = GITHUB_REPO_OWNER
    self.repo_name = GITHUB_REPO_NAME
    self.dict_dir = DICT_DIR
    self.status_file = STATUS_FILE
    self.github_token = github_token

    # API配置成员变量
    self.api_url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/releases/latest"
    self.headers = {
        'Accept': GITHUB_API_ACCEPT,
        'User-Agent': USER_AGENT,
        'Authorization': f'Bearer {self.github_token}'
    }

    self.old_status = self.load_status()  # 旧状态（包含历史记录）
    self.new_status = NEW_STATUS_TEMPLATE.copy()  # 新状态（不包含历史记录）

  def get_latest_release_info(self) -> Optional[dict]:
    """获取最新发布版本信息， 返回响应JSON"""
    for attempt in range(MAX_RETRIES):
      try:
        logger.info(f"尝试获取发布信息 (第 {attempt + 1}/{MAX_RETRIES} 次)")
        response = requests.get(self.api_url,
                                headers=self.headers,
                                timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        return response.json()

      except requests.exceptions.HTTPError as e:
        if e.response.status_code == 403:
          rate_limit_remaining = e.response.headers.get(
              'X-RateLimit-Remaining', 'unknown')
          rate_limit_reset = e.response.headers.get('X-RateLimit-Reset',
                                                    'unknown')
          logger.warning(
              f"GitHub API 速率限制 (剩余: {rate_limit_remaining}, 重置时间: {rate_limit_reset})"
          )

          if attempt < MAX_RETRIES - 1:
            wait_time = RETRY_DELAY * (attempt + 1)
            logger.info(f"等待 {wait_time} 秒后重试...")
            time.sleep(wait_time)
            continue
        else:
          logger.error(f"HTTP 错误: {e}")
          break
      except Exception as e:
        logger.error(f"获取发布信息失败 (尝试 {attempt + 1}): {e}")
        if attempt < MAX_RETRIES - 1:
          time.sleep(RETRY_DELAY)
          continue
        break

        return None

    return None

  def load_status(self) -> dict:
    """加载状态文件到旧状态结构体"""
    try:
      if self.status_file.exists():
        with open(self.status_file, 'r', encoding='utf-8') as f:
          status = json.load(f)
          for key in DEFAULT_STATUS:
            if key not in status:
              status[key] = DEFAULT_STATUS[key]
          return status
    except Exception as e:
      logger.warning(f"加载状态文件失败: {e}")
    return DEFAULT_STATUS.copy()

  def save_status(self):
    """将旧状态实例持久化到文件"""
    try:
      self.status_file.parent.mkdir(parents=True, exist_ok=True)
      with open(self.status_file, 'w', encoding='utf-8') as f:
        json.dump(self.old_status, f, ensure_ascii=False, indent=2)
      logger.debug("已持久化状态文件")
    except Exception as e:
      logger.error(f"持久化状态文件失败: {e}")

  def update_status(self, success: bool = True):
    """将新状态实例同步到旧状态实例，并添加更新历史"""
    from datetime import datetime

    # 将新状态的非空值同步到旧状态
    for key, value in self.new_status.items():
      if value is not None:
        self.old_status[key] = value
        logger.debug(f"已同步{key}: {value}")

    # 添加更新历史记录
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    version = self.new_status.get("version")
    dict_name = self.new_status.get("latest_dict_name", "未知")

    # 构建更新状态文本
    if success:
      status_text = "✅ 成功"
      new_entry = f"{now}: {status_text} - 更新到版本 `{version}`, 词库文件: {dict_name}"
    else:
      status_text = "❌ 失败"
      new_entry = f"{now}: {status_text} - 尝试更新到版本 `{version}`, 词库文件: {dict_name}"

    # 添加更新历史记录
    if "update_history" not in self.old_status:
      self.old_status["update_history"] = []  # 确保历史记录列表存在
    self.old_status["update_history"].append(new_entry)  # 追加到列表末尾
    if len(self.old_status["update_history"]) > MAX_HISTORY_RECORDS:  # 超过最大记录数
      self.old_status["update_history"] = self.old_status["update_history"][
          -MAX_HISTORY_RECORDS:]  # 只保留最后50条记录

    logger.info(f"已添加更新历史: {new_entry}")

  def should_update(self, force: bool = False) -> bool:
    """判断是否需要更新"""
    if force:
      logger.info("强制更新模式")
      return True

    latest_version = self.new_status.get("version")
    current_version = self.old_status.get("version")
    if current_version != latest_version:
      logger.info(f"版本不同，需要更新: {current_version} -> {latest_version}")
      return True

    logger.info("版本相同，检查词库文件日期是否有更新...")
    latest_date: Optional[str] = self.new_status.get("latest_dict_date")
    current_date: Optional[str] = self.old_status.get("latest_dict_date")
    if current_date != latest_date:
      logger.info(f"词库日期不同，需要更新: {current_date} -> {latest_date}")
      return True

    logger.info(f"词库日期皆为{current_date}，无需更新")
    return False

  def extract_date_from_filename(self, filename: str) -> Optional[str]:
    """从文件名中提取日期
        
        例如: zhwiki-20240509.dict -> 20240509
        """
    # 使用全局配置的日期匹配模式
    match = re.search(DATE_PATTERN, filename)
    if match:
      return match.group(1)
    return None

  def find_latest_dict_asset(self, assets: List[dict]) -> Optional[dict]:
    """查找最新的zhwiki词库文件"""
    dict_assets = []

    for asset in assets:
      if asset['name'].startswith(
          TARGET_FILE_PREFIX) and asset['name'].endswith(TARGET_FILE_SUFFIX):
        date_str = self.extract_date_from_filename(asset['name'])
        if date_str:
          dict_assets.append({
              'asset': asset,
              'date': date_str,
              'name': asset['name']
          })

    if not dict_assets:
      return None

    # 按日期排序，返回最新的
    dict_assets.sort(key=lambda x: x['date'], reverse=True)
    latest = dict_assets[0]

    logger.info(
        f"找到 {len(dict_assets)} 个词库文件，最新的是: {latest['name']} (日期: {latest['date']})"
    )
    return latest

  def remove_old_dict_files(self) -> List[str]:
    """删除旧的zhwiki词库文件，返回删除的文件列表"""
    removed_files = []

    # 查找所有现有的zhwiki词库文件
    pattern = str(self.dict_dir / f"{TARGET_FILE_PREFIX}*{TARGET_FILE_SUFFIX}")
    existing_files = glob.glob(pattern)

    for file_path in existing_files:
      try:
        os.remove(file_path)
        filename = os.path.basename(file_path)
        removed_files.append(filename)
        logger.info(f"已删除旧词库文件: {filename}")
      except Exception as e:
        logger.error(f"删除文件失败 {file_path}: {e}")

    return removed_files

  def download_file(self, url: str, local_path: Path) -> bool:
    """下载文件到指定路径"""
    try:
      logger.info(f"开始下载: {url}")
      response = requests.get(url, stream=True, timeout=REQUEST_TIMEOUT)
      response.raise_for_status()

      with open(local_path, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
          if chunk:
            f.write(chunk)

      logger.info(f"下载完成: {local_path}")
      return True
    except Exception as e:
      logger.error(f"下载失败: {e}")
      return False

  def update(self, force: bool = False) -> bool:
    """执行更新操作"""
    logger.info("开始检查zhwiki词库更新...")

    # 获取最新发布信息
    release_info = self.get_latest_release_info()
    if not release_info:
      logger.error("无法获取发布信息")
      return False

    # 使用状态结构体存储版本信息
    self.new_status["version"] = release_info['tag_name']

    # 查找最新的词库文件
    latest_dict_info = self.find_latest_dict_asset(
        release_info.get('assets', []))
    if not latest_dict_info:
      logger.error("未找到zhwiki词库文件")
      return False

    # 存储最新词库信息到新状态中
    self.new_status["latest_dict_date"] = latest_dict_info['date']
    self.new_status["latest_dict_name"] = latest_dict_info['name']

    if not self.should_update(force):
      logger.info("无需更新")
      return True

    # 确保dict目录存在
    self.dict_dir.mkdir(parents=True, exist_ok=True)

    # 删除旧的词库文件
    removed_files = self.remove_old_dict_files()
    if removed_files:
      logger.info(
          f"删除了 {len(removed_files)} 个旧词库文件: {', '.join(removed_files)}")

    # 下载新的词库文件
    new_dict_path = self.dict_dir / latest_dict_info['name']
    asset = latest_dict_info['asset']

    if not self.download_file(asset['browser_download_url'], new_dict_path):
      return False

    # 更新状态信息
    self.update_status(success=True)

    # 统一持久化保存状态结构体
    self.save_status()

    logger.info(f"更新完成！新词库文件: {latest_dict_info['name']}")
    return True


def main():
  """主函数"""
  try:
    # 获取并验证GitHub token
    github_token = get_github_token()

    # 检查命令行参数
    force_update = '--force' in sys.argv

    updater = ZhwikiUpdater(github_token=github_token)

    success = updater.update(force=force_update)
    if success:
      logger.info("更新操作成功完成")
      sys.exit(0)
    else:
      logger.error("更新操作失败")
      sys.exit(1)
  except ValueError as e:
    logger.error(f"配置错误: {e}")
    sys.exit(1)
  except KeyboardInterrupt:
    logger.info("用户取消操作")
    sys.exit(1)
  except Exception as e:
    logger.error(f"发生未预期的错误: {e}")
    sys.exit(1)


if __name__ == "__main__":
  main()
