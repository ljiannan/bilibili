"""哔哩哔哩合集视频链接批量采集脚本，适配所有电脑，配置区集中管理"""
import requests
import os
import re

# ====================== 用户配置区 ======================
# 只需填写合集页面URL（支持新版/lists/4512129?type=season 和老版/channel/seriesdetail?sid=xxx）
COLLECTION_URL = "https://space.bilibili.com/19071708/lists/1942656?type=season"
# 必须填写你的B站cookie（建议用Chrome插件导出，粘贴到此处，注意不要换行）
COOKIE = r"C:\Users\DELL\Desktop\bilibili.txt"  # 例：'SESSDATA=xxx; bili_jct=xxx; ...'
# 输出文件名（当前目录下）
OUTPUT_FILE = "bilibili_collection_links.csv"
# 采集起止页码
START_PAGE = 1
END_PAGE = 5
# ======================================================

# 自动清除代理环境变量，兼容所有电脑
os.environ.pop("HTTP_PROXY", None)
os.environ.pop("HTTPS_PROXY", None)
os.environ.pop("http_proxy", None)
os.environ.pop("https_proxy", None)

headers = {
    'cookie': COOKIE,
    'referer': 'https://space.bilibili.com/',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36 Edg/134.0.0.0'
}

def parse_mid_and_seasonid(url):
    mid_match = re.search(r'space\.bilibili\.com/(\d+)', url)
    # 支持新版/lists/4512129?type=season 和老版/channel/seriesdetail?sid=xxx
    seasonid_match = re.search(r'/lists/(\d+)', url)
    if not seasonid_match:
        seasonid_match = re.search(r'sid=(\d+)', url)
    if mid_match and seasonid_match:
        return mid_match.group(1), seasonid_match.group(1)
    else:
        return None, None

mid, season_id = parse_mid_and_seasonid(COLLECTION_URL)
if not mid or not season_id:
    print("合集URL格式不正确，请检查！")
    exit(1)

url = f"mid={mid}&season_id={season_id}"

def tougao(href):
    reponse = requests.get(href,headers=headers)
    # print(reponse.text)
    if reponse.status_code == 200:
        print(reponse.text)
        jsondata = reponse.json()
        print(jsondata)
        archives = jsondata["data"]["list"]["vlist"]
        # print(archives)
        for i in archives:
            bvid = i["bvid"]
        #     # print(bvid)
        #     # title = i["title"]
            href = 'https://www.bilibili.com/video/' + bvid + '/?spm_id_from=333.1387.collection.video_card.click'
            print(href)
            with open(OUTPUT_FILE, 'a', encoding='utf-8') as f:
                f.write(href)
                f.write('\n')
        print('主页视频链接已写入csv文件')
    else:
        print("页面获取失败")

def heji(href, x, y):
    a = href
    seen_bvids = set()
    for page in range(x, y + 1):
        api_url = f'https://api.bilibili.com/x/polymer/web-space/seasons_archives_list?{a}&sort_reverse=false&page_size=30&page_num={page}&web_location=333.1387'
        respons = requests.get(api_url, headers=headers)
        if respons.status_code == 200:
            try:
                json_data = respons.json()
            except Exception as e:
                print(f"第{page}页解析json失败，返回内容：", respons.text)
                continue
            if not json_data or "data" not in json_data or not json_data["data"] or "archives" not in json_data["data"]:
                print(f"第{page}页接口返回异常，内容：", respons.text)
                print(f"请检查mid和season_id参数是否正确，当前请求URL：{api_url}")
                continue
            archives = json_data["data"]["archives"]
            if not archives:
                print(f"第{page}页无数据，自动终止采集。")
                break
            new_count = 0
            for i in archives:
                bvid = i["bvid"]
                if bvid in seen_bvids:
                    continue
                seen_bvids.add(bvid)
                href = f'https://www.bilibili.com/video/{bvid}/?spm_id_from=333.1387.collection.video_card.click'
                print(href)
                with open(OUTPUT_FILE, 'a', encoding='utf-8') as f:
                    f.write(href)
                    f.write("\n")
                new_count += 1
            print(f"第{page}页合集链接已写入{OUTPUT_FILE}，新增{new_count}条")
        else:
            print(f"第{page}页合集链接获取失败")

if __name__ == '__main__':
    # 运行前自动清空输出文件，防止重复
    open(OUTPUT_FILE, 'w', encoding='utf-8').close()
    heji(url, START_PAGE, END_PAGE)
