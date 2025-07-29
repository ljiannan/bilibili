#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Optimized version of yt_plus02.py

import yt_dlp
import os
import logging
import asyncio
import concurrent.futures
from datetime import datetime
from urllib.parse import urlparse
from functools import lru_cache
from typing import Dict, List, Tuple, Optional, Any
import random
import json
import pathlib
import re
from tqdm import tqdm
import shutil
import sys
from colorama import init, Fore, Back, Style
import time

# 初始化colorama
init(autoreset=True)

# ===================== 用户配置区域 =====================

# 下载源和目标配置
URL_LIST_FILE = r"C:\Users\DELL\Desktop\bilibili视频链接.txt"  # URL列表文件路径
OUTPUT_BASE_DIR = r"D:\采集到的视频"  # 下载根目录
LOG_DIR = r"C:\Users\DELL\Desktop\视频裁剪\logs"  # 日志目录
DOWNLOADED_RECORD_FILE = r"C:\Users\DELL\Desktop\视频采集\downloaded_videos.json"  # 已下载视频记录文件

# Cookie配置
COOKIES = {
    "youtube": r"C:\Users\DELL\Desktop\youtube.txt",
    "bilibili": r"C:\Users\DELL\Desktop\bilibili.txt"
}

# 下载行为配置
MAX_WORKERS = 5  # 并行下载数量
MAX_RETRIES = 3  # 单个视频最大重试次数
DOWNLOAD_TIMEOUT = 600  # 下载超时(秒)

# 分辨率设置
MIN_RESOLUTION = 1080  # 视频最小分辨率 (YouTube) - 短边至少这个分辨率
MAX_RESOLUTION = 2160  # 视频最大分辨率 (YouTube) - 可选限制，设为较高值以获取高质量视频

# 显示配置
USE_PROGRESS_BAR = True  # 是否使用进度条显示
DEBUG_MODE = False  # 调试模式，打印更多信息
SIMPLE_MODE = True  # 简化模式，使用更简单的进度显示

# ===================== 系统配置区域 =====================
# 无需修改的内部配置

# 将配置整合到一个字典中，以便程序内部使用
CONFIG = {
    "cookies": COOKIES,
    "output_base": OUTPUT_BASE_DIR,
    "log_path": LOG_DIR,
    "max_retries": MAX_RETRIES,
    "max_workers": MAX_WORKERS,
    "timeout": DOWNLOAD_TIMEOUT,
    "downloaded_record": DOWNLOADED_RECORD_FILE,
    "url_list_file": URL_LIST_FILE,
    "use_progress_bar": USE_PROGRESS_BAR,
    "debug_mode": DEBUG_MODE,
    "simple_mode": SIMPLE_MODE,
    "max_resolution": MAX_RESOLUTION,
    "min_resolution": MIN_RESOLUTION
}

# 从文件读取URL列表
def load_url_list_from_file(file_path: str) -> Dict[str, str]:
    """从文本文件读取URL列表
    
    文件格式: 每行一个URL和标题，用制表符分隔
    例如: https://www.youtube.com/watch?v=abcdef123456\t视频标题
    """
    result = {}
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):  # 跳过空行和注释
                    parts = line.split('\t', 1)  # 使用制表符分割URL和标题
                    if len(parts) == 2:
                        url, title = parts
                        result[url.strip()] = title.strip()
                    else:
                        # 如果没有标题，使用URL作为标题的依据，但需要清理
                        url = parts[0].strip()
                        # 从URL中提取视频ID作为标题
                        if 'youtube' in url or 'youtu.be' in url:
                            video_id = url.split('v=')[-1].split('&')[0] if 'v=' in url else url.split('/')[-1]
                            result[url] = f"youtube_{video_id}"
                        elif 'bilibili' in url:
                            video_id = url.split('/')[-1]
                            result[url] = f"bilibili_{video_id}"
                        else:
                            # 为其他URL创建安全的标题
                            safe_title = re.sub(r'[\\/:*?"<>|]', '_', url)
                            result[url] = safe_title
        return result
    except Exception as e:
        # 由于logger在后面才定义，这里使用logging模块直接记录错误
        logging.error(f"读取URL列表失败: {str(e)}")
        return {}

