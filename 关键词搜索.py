import os
import re
import sys
import time
import requests
import hashlib
from functools import reduce
from tqdm import tqdm
from loguru import logger
import urllib.parse

# --- 配置参数 ---
KEYWORD = '自然'
START_PAGE = 1
END_PAGE = 30
REQUEST_DELAY = 15  # 请求延迟(秒)
COLLECTED_MIDS_FILE = r'Z:\数据采集组\mid_one.txt'#指定存储已收集MID的文件路径
PROCESSED_MIDS_FILE = r'Z:\数据采集组\mid_two.txt'#指定存储已处理（已完成）MID的文件路径
TEMP_MIDS_FILE = r'Z:\数据采集组\mid_processing.txt'#指定存储正在处理的MID的文件路径
OUTPUT_CSV_FILE = r'./bilibili.csv'#指定存储最终视频链接的CSV文件路径
MAX_RETRIES = 3
PAGE_SIZE = 30

# B站Cookie配置
HEADERS = {
    'cookie': "buvid3=63903C2A-0549-43EB-E7E0-8DC374D15FB463220infoc; b_nut=1753085463; _uuid=EDFD799B-4625-8C47-F792-A3DD658E4CBF62169infoc; enable_web_push=DISABLE; home_feed_column=5; buvid4=CC6475CE-091D-50CC-EC59-79A09882321963662-025072116-pk1atL693e%2FEXobScNyTag%3D%3D; buvid_fp=f1558038539db8076a20b47c86a32181; rpdid=|(Yu|mRmYuY0J'u~lJ|)lRYl; browser_resolution=2552-1314; SESSDATA=8767e538%2C1768989844%2C39f17%2A72CjC-1kNA9SHZJ-N2h2KmK3BxEQuXj2Ju1qKQbr_EdOa2ZiUcV2kj5xVovxncjAO65rYSVmtTSXVXUzVza2VqUXdIWWNYblgwR2owdXZxMHNqNWlyTzFSME9LUEdPR0ZEZVRhcDZ6QXJjaWxzenc1TnptbnVhN2g4RGpXWG5rb0t4dkJtc21OejVnIIEC; bili_jct=288d6a7ad377a4bf21cdf43c37fd2f79; DedeUserID=476990344; DedeUserID__ckMd5=afa6a27510b63e3e; sid=4q0m554i; bili_ticket=eyJhbGciOiJIUzI1NiIsImtpZCI6InMwMyIsInR5cCI6IkpXVCJ9.eyJleHAiOjE7NTM5MjM4NzAsImlhdCI6MTc1MzY2NDYxMCwicGx0IjotMX0.yYsor77-oTPW6Q9QbofqzpK-D_k1fX0FoJnIgugr_CY; bili_ticket_expires=1753923810; b_lsid=1210E7753_1984EA71325; bsource=search_bing; bmg_af_switch=1; bmg_src_def_domain=i0.hdslb.com; theme-tip-show=SHOWED; CURRENT_FNVAL=4048",
    'referer': 'https://www.bilibili.com/',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'origin': 'https://www.bilibili.com'
}

# --- WBI签名算法 ---
mixinKeyEncTab = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
    33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40,
    61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11,
    36, 20, 34, 44, 16
]


def get_mixin_key(orig: str):
    return reduce(lambda s, i: s + orig[i], mixinKeyEncTab, '')[:32]


def get_wbi_keys():
    try:
        resp = requests.get('https://api.bilibili.com/x/web-interface/nav', headers=HEADERS)
        resp.raise_for_status()
        json_content = resp.json()
        img_url: str = json_content['data']['wbi_img']['img_url']
        sub_url: str = json_content['data']['wbi_img']['sub_url']
        img_key = img_url.rsplit('/', 1)[1].split('.')[0]
        sub_key = sub_url.rsplit('/', 1)[1].split('.')[0]
        return get_mixin_key(img_key + sub_key)
    except Exception:
        logger.error("获取WBI keys失败")
        return None


def sign_params(params: dict, wbi_key: str):
    params['wts'] = int(time.time())
    query = '&'.join([f'{key}={value}' for key, value in sorted(params.items())])
    w_rid = hashlib.md5((query + wbi_key).encode()).hexdigest()
    params['w_rid'] = w_rid
    return params


# --- MID采集功能 ---
def load_mids(filename):
    """加载MID文件"""
    if not os.path.exists(filename):
        return set()
    with open(filename, 'r', encoding='utf-8') as f:
        return set(line.strip() for line in f if line.strip())


