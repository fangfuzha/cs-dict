#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自动更新 CustomPinyinDictionary_Fcitx.dict 文件
从 https://github.com/wuhgit/CustomPinyinDictionary 下载最新版本并转换格式
"""

# 关联文件
# 目标词典文件：dict/CustomPinyinDictionary_Fcitx.dict
# 状态文件：logs/custom_pinyin_status.json
# 日志文件：logs/custom_pinyin_update.log

### 使用说明

# - 无参数: 检查更新，仅在有新版本或文件日期变化时更新
# - `--force`: 强制更新，即使版本和文件日期都相同
# - `--github-token TOKEN`: 指定 GitHub Token（可选，优先级高于环境变量）
# - `GITHUB_TOKEN=TOKEN`: 设置环境变量，推荐使用

import os
import sys
import time
import requests
import json
import tarfile
import tempfile
import shutil
from pathlib import Path
from typing import Optional, List
import hashlib
import logging

# ================================ 配置常量 ================================
# 目标 GitHub 仓库信息
GITHUB_REPO_OWNER = "wuhgit"
GITHUB_REPO_NAME = "CustomPinyinDictionary"

# 文件路径配置
PROJECT_ROOT = Path(__file__).parent.parent
DICT_FILE = PROJECT_ROOT / "dict" / "CustomPinyinDictionary_Fcitx.dict"
STATUS_FILE = PROJECT_ROOT / "logs" / "custom_pinyin_status.json"
LOG_FILE = PROJECT_ROOT / "logs" / "custom_pinyin_update.log"

# 网络请求配置
MAX_RETRIES = 3  # 最大重试次数
RETRY_DELAY = 5  # 重试延迟（秒）
REQUEST_TIMEOUT = 60  # 请求超时（秒）

# GitHub API 配置
GITHUB_API_ACCEPT = "application/vnd.github.v3+json"
USER_AGENT = "CustomPinyinUpdater/1.0"

# 最大历史记录数
MAX_HISTORY_RECORDS = 50

# 文件匹配模式
TARGET_FILE_PATTERN = "CustomPinyinDictionary_Fcitx"
DATE_PATTERN = r'_(\d{8})\.'  # 匹配文件名中的8位日期格式

# ================================ 状态结构体定义 ================================
# 默认状态结构体模板
DEFAULT_STATUS = {"version": None, "asset_date": None, "update_history": []}

# 新状态结构体模板（不包含历史记录，避免覆盖）
NEW_STATUS_TEMPLATE = {"version": None, "asset_date": None}

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


class CustomPinyinUpdater:

  def __init__(self, github_token: str):
    self.repo_owner = GITHUB_REPO_OWNER
    self.repo_name = GITHUB_REPO_NAME
    self.dict_file = DICT_FILE
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
    self.asset_name = None  # 当前资源文件名

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

    # 构建文件日期信息
    file_date_info = ""
    file_date = self.new_status.get("asset_date")
    if file_date:
      try:
        formatted_date = datetime.strptime(file_date,
                                           '%Y%m%d').strftime('%Y-%m-%d')
        file_date_info = f" (目标文件日期: {formatted_date})"
      except ValueError:
        file_date_info = f" (目标文件日期: {file_date})"

# 构建更新状态文本
    if success:
      status_text = "✅ 成功"
      new_entry = f"{now}: {status_text} - 更新到版本 `{version}`{file_date_info}"
    else:
      status_text = "❌ 失败"
      new_entry = f"{now}: {status_text} - 尝试更新到版本 `{version}`{file_date_info}"


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

    logger.info("版本相同，检查文件日期是否有更新...")
    latest_date: Optional[str] = self.new_status.get("asset_date")
    current_date: Optional[str] = self.old_status.get("asset_date")
    if current_date != latest_date:
      logger.info(f"文件日期不同，需要更新: {current_date} -> {latest_date}")
      return True
    logger.info(f"文件日期皆为{current_date}，无需更新")
    return False

  def extract_date_from_filename(self, filename: str) -> Optional[str]:
    """从文件名中提取日期
        
        例如: CustomPinyinDictionary_Fcitx_20250101.tar.gz -> 20250101
        """
    import re
    # 使用全局配置的日期匹配模式
    match = re.search(DATE_PATTERN, filename)
    if match:
      return match.group(1)
    return None

  def find_tar_gz_asset(self, assets: List[dict]) -> Optional[dict]:
    """查找tar.gz格式的资源文件"""
    for asset in assets:
      if asset['name'].endswith(
          '.tar.gz') and TARGET_FILE_PATTERN in asset['name']:
        return asset
    return None

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

  def extract_tar_gz(self, tar_path: Path, extract_dir: Path) -> bool:
    """解压tar.gz文件"""
    try:
      logger.info(f"开始解压: {tar_path}")
      with tarfile.open(tar_path, 'r:gz') as tar:
        tar.extractall(extract_dir)
      logger.info(f"解压完成到: {extract_dir}")
      return True
    except Exception as e:
      logger.error(f"解压失败: {e}")
      return False

  def find_dict_files(self, directory: Path) -> List[Path]:
    """查找目录中的dict文件"""
    dict_files = []
    for dict_file in directory.rglob("*.dict"):
      if TARGET_FILE_PATTERN in dict_file.name:
        dict_files.append(dict_file)
    return dict_files

  def copy_dict_file(self, source_dict: Path, output_file: Path) -> bool:
    """直接复制dict文件"""
    try:
      logger.info(f"开始复制dict文件: {source_dict} -> {output_file}")

      # 确保输出目录存在
      output_file.parent.mkdir(parents=True, exist_ok=True)

      # 直接复制文件
      shutil.copy2(source_dict, output_file)

      logger.info("dict文件复制完成")
      return True

    except Exception as e:
      logger.error(f"复制dict文件时出错: {e}")
      return False

  def calculate_file_hash(self, file_path: Path) -> Optional[str]:
    """计算文件的MD5哈希值"""
    try:
      hash_md5 = hashlib.md5()
      with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
          hash_md5.update(chunk)
      return hash_md5.hexdigest()
    except Exception as e:
      logger.error(f"计算哈希值失败: {e}")
      return None

  def update(self, force: bool = False) -> bool:
    """执行更新操作"""
    logger.info("开始检查更新...")

    # 获取最新发布信息
    release_info = self.get_latest_release_info()
    if not release_info:
      logger.error("无法获取发布信息")
      return False
    # 使用状态结构体存储版本信息
    self.new_status["version"] = release_info['tag_name']

    # 查找并存储tar.gz资源信息
    asset = self.find_tar_gz_asset(release_info.get('assets', []))
    if not asset:
      logger.error("未找到tar.gz格式的资源文件")
      return False
    else:
      logger.info(f"找到资源文件名: {asset['name']}")
      # 设置成员变量
      self.asset_name = asset['name']
      # 将资产日期信息存储到新状态中
      self.new_status["asset_date"] = self.extract_date_from_filename(
          asset['name'])

    if not self.should_update(force):
      logger.info("无需更新")
      return True

    # 创建临时目录，with语句结束后自动删除
    with tempfile.TemporaryDirectory() as temp_dir:
      temp_path = Path(temp_dir)
      tar_file = temp_path / asset['name']
      extract_dir = temp_path / "extracted"

      # 下载文件
      if not self.download_file(asset['browser_download_url'], tar_file):
        return False

      # 解压文件
      if not self.extract_tar_gz(tar_file, extract_dir):
        return False

      # 查找dict文件
      dict_files = self.find_dict_files(extract_dir)
      if not dict_files:
        logger.error("解压后未找到CustomPinyinDictionary_Fcitx.dict文件")
        return False

      logger.info(f"找到 {len(dict_files)} 个dict文件:")
      for dict_file in dict_files:
        logger.info(f"  - {dict_file}")

      # 使用第一个找到的dict文件
      source_dict_file = dict_files[0]

      # 直接复制dict文件
      if not self.copy_dict_file(source_dict_file, self.dict_file):
        return False

      # 更新状态信息（使用成员变量中的状态信息）
      self.update_status(success=True)

      # 统一持久化保存状态结构体
      self.save_status()

      # 计算新文件的哈希值
      new_hash = self.calculate_file_hash(self.dict_file)
      if new_hash:
        logger.info(f"新文件哈希值: {new_hash}")

      logger.info("更新完成！")
      return True


def main():
  """主函数"""
  try:
    # 获取并验证GitHub token
    github_token = get_github_token()

    # 检查命令行参数
    force_update = '--force' in sys.argv

    updater = CustomPinyinUpdater(github_token=github_token)

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