# 加载URL列表
url_list = load_url_list_from_file(CONFIG["url_list_file"])

# ===================================================

# 日志配置
class LoggerSetup:
    _logger = None

    @classmethod
    def get_logger(cls):
        if cls._logger is None:
            cls._logger = cls._setup_logger()
        return cls._logger

    @staticmethod
    def _setup_logger():
        os.makedirs(CONFIG["log_path"], exist_ok=True)
        log_file = os.path.join(CONFIG["log_path"], f"download_{datetime.now().strftime('%Y%m%d')}.log")

        logger = logging.getLogger("VideoDownloader")
        logger.setLevel(logging.INFO)

        # 避免重复添加处理器
        if not logger.handlers:
            # 文件处理器 - 保持完整日志记录
            file_handler = logging.FileHandler(log_file, encoding='utf-8')
            file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
            file_handler.setFormatter(file_formatter)
            logger.addHandler(file_handler)

            # 控制台处理器 - 美化输出
            console_handler = ColorizingStreamHandler()
            console_formatter = logging.Formatter('%(message)s')  # 简化控制台输出格式
            console_handler.setFormatter(console_formatter)
            logger.addHandler(console_handler)

        return logger


# 彩色日志处理器
class ColorizingStreamHandler(logging.StreamHandler):
    def emit(self, record):
        try:
            message = self.format(record)
            
            # 根据日志级别添加颜色
            if record.levelno >= logging.ERROR:
                message = f"{Fore.RED}{Style.BRIGHT}{message}{Style.RESET_ALL}"
            elif record.levelno >= logging.WARNING:
                message = f"{Fore.YELLOW}{message}{Style.RESET_ALL}"
            elif record.levelno == logging.INFO:
                # 根据消息内容应用不同的颜色
                if "✅ 下载成功" in message:
                    message = f"{Fore.GREEN}{Style.BRIGHT}{message}{Style.RESET_ALL}"
                elif "开始处理任务" in message:
                    message = f"{Fore.CYAN}{Style.BRIGHT}{message}{Style.RESET_ALL}"
                elif "标题:" in message:
                    message = f"{Fore.WHITE}{Style.BRIGHT}{message}{Style.RESET_ALL}"
                elif "URL:" in message:
                    message = f"{Fore.BLUE}{message}{Style.RESET_ALL}"
                elif "保存路径:" in message:
                    message = f"{Fore.MAGENTA}{message}{Style.RESET_ALL}"
                elif "====" in message:
                    message = f"{Fore.CYAN}{Style.BRIGHT}{message}{Style.RESET_ALL}"
                elif "下载中:" in message:
                    message = f"{Fore.BLUE}{message}{Style.RESET_ALL}"
            
            stream = self.stream
            stream.write(message)
            stream.write(self.terminator)
            self.flush()
        except Exception:
            self.handleError(record)


logger = LoggerSetup.get_logger()


# 平台检测
@lru_cache(maxsize=128)
def get_platform(url: str) -> str:
    """判断URL所属平台，使用缓存优化"""
    if 'youtube' in url:
        return 'youtube'
    elif 'bilibili' in url:
        return 'bilibili'
    else:
        raise ValueError(f"不支持的平台: {url}")