def save_mids(filename, mids):
    """保存MID到文件"""
    with open(filename, 'a', encoding='utf-8') as f:
        for mid in mids:
            f.write(f"{mid}\n")


def remove_mid_from_file(filename, mid):
    """从文件中删除指定的MID"""
    if not os.path.exists(filename):
        return False

    try:
        with open(filename, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        with open(filename, 'w', encoding='utf-8') as f:
            for line in lines:
                if line.strip() != mid:
                    f.write(line)
        return True
    except Exception as e:
        logger.error(f"从文件 {filename} 删除MID {mid} 失败: {e}")
        return False


def move_mid_to_temp(mid):
    """将MID移动到临时文件"""
    try:
        # 从原文件删除
        if remove_mid_from_file(COLLECTED_MIDS_FILE, mid):
            # 添加到临时文件
            with open(TEMP_MIDS_FILE, 'a', encoding='utf-8') as f:
                f.write(f"{mid}\n")
            return True
        return False
    except Exception as e:
        logger.error(f"移动MID {mid} 到临时文件失败: {e}")
        return False


def finalize_mid_processing(mid, success):
    """根据处理结果将MID移动到最终位置"""
    try:
        # 从临时文件删除
        if not remove_mid_from_file(TEMP_MIDS_FILE, mid):
            return False

        # 根据处理结果移动到不同文件
        if success:
            save_mids(PROCESSED_MIDS_FILE, [mid])
            logger.info(f"已将MID {mid} 移动到完成文件 {PROCESSED_MIDS_FILE}")
        else:
            save_mids(COLLECTED_MIDS_FILE, [mid])
            logger.info(f"已将MID {mid} 移回原文件 {COLLECTED_MIDS_FILE}")
        return True
    except Exception as e:
        logger.error(f"最终处理MID {mid} 失败: {e}")
        return False


def collect_mids_from_search():
    """从B站搜索收集MID"""
    existing_mids = load_mids(COLLECTED_MIDS_FILE) | load_mids(PROCESSED_MIDS_FILE) | load_mids(TEMP_MIDS_FILE)
    new_mids = set()

    logger.info(f"开始采集 {KEYWORD} 的UP主MID (第{START_PAGE}到{END_PAGE}页)")

    for page in tqdm(range(START_PAGE, END_PAGE + 1), desc="搜索进度"):
        time.sleep(REQUEST_DELAY)
        url = f'https://api.bilibili.com/x/web-interface/search/type?search_type=video&keyword={KEYWORD}&page={page}'

        try:
            response = requests.get(url, headers=HEADERS)
            response.encoding = 'utf-8'
            response.raise_for_status()

            data = response.json()
            if data.get('code') == 0:
                for item in data.get('data', {}).get('result', []):
                    mid = str(item.get('mid', ''))
                    if mid and mid not in existing_mids and mid not in new_mids:
                        new_mids.add(mid)
            else:
                logger.error(f"第 {page} 页API返回错误: {data.get('message')}")

        except Exception as e:
            logger.error(f"第 {page} 页采集失败: {str(e)}")

    if new_mids:
        save_mids(COLLECTED_MIDS_FILE, new_mids)
        logger.success(f"新增 {len(new_mids)} 个MID到 {COLLECTED_MIDS_FILE}")
        return new_mids
    else:
        logger.info("没有发现新的MID")
        return set()


# --- 视频链接获取功能 ---
def get_up_name(mid):
    """获取UP主昵称"""
    try:
        url = f'https://api.bilibili.com/x/space/acc/info?mid={mid}'
        response = requests.get(url, headers=HEADERS, timeout=20)
        response.raise_for_status()
        data = response.json()
        if data.get('code') == 0:
            return data.get('data', {}).get('name', f'UP主_{mid}')
        return f'UP主_{mid}'
    except Exception:
        return f'UP主_{mid}'


def get_up_videos(mid, wbi_key=None):
    """获取指定UP主的视频列表"""
    videos = []
    page_num = 1
    api_url = "https://api.bilibili.com/x/space/wbi/arc/search"

    while True:
        params = {
            'mid': mid, 'ps': PAGE_SIZE, 'tid': 0, 'pn': page_num, 'keyword': '',
            'order': 'pubdate', 'platform': 'web', 'web_location': '1550101',
            'order_avoided': 'true',
        }

        if wbi_key:
            params = sign_params(params, wbi_key)

        try:
            response = requests.get(api_url, params=params, headers=HEADERS, timeout=20)
            response.raise_for_status()
            data = response.json()

            if data.get('code') != 0:
                logger.error(f"获取UP主 {mid} 视频失败: {data.get('message')}")
                break

            video_list = data.get('data', {}).get('list', {}).get('vlist', [])
            if not video_list:
                break

            videos.extend([{
                'bvid': item.get('bvid'),
                'title': item.get('title', '无标题').replace(',', '，').replace('\n', ' ').strip(),
                'url': f"https://www.bilibili.com/video/{item.get('bvid')}/"
            } for item in video_list])

            page_info = data.get('data', {}).get('page', {})
            if len(videos) >= page_info.get('count', 0):
                break

            page_num += 1
            time.sleep(REQUEST_DELAY)
        except Exception as e:
            logger.error(f"获取UP主 {mid} 视频出错: {e}")
            break

    return videos


def write_to_csv(mid, up_name, videos):
    """按照指定格式写入CSV文件"""
    try:
        with open(OUTPUT_CSV_FILE, 'a', encoding='utf-8') as f:
            f.write(f"\n{up_name}\n")
            for video in videos:
                f.write(f"{video['url'] + '?spm_id_from=333.1387.collection.video_card.click'}\n")
        return True
    except Exception as e:
        logger.error(f"写入CSV文件失败: {e}")
        return False


def process_existing_mids(wbi_key):
    """处理已有的MID"""
    logger.info("\n=== 开始处理已有UP主视频 ===")

    while True:
        # 每次重新加载文件，获取最新的MID列表
        collected_mids = load_mids(COLLECTED_MIDS_FILE)
        if not collected_mids:
            logger.info("没有更多MID需要处理")
            break

        # 获取一个MID进行处理
        mid = collected_mids.pop()

        # 将MID移动到临时文件
        if not move_mid_to_temp(mid):
            logger.error(f"无法移动MID {mid} 到临时文件，跳过处理")
            continue

        try:
            # 获取UP主信息
            up_name = get_up_name(mid)
            logger.info(f"\n处理UP主: {up_name} (MID: {mid})")

            # 获取视频列表
            videos = get_up_videos(mid, wbi_key)
            success = False

            if videos:
                # 写入CSV
                if write_to_csv(mid, up_name, videos):
                    logger.success(f"成功写入 {len(videos)} 个视频链接")
                    success = True
                else:
                    logger.error(f"写入UP主 {up_name} 视频链接失败")
            else:
                logger.warning(f"未获取到UP主 {up_name} 的视频")

            # 根据处理结果移动MID到最终位置
            finalize_mid_processing(mid, success)

            time.sleep(REQUEST_DELAY)

        except Exception as e:
            logger.error(f"处理MID {mid} 时出错: {e}")
            # 出错时也将MID移回原文件
            finalize_mid_processing(mid, False)
            continue


# --- 主流程 ---
def main():
    # 初始化日志
    logger.remove()
    logger.add(
        sys.stdout,
        colorize=True,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
        level="INFO"
    )

    # 确保目录存在
    os.makedirs(os.path.dirname(COLLECTED_MIDS_FILE), exist_ok=True)
    os.makedirs(os.path.dirname(OUTPUT_CSV_FILE), exist_ok=True)

    # 初始化CSV文件
    if not os.path.exists(OUTPUT_CSV_FILE):
        with open(OUTPUT_CSV_FILE, 'a', encoding='utf-8') as f:
            f.write("B站视频链接采集结果\n")

    # 1. 采集MID
    logger.info("=== 开始采集UP主MID ===")
    new_mids = collect_mids_from_search()

    # 2. 获取WBI签名密钥
    logger.info("\n=== 获取WBI签名密钥 ===")
    wbi_key = get_wbi_keys()
    if not wbi_key:
        logger.warning("将不使用WBI签名，可能会影响部分UP主视频获取")

    # 3. 处理MID获取视频
    if new_mids:
        logger.info("\n=== 开始处理新采集的UP主视频 ===")
        process_existing_mids(wbi_key)
    else:
        logger.info("\n=== 没有新采集到MID，开始处理已有MID ===")
        process_existing_mids(wbi_key)

    logger.success("\n=== 所有任务完成 ===")


if __name__ == '__main__':
    main()