# 下载配置
def get_ydl_opts(platform: str, output_path: str, task_id: int, position: int = 0) -> Dict[str, Any]:
    """获取平台专用配置"""

    # 创建进度条
    progress_bar = DownloadProgressBar(task_id, len(url_list), position)

    common_opts = {
        'outtmpl': os.path.join(output_path, '%(title)s.%(ext)s'),
        'retries': 10,
        'fragment_retries': 10,
        'ignoreerrors': True,
        'noprogress': True,  # 禁用内置进度条
        'progress_hooks': [progress_bar.hook],
        'logger': logger,
        'merge_output_format': 'mp4',
        'socket_timeout': CONFIG["timeout"],
        'verbose': CONFIG["debug_mode"],  # 启用详细输出以便调试
        'quiet': not CONFIG["debug_mode"],  # 非调试模式下静默运行
        'postprocessors': [{
            'key': 'FFmpegMetadata',
            'add_metadata': True
        }]
    }

    # 平台特定配置
    if platform == 'youtube':
        return {
            **common_opts,
            'format': f'bestvideo[height>={CONFIG["min_resolution"]}]+bestaudio[ext=m4a]/best[height>={CONFIG["min_resolution"]}]/best',  # 确保短边至少是指定分辨率
            'cookiefile': CONFIG["cookies"]["youtube"],
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36',
                'Accept-Language': 'en-US,en;q=0.9'
            }
        }
    elif platform == 'bilibili':
        return {
            **common_opts,
            'format': 'bestvideo+bestaudio/best',
            'cookiefile': CONFIG["cookies"]['bilibili'],
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': 'https://www.bilibili.com/'
            }
        }


# 带超时的下载函数
def download_with_timeout(ydl_opts, url):
    """带超时功能的下载函数"""
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        return ydl.download([url])


async def download_video(url: str, title: str, task_id: int, position: int = 0) -> bool:
    """异步下载单个视频
    
    Args:
        url: 视频URL
        title: 视频标题
        task_id: 全局任务ID
        position: 工作线程ID，用于进度条定位
    """
    progress_bar = None
    status_bar = None
    # 获取状态栏颜色
    text_color = random.choice(DownloadProgressBar.TEXT_COLORS)
    
    try:
        platform = get_platform(url)

        # 创建日期目录结构
        date_str = datetime.now().strftime("%Y%m%d")
        output_path = os.path.join(CONFIG["output_base"], platform, date_str, title)
        os.makedirs(output_path, exist_ok=True)

        # 创建状态显示行 - 显示当前任务信息，使用随机颜色
        status_msg = f"开始 [{task_id}/{len(url_list)}]: {title[:40]}"
        status_bar = tqdm(
            total=0, 
            position=position, 
            bar_format=f"{text_color}{status_msg}{Style.RESET_ALL}",
            leave=True
        )
        
        # 获取下载配置 - 传递选定的颜色给进度条
        ydl_opts = get_ydl_opts(platform, output_path, task_id, position)
        
        # 保存进度条引用以便后续关闭
        progress_bar = ydl_opts['progress_hooks'][0].__self__
        
        # 保存文本颜色以便后续使用
        success_color = progress_bar.text_color
        
        # 减少线程之间的干扰
        if platform == 'youtube':
            await asyncio.sleep(random.uniform(0.2, 0.5))
        
        # 关闭状态栏，进度条会接管这个位置
        status_bar.close()
        status_bar = None
        
        # 在线程池中运行实际下载
        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            for attempt in range(CONFIG["max_retries"]):
                try:
                    # 设置下载函数
                    download_task = lambda: download_with_timeout(ydl_opts, url)
                    download_future = loop.run_in_executor(pool, download_task)
                    
                    # 等待下载完成，设置超时时间
                    try:
                        # 等待下载完成
                        result = await asyncio.wait_for(download_future, timeout=CONFIG["timeout"])
                    except asyncio.TimeoutError:
                        # 处理超时情况 - 创建一个新的状态行显示超时信息
                        if progress_bar and hasattr(progress_bar, 'close'):
                            progress_bar.close()
                            progress_bar = None
                            
                        status_bar = tqdm(
                            total=0, 
                            position=position, 
                            bar_format=f"{Fore.RED}⚠️ [{task_id}] 下载超时 (尝试 {attempt + 1}/{CONFIG['max_retries']})",
                            leave=True
                        )
                        
                        # 重试前等待
                        if attempt < CONFIG["max_retries"] - 1:
                            delay = 2 ** (attempt + 1)
                            await asyncio.sleep(delay)
                            status_bar.close()
                            status_bar = None
                        continue
                    
                    # 检查是否实际下载了视频文件
                    files = os.listdir(output_path)
                    video_files = [f for f in files if f.endswith(('.mp4', '.webm', '.mkv'))]
                    
                    if not video_files:
                        # 如果目录为空或只有非视频文件，可能是碰到了人机验证
                        if progress_bar and hasattr(progress_bar, 'close'):
                            progress_bar.close()
                            progress_bar = None
                            
                        tqdm.write(f"{Fore.RED}⚠️ [{task_id}] 可能碰到人机验证，未找到视频文件")
                        return False
                    
                    # 检查视频文件大小是否为0
                    for video_file in video_files:
                        file_path = os.path.join(output_path, video_file)
                        if os.path.getsize(file_path) < 10240:  # 小于10KB的视频文件视为异常
                            if progress_bar and hasattr(progress_bar, 'close'):
                                progress_bar.close()
                                progress_bar = None
                                
                            tqdm.write(f"{Fore.RED}⚠️ [{task_id}] 视频文件大小异常，可能是人机验证")
                            return False
                    
                    # 成功下载，计算文件大小
                    file_size = sum(os.path.getsize(os.path.join(output_path, f)) for f in video_files)
                    file_size_str = get_human_readable_size(file_size)
                    
                    # 关闭进度条
                    if progress_bar and hasattr(progress_bar, 'close'):
                        progress_bar.close()
                        progress_bar = None
                        
                    # 使用tqdm的写入方法，避免干扰进度条（使用任务颜色）
                    tqdm.write(f"{success_color}✅ [{task_id}] 成功: {video_files[0]} ({file_size_str}){Style.RESET_ALL}")
                    
                    # 保存已下载视频记录
                    save_downloaded_video(url)
                    return True

                except Exception as e:
                    error_message = str(e)
                    # 关闭进度条
                    if progress_bar and hasattr(progress_bar, 'close'):
                        progress_bar.close()
                        progress_bar = None
                        
                    # 显示错误消息（保持红色以表示错误）
                    tqdm.write(f"{Fore.RED}❌ [{task_id}] 失败: {error_message[:80]}")
                    
                    # 检测是否是人机验证错误
                    if "429" in error_message or "bot" in error_message.lower() or "sign in" in error_message.lower():
                        tqdm.write(f"{Fore.RED}⚠️ [{task_id}] 检测到人机验证限制")
                        return False
                        
                    if attempt < CONFIG["max_retries"] - 1:
                        delay = 2 ** (attempt + 1)
                        await asyncio.sleep(delay)
                    else:
                        tqdm.write(f"{Fore.RED}⚠️ [{task_id}] 放弃下载")
                        return False

    except Exception as e:
        tqdm.write(f"{Fore.RED}⚠️ [{task_id}] 异常: {str(e)}")
        return False
    finally:
        # 确保进度条被正确关闭
        if progress_bar and hasattr(progress_bar, 'close'):
            try:
                progress_bar.close()
            except:
                pass
                
        # 确保状态栏被正确关闭
        if status_bar and hasattr(status_bar, 'close'):
            try:
                status_bar.close()
            except:
                pass


# 已下载视频记录
def load_downloaded_videos() -> set:
    """加载已下载视频记录"""
    record_file = CONFIG["downloaded_record"]
    if os.path.exists(record_file):
        try:
            with open(record_file, 'r', encoding='utf-8') as f:
                return set(json.load(f))
        except Exception as e:
            logger.error(f"读取下载记录失败: {str(e)}")
    return set()

def save_downloaded_video(url: str):
    """保存已下载视频记录"""
    record_file = CONFIG["downloaded_record"]
    downloaded = load_downloaded_videos()
    downloaded.add(url)
    try:
        # 确保目录存在
        pathlib.Path(record_file).parent.mkdir(parents=True, exist_ok=True)
        with open(record_file, 'w', encoding='utf-8') as f:
            json.dump(list(downloaded), f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"保存下载记录失败: {str(e)}")


async def download_manager():
    """管理并发下载（使用工作队列模式，保持固定数量的进度条）"""
    # 加载已下载视频记录
    downloaded_videos = load_downloaded_videos()
    
    # 准备跳过的视频和需要下载的视频
    skipped_urls = [url for url in url_list if url in downloaded_videos]
    to_download_urls = [url for url in url_list if url not in downloaded_videos]
    
    if skipped_urls:
        logger.info(f"\n{Fore.YELLOW}跳过 {len(skipped_urls)} 个已下载视频")
        if CONFIG["debug_mode"]:
            for url in skipped_urls[:5]:  # 只显示前5个
                logger.debug(f"{Fore.YELLOW}跳过: {url} - {url_list[url]}")
            if len(skipped_urls) > 5:
                logger.debug(f"{Fore.YELLOW}... 还有 {len(skipped_urls)-5} 个已跳过的视频")
    
    if not to_download_urls:
        logger.info(f"{Fore.GREEN}{Style.BRIGHT}所有视频都已下载完成！")
        return
        
    logger.info(f"\n{Fore.WHITE}{Style.BRIGHT}开始下载 {len(to_download_urls)} 个新视频")
    
    # 预留固定的进度条空间
    print("\n" * (CONFIG["max_workers"] + 2))  # 多加2行用于总进度和其他信息
    
    # 创建下载队列
    queue = asyncio.Queue()
    
    # 将所有URL放入队列
    for url in to_download_urls:
        await queue.put(url)
    
    # 任务计数
    total_tasks = len(to_download_urls)
    completed_tasks = 0
    success_count = 0
    fail_count = 0
    
    # 创建彩色总进度条
    # 为总进度条创建彩色描述
    rainbow_text = ""
    rainbow_colors = DownloadProgressBar.TEXT_COLORS
    text = "总进度"
    for i, char in enumerate(text):
        rainbow_text += f"{rainbow_colors[i % len(rainbow_colors)]}{char}"
    rainbow_text += Style.RESET_ALL
    
    # 随机选择一个进度条颜色
    progress_colors = ['green', 'red', 'yellow', 'blue', 'magenta', 'cyan']
    total_bar_color = random.choice(progress_colors)
    
    # 创建总进度条
    total_progress = tqdm(
        total=total_tasks,
        desc=rainbow_text,
        position=CONFIG["max_workers"],  # 放在所有下载进度条下面
        bar_format='{desc}: {percentage:3.0f}%|{bar}| {n}/{total} [剩余:{remaining}]',
        leave=True,
        colour=total_bar_color,  # 使用tqdm原生的颜色支持
        ascii="━━░"  # 使用不同的进度条字符，更醒目
    )
    
    # 用于保护计数器的锁
    counter_lock = asyncio.Lock()
    
    # 创建工作线程函数
    async def worker(position):
        nonlocal completed_tasks, success_count, fail_count
        task_id = 0
        
        while not queue.empty():
            try:
                # 获取下一个URL
                url = await queue.get()
                
                # 安全地增加全局任务ID
                async with counter_lock:
                    task_id = completed_tasks + 1
                
                # 获取标题
                title = url_list[url]
                
                # 下载视频 - 在固定的位置显示进度条
                success = await download_video(url, title, task_id, position)
                
                # 安全地更新完成计数
                async with counter_lock:
                    completed_tasks += 1
                    if success:
                        success_count += 1
                    else:
                        fail_count += 1
                    
                    # 更新总进度条
                    total_progress.update(1)
                
                # 标记任务完成
                queue.task_done()
                
            except Exception as e:
                logger.error(f"{Fore.RED}工作线程 {position} 异常: {str(e)}")
    
    # 创建工作线程
    workers = []
    worker_count = min(CONFIG["max_workers"], len(to_download_urls))
    
    for i in range(worker_count):
        # 工作线程ID从0开始，用于定位进度条位置
        workers.append(asyncio.create_task(worker(i)))
    
    # 等待所有任务完成
    await asyncio.gather(*workers)
    
    # 关闭总进度条
    total_progress.close()
    
    # 显示漂亮的结果统计
    logger.info(f"\n{Fore.CYAN}{Style.BRIGHT}{'=' * 50}")
    logger.info(f"{Fore.CYAN}{Style.BRIGHT}下载任务完成统计")
    logger.info(f"{Fore.WHITE}总任务数: {Style.BRIGHT}{len(url_list)}")
    logger.info(f"{Fore.GREEN}成功下载: {Style.BRIGHT}{success_count}")
    logger.info(f"{Fore.RED}下载失败: {Style.BRIGHT}{fail_count}")
    logger.info(f"{Fore.YELLOW}已跳过的: {Style.BRIGHT}{len(skipped_urls)}")
    logger.info(f"{Fore.CYAN}{Style.BRIGHT}{'=' * 50}")


# 漂亮的应用程序横幅
def print_banner():
    banner = f"""
{Fore.CYAN}{Style.BRIGHT}╔══════════════════════════════════════════════════════════╗
║                                                          ║
║  {Fore.YELLOW}▶ {Fore.WHITE}YT+ Video Downloader v2.0{Fore.CYAN}                             ║
║                                                          ║
║  {Fore.WHITE}高效批量下载视频，支持YouTube和Bilibili{Fore.CYAN}                  ║
║                                                          ║
╚══════════════════════════════════════════════════════════╝{Style.RESET_ALL}
"""
    print(banner)

def main():
    """程序入口点"""
    try:
        # 打印漂亮的横幅
        print_banner()
        
        # 处理命令行参数
        if len(sys.argv) > 1:
            for arg in sys.argv[1:]:
                if arg.lower() == '--no-progress-bar':
                    CONFIG['use_progress_bar'] = False
                    logger.info(f"{Fore.YELLOW}已禁用进度条显示")
                elif arg.lower() == '--debug':
                    CONFIG['debug_mode'] = True
                    logger.setLevel(logging.DEBUG)
                    logger.info(f"{Fore.YELLOW}已启用调试模式")
        
        # 打印加载的URL信息
        logger.info(f"{Fore.GREEN}已从 {Fore.WHITE}{Style.BRIGHT}{CONFIG['url_list_file']}{Style.RESET_ALL}{Fore.GREEN} 加载 {Fore.WHITE}{Style.BRIGHT}{len(url_list)}{Style.RESET_ALL}{Fore.GREEN} 个URL")
        
        # 打印分隔线和配置信息
        logger.info(f"{Fore.CYAN}{Style.BRIGHT}{'=' * 50}")
        logger.info(f"{Fore.CYAN}{Style.BRIGHT}视频下载任务启动")
        logger.info(f"{Fore.WHITE}总任务数: {Fore.WHITE}{Style.BRIGHT}{len(url_list)}")
        logger.info(f"{Fore.WHITE}并行下载数: {Fore.WHITE}{Style.BRIGHT}{CONFIG['max_workers']}")
        
        # 加载已下载记录
        downloaded_videos = load_downloaded_videos()
        logger.info(f"{Fore.WHITE}已下载视频数: {Fore.WHITE}{Style.BRIGHT}{len(downloaded_videos)}")
        logger.info(f"{Fore.WHITE}待下载视频数: {Fore.WHITE}{Style.BRIGHT}{len(url_list) - len([url for url in url_list if url in downloaded_videos])}")
        logger.info(f"{Fore.CYAN}{Style.BRIGHT}{'=' * 50}")
        
        # 运行异步下载管理器
        asyncio.run(download_manager())
    except KeyboardInterrupt:
        logger.info(f"\n{Fore.YELLOW}{Style.BRIGHT}用户中断，正在退出...")
    except Exception as e:
        logger.exception(f"{Fore.RED}{Style.BRIGHT}程序异常: {str(e)}")
    finally:
        logger.info(f"{Fore.CYAN}{Style.BRIGHT}程序已退出")


# 进度条管理器
class DownloadProgressBar:
    # 可用的进度条颜色和样式组合
    BAR_STYLES = [
        {'colour': 'green', 'bar_format': '{desc} {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{rate_fmt}]'},
        {'colour': 'red', 'bar_format': '{desc} {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{rate_fmt}]'},
        {'colour': 'yellow', 'bar_format': '{desc} {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{rate_fmt}]'},
        {'colour': 'blue', 'bar_format': '{desc} {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{rate_fmt}]'},
        {'colour': 'magenta', 'bar_format': '{desc} {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{rate_fmt}]'},
        {'colour': 'cyan', 'bar_format': '{desc} {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{rate_fmt}]'},
    ]
    
    # 可用的前缀颜色 - 与tqdm颜色区分，用于文本显示
    TEXT_COLORS = [
        Fore.LIGHTGREEN_EX,
        Fore.LIGHTRED_EX,
        Fore.LIGHTYELLOW_EX,
        Fore.LIGHTBLUE_EX,
        Fore.LIGHTMAGENTA_EX,
        Fore.LIGHTCYAN_EX,
    ]
    
    def __init__(self, task_id, total_tasks, position=0):
        self.task_id = task_id
        self.total_tasks = total_tasks
        self.position = position  # 工作线程ID (0-based) - 固定进度条位置
        self.pbar = None
        self.downloaded_bytes = 0
        self.total_bytes = 0
        self.filename = ""
        self.use_progress_bar = CONFIG["use_progress_bar"]
        self.debug_mode = CONFIG["debug_mode"]
        self.no_color = False  # 是否禁用颜色
        self.leave_progress_bar = True  # 保留进度条，防止被清除
        
        # 为进度条随机选择一个样式和颜色
        self.bar_style = random.choice(self.BAR_STYLES)
        self.text_color = random.choice(self.TEXT_COLORS)
        
        # 只在使用进度条模式下获取终端宽度
        if self.use_progress_bar:
            try:
                self.terminal_width = shutil.get_terminal_size().columns
            except:
                self.terminal_width = 120  # 默认宽度更宽

    def create_progressbar(self, total_bytes, d):
        """创建下载进度条"""
        try:
            # 保存总字节数并初始化已下载字节数
            self.total_bytes = total_bytes
            self.downloaded_bytes = 0
            
            # 从下载信息中获取文件名
            self.filename = os.path.basename(d.get('filename', '未知文件'))
            
            # 尝试获取终端宽度
            try:
                terminal_width = shutil.get_terminal_size().columns
            except:
                terminal_width = 80
            
            # 处理文件名显示
            max_filename_length = 20
            if len(self.filename) > max_filename_length:
                self.filename_short = self.filename[:max_filename_length-3] + "..."
            else:
                self.filename_short = self.filename
                
            # 创建进度条前缀 - 使用文本颜色
            desc = f"{self.text_color}下载中 [{self.task_id}/{self.total_tasks}]{Style.RESET_ALL}"
            
            # 关闭之前可能存在的进度条
            if self.pbar is not None:
                self.pbar.close()
                self.pbar = None
            
            # 创建tqdm进度条 - 使用固定位置和选定颜色
            self.pbar = tqdm(
                total=total_bytes, 
                unit='B',
                unit_scale=True,
                unit_divisor=1024,
                desc=desc,
                initial=0,
                leave=True,  # 保留进度条，防止被其他线程清除
                position=self.position,  # 固定进度条位置
                bar_format=self.bar_style['bar_format'],
                colour=self.bar_style['colour'],  # 使用tqdm原生的颜色支持
                disable=not self.use_progress_bar
            )
            
        except Exception as e:
            # 出错时禁用进度条
            self.use_progress_bar = False
            if self.debug_mode:
                logger.debug(f"创建进度条失败: {str(e)}")

    def hook(self, d):
        """下载进度回调函数"""
        if not self.use_progress_bar:
            return
            
        try:
            # 检查下载信息是否有效
            if d is None:
                return
                
            status = d.get('status', '')
            
            # 处理下载中状态
            if status == 'downloading':
                # 获取下载信息
                downloaded_bytes = d.get('downloaded_bytes', 0)
                total_bytes = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                
                # 更新文件名
                if 'filename' in d:
                    filename = os.path.basename(d['filename'])
                    if filename != self.filename:
                        self.filename = filename
                        # 处理文件名显示
                        max_filename_length = 20
                        if len(self.filename) > max_filename_length:
                            self.filename_short = self.filename[:max_filename_length-3] + "..."
                        else:
                            self.filename_short = self.filename
                
                # 首次更新或进度条不存在时创建新的进度条
                if self.pbar is None and total_bytes > 0:
                    self.create_progressbar(total_bytes, d)
                
                # 更新进度
                if self.pbar is not None:
                    # 计算增量
                    increment = downloaded_bytes - self.downloaded_bytes
                    if increment > 0:
                        self.update_progressbar(increment)
                        self.downloaded_bytes = downloaded_bytes
                        
            # 下载完成
            elif status == 'finished':
                # 确保进度条显示100%
                if self.pbar is not None:
                    # 计算剩余字节数并更新
                    remaining = max(0, self.total_bytes - self.downloaded_bytes)
                    if remaining > 0:
                        self.pbar.update(remaining)
                    
                    # 强制更新到100%
                    self.pbar.n = self.pbar.total
                    self.pbar.set_description(f"{Fore.GREEN}已完成 [{self.task_id}/{self.total_tasks}]{Style.RESET_ALL}")
                    self.pbar.refresh()
                    
                    # 不关闭进度条，稍后在download_video中手动关闭，以便显示成功消息
            
            # 处理错误状态
            elif status == 'error':
                if self.pbar is not None:
                    self.pbar.set_description(f"{Fore.RED}下载错误 [{self.task_id}/{self.total_tasks}]{Style.RESET_ALL}")
                    # 稍后在download_video中手动关闭，以便显示错误消息
        
        except Exception as e:
            # 发生异常时禁用进度条
            self.use_progress_bar = False
            if self.debug_mode:
                logger.debug(f"进度条回调错误: {str(e)}")

    def update_progressbar(self, increment):
        """更新进度条"""
        try:
            if self.pbar is not None:
                # 更新进度
                self.pbar.update(increment)
                self.pbar.refresh()  # 强制刷新显示
        except Exception as e:
            # 更新出错时禁用进度条
            self.use_progress_bar = False
            if self.debug_mode:
                logger.debug(f"更新进度条错误: {str(e)}")

    def close(self):
        """关闭进度条"""
        if self.pbar:
            try:
                # 确保100%完成
                if self.pbar.n < self.pbar.total and self.pbar.total > 0:
                    self.pbar.n = self.pbar.total
                    self.pbar.refresh()
                
                # 先改变描述再关闭
                self.pbar.set_description(f"{Fore.GREEN}已完成 [{self.task_id}/{self.total_tasks}]{Style.RESET_ALL}")
                self.pbar.refresh()
                
                # 关闭进度条
                self.pbar.close()
                self.pbar = None
            except Exception as e:
                if self.debug_mode:
                    logger.debug(f"关闭进度条错误: {str(e)}")


# 文件大小格式化
def get_human_readable_size(size_bytes):
    """Convert bytes to human readable format"""
    if size_bytes < 0:
        raise ValueError("Invalid size: negative value")
    
    units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
    unit_index = 0
    
    while size_bytes >= 1024 and unit_index < len(units) - 1:
        size_bytes /= 1024
        unit_index += 1
    
    return f"{size_bytes:.2f} {units[unit_index]}"


if __name__ == "__main__":
    main()
