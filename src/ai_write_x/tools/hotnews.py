import requests
import random
import time
from typing import Any, Optional, List, Dict
from bs4 import BeautifulSoup

from src.ai_write_x.utils import log

# 平台名称映射
PLATFORMS = [
    {"name": "微博", "zhiwei_id": "weibo", "tophub_id": "s.weibo.com", "viki_id": "weibo"},
    {"name": "抖音", "zhiwei_id": "douyin", "tophub_id": "douyin.com", "viki_id": "douyin"},
    {"name": "哔哩哔哩", "zhiwei_id": "bilibili", "tophub_id": "bilibili.com", "viki_id": "bili"},
    {"name": "今日头条", "zhiwei_id": "toutiao", "tophub_id": "toutiao.com", "viki_id": "toutiao"},
    {"name": "百度热点", "zhiwei_id": "baidu", "tophub_id": "baidu.com", "viki_id": "baidu"},
    {"name": "小红书", "zhiwei_id": "little-red-book", "tophub_id": None, "viki_id": "xiaohongshu"},
    {"name": "快手", "zhiwei_id": "kuaishou", "tophub_id": None, "viki_id": "kuaishou"},
    {"name": "虎扑", "zhiwei_id": None, "tophub_id": "hupu.com", "viki_id": None},
    {"name": "豆瓣电影", "zhiwei_id": None, "tophub_id": None, "viki_id": None},
    {"name": "澎湃新闻", "zhiwei_id": None, "tophub_id": "thepaper.cn", "viki_id": None},
    {"name": "知乎热榜", "zhiwei_id": "zhihu", "tophub_id": "zhihu.com", "viki_id": "zhihu"},
    {"name": "36氪", "zhiwei_id": None, "tophub_id": None, "viki_id": None},
]

# 知微数据支持的平台
ZHIWEI_PLATFORMS = [p["zhiwei_id"] for p in PLATFORMS if p.get("zhiwei_id")]

# tophub 支持的平台
TOPHUB_PLATFORMS = [p["tophub_id"] for p in PLATFORMS if p["tophub_id"]]

# 60s.viki.moe 统一API支持的平台
VIKI_PLATFORMS = {p["viki_id"]: p["name"] for p in PLATFORMS if p.get("viki_id")}

# 通用请求头
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


def get_viki_hotnews(platform: str) -> Optional[List[Dict]]:
    """通过 60s.viki.moe 统一API获取热榜（优先级最高，覆盖最广）"""
    viki_map = {
        "微博": "weibo", "抖音": "douyin", "哔哩哔哩": "bili",
        "今日头条": "toutiao", "百度热点": "baidu", "知乎热榜": "zhihu",
        "小红书": "xiaohongshu", "快手": "kuaishou",
    }
    viki_id = viki_map.get(platform)
    if not viki_id:
        return None

    try:
        url = f"https://60s.viki.moe/v2/{viki_id}"
        r = requests.get(url, headers={"User-Agent": _UA}, timeout=10)
        data = r.json()
        if data.get("code") == 200 and isinstance(data.get("data"), list):
            items = []
            for item in data["data"]:
                title = item.get("title", "")
                if title:
                    items.append({"name": title, "rank": len(items) + 1, "url": item.get("link", "")})
            return items
    except Exception:
        pass
    return None


def get_bili_hotnews(cnt: int = 50) -> Optional[List[Dict]]:
    """B站热门 - 官方API"""
    try:
        r = requests.get("https://api.bilibili.com/x/web-interface/popular",
                         headers={"User-Agent": _UA}, timeout=10)
        data = r.json().get("data", {}).get("list", [])
        return [{"name": item.get("title", ""), "rank": i + 1, "url": f"https://www.bilibili.com/video/{item.get('bvid', '')}"}
                for i, item in enumerate(data[:cnt]) if item.get("title")]
    except Exception:
        return None


def get_douyin_hotnews(cnt: int = 50) -> Optional[List[Dict]]:
    """抖音热点 - 官方Web API"""
    try:
        r = requests.get("https://www.douyin.com/aweme/v1/web/hot/search/list/",
                         headers={"User-Agent": _UA, "Referer": "https://www.douyin.com/"}, timeout=10)
        data = r.json()
        word_list = data.get("word_list", [])
        return [{"name": item.get("word_info", {}).get("word", ""), "rank": i + 1,
                 "url": item.get("word_info", {}).get("scheme_url", "")}
                for i, item in enumerate(word_list[:cnt])
                if item.get("word_info", {}).get("word")]
    except Exception:
        return None


def get_baidu_official_hotnews(cnt: int = 50) -> Optional[List[Dict]]:
    """百度热搜 - 官方API"""
    try:
        r = requests.get("https://top.baidu.com/api/board?platform=wise&tab=realtime",
                         headers={"User-Agent": _UA}, timeout=10)
        data = r.json().get("data", {}).get("cards", [])
        # 解析百度热搜卡片结构
        items = []
        for card in data:
            for content in card.get("content", []):
                query = content.get("query", "")
                if query and query not in [i["name"] for i in items]:
                    items.append({"name": query, "rank": len(items) + 1,
                                  "url": content.get("url", "")})
                    if len(items) >= cnt:
                        break
            if len(items) >= cnt:
                break
        return items or None
    except Exception:
        return None


def get_toutiao_hotnews(cnt: int = 50) -> Optional[List[Dict]]:
    """今日头条热榜 - 官方API"""
    try:
        r = requests.get("https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc",
                         headers={"User-Agent": _UA}, timeout=10)
        data = r.json().get("data", [])
        return [{"name": item.get("Title", ""), "rank": i + 1, "url": item.get("Url", "")}
                for i, item in enumerate(data[:cnt]) if item.get("Title")]
    except Exception:
        return None


def get_weibo_official_hotnews(cnt: int = 50) -> Optional[List[Dict]]:
    """微博热搜 - 官方API"""
    try:
        r = requests.get("https://weibo.com/ajax/side/hotSearch",
                         headers={"User-Agent": _UA, "Referer": "https://weibo.com"}, timeout=10)
        data = r.json().get("data", {}).get("realtime", [])
        return [{"name": item.get("note", ""), "rank": item.get("rank", 0),
                 "url": item.get("url", "")} for item in data[:cnt] if item.get("note")]
    except Exception:
        return None


def get_douban_movie_hotnews(cnt: int = 20) -> Optional[List[Dict]]:
    """豆瓣电影榜单"""
    try:
        url = ("https://movie.douban.com/j/chart/top_list?"
               "type=24&interval_id=100%3A90&action=&start=0&limit={}".format(cnt))
        r = requests.get(url, headers={"User-Agent": _UA}, timeout=10)
        data = r.json()
        return [{"name": item.get("title", ""), "rank": i + 1,
                 "url": item.get("url", "")} for i, item in enumerate(data) if item.get("title")]
    except Exception:
        return None


def get_hupu_hotnews(cnt: int = 30) -> Optional[List[Dict]]:
    """虎扑步行街热门话题"""
    try:
        r = requests.get("https://bbs.hupu.com/", headers={"User-Agent": _UA}, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        items = []
        for el in soup.select(".titlelink")[:cnt]:
            text = el.get_text(strip=True)
            href = el.get("href", "")
            if text:
                items.append({"name": text, "rank": len(items) + 1,
                              "url": f"https://bbs.hupu.com{href}" if href.startswith("/") else href})
        return items or None
    except Exception:
        return None


def get_36kr_hotnews(cnt: int = 30) -> Optional[List[Dict]]:
    """36氪快讯"""
    try:
        r = requests.get("https://36kr.com/api/newsflash", headers={"User-Agent": _UA}, timeout=10)
        data = r.json().get("data", {}).get("items", [])
        return [{"name": item.get("title", ""), "rank": i + 1,
                 "url": f"https://36kr.com/newsflashes/{item.get('id', '')}"}
                for i, item in enumerate(data[:cnt]) if item.get("title")]
    except Exception:
        return None


def get_zhihu_new_api(cnt: int = 50) -> Optional[List[Dict]]:
    """知乎热榜 - 新版官方API"""
    try:
        r = requests.get("https://www.zhihu.com/api/v3/feed/topstory/hot-list-web",
                         headers={"User-Agent": _UA}, timeout=10)
        data = r.json().get("data", [])
        return [{"name": item.get("target", {}).get("title", ""), "rank": i + 1,
                 "url": item.get("target", {}).get("url", "").replace("api.", "www.").replace("/questions/", "/question/")}
                for i, item in enumerate(data[:cnt])
                if item.get("target", {}).get("title")]
    except Exception:
        return None


def get_zhiwei_hotnews(platform: str) -> Optional[List[Dict]]:
    """
    获取知微数据的热点数据
    参数 platform: 平台标识 (weibo, douyin, bilibili, toutiao, baidu, little-red-book, kuaishou, zhihu)
    返回格式: 列表数据，每个元素为热点条目字典，仅包含 name, rank, lastCount, url
    """
    api_url = f"https://trends.zhiweidata.com/hotSearchTrend/search/longTimeInListSearch?type={platform}&sortType=realTime"  # noqa 501
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",  # noqa 501
            "Referer": "https://trends.zhiweidata.com/",
        }
        response = requests.get(api_url, headers=headers, timeout=10)
        response.raise_for_status()

        data = response.json()
        if data.get("state") and isinstance(data.get("data"), list):
            return [
                {
                    "name": item.get("name", ""),
                    "rank": item.get("rank", 0),
                    "lastCount": item.get("lastCount", 0),
                    "url": item.get("url", ""),
                }
                for item in data["data"]
            ]
        return None
    except Exception as e:  # noqa 841
        return None


def get_tophub_hotnews(platform: str, cnt: int = 10) -> Optional[List[Dict]]:
    """
    获取 tophub.today 的热点数据
    参数 platform: 平台名称（中文，如“微博”）
    参数 tophub_id: tophub.today 的平台标识（如 s.weibo.com, zhihu.com）
    参数 cnt: 返回的新闻数量
    返回格式: 列表数据，每个元素为热点条目字典，包含 name, rank, lastCount
    """
    api_url = "https://tophub.today/"
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",  # noqa 501
        }
        response = requests.get(api_url, headers=headers, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        platform_divs = soup.find_all("div", class_="cc-cd")

        for div in platform_divs:
            platform_span = div.find("div", class_="cc-cd-lb").find("span")  # type: ignore
            if platform_span and platform_span.text.strip() == platform:  # type: ignore
                news_items = div.find_all("div", class_="cc-cd-cb-ll")[:cnt]  # type: ignore
                hotnews = []
                for item in news_items:
                    rank = item.find("span", class_="s").text.strip()  # type: ignore
                    title = item.find("span", class_="t").text.strip()  # type: ignore
                    engagement = item.find("span", class_="e")  # type: ignore
                    last_count = engagement.text.strip() if engagement else "0"
                    hotnews.append(
                        {
                            "name": title,
                            "rank": int(rank),
                            "lastCount": last_count,
                            "url": item.find("a")["href"] if item.find("a") else "",  # type: ignore
                        }
                    )
                return hotnews
        return None
    except Exception as e:  # noqa 841
        return None


def get_vvhan_hotnews() -> Optional[List[Dict]]:
    """
    获取 vvhan 的热点数据（作为备用）
    返回格式: [{"name": platform_name, "data": [...]}, ...]
    """
    api_url = "https://api.vvhan.com/api/hotlist/all"
    try:
        response = requests.get(api_url, timeout=10)
        response.raise_for_status()

        data = response.json()
        if data.get("success") and isinstance(data.get("data"), list):
            return data["data"]
        return None
    except Exception as e:  # noqa 841
        return None


def get_platform_news(platform: str, cnt: int = 10, exclude_topics: List[str] = None) -> List[str]:
    """
    获取指定平台的新闻标题，深度支持到 200 条

    优先级链：60s.viki.moe > 官方API > 知微数据 > tophub.today > vvhan
    """
    if exclude_topics is None:
        exclude_topics = []

    # 查找平台对应的标识
    platform_info = next((p for p in PLATFORMS if p["name"] == platform), None)
    if not platform_info:
        return []

    topics = []

    # 0. 优先尝试 60s.viki.moe 统一API（覆盖最广，最稳定）
    viki_data = get_viki_hotnews(platform)
    if viki_data:
        topics = [item.get("name", "") for item in viki_data[:200] if item.get("name")]

    # 1. 平台官方API直连（数据最新最准）
    if not topics:
        official_fetchers = {
            "哔哩哔哩": get_bili_hotnews,
            "抖音": get_douyin_hotnews,
            "百度热点": get_baidu_official_hotnews,
            "今日头条": get_toutiao_hotnews,
            "微博": get_weibo_official_hotnews,
            "知乎热榜": get_zhihu_new_api,
            "豆瓣电影": get_douban_movie_hotnews,
            "虎扑": get_hupu_hotnews,
            "36氪": get_36kr_hotnews,
        }
        fetcher = official_fetchers.get(platform)
        if fetcher:
            data = fetcher(200)
            if data:
                topics = [item.get("name", "") for item in data if item.get("name")]

    # 2. 回退到知微数据
    if not topics and platform_info["zhiwei_id"] in ZHIWEI_PLATFORMS:
        hotnews = get_zhiwei_hotnews(platform_info["zhiwei_id"])
        if hotnews:
            topics = [item.get("name", "") for item in hotnews[:200] if item.get("name")]

    # 3. 回退到 tophub.today
    if not topics and platform_info["tophub_id"] in TOPHUB_PLATFORMS:
        hotnews = get_tophub_hotnews(platform, 200)
        if hotnews:
            topics = [item.get("name", "") for item in hotnews[:200] if item.get("name")]

    # 4. 回退到 vvhan API
    if not topics:
        hotnews = get_vvhan_hotnews()
        if hotnews:
            platform_data = next((pf["data"] for pf in hotnews if pf["name"] == platform), [])
            topics = [item["title"] for item in platform_data[:200]]

    # 过滤掉已存在的话题
    filtered_topics = [t for t in topics if t not in exclude_topics]
    return filtered_topics


def get_authority_topics(limit: int = 50, exclude_topics: List[str] = None, min_time: float = None) -> List[str]:
    """
    从高权重源（BBC, NYTimes, WSJ等）抓取优质话题
    min_time: 限制仅返回该时间戳（秒）之后抓取的文章
    """
    if exclude_topics is None:
        exclude_topics = []
        
    try:
        from src.ai_write_x.tools.spider_runner import spider_runner
        import asyncio
        
        authority_spiders = ["bbc", "nytimes", "wsj", "zaobao", "xinhua"]
        all_authority_news = []
        
        # 为了避免异步嵌套复杂性，优先从 spider_data_manager 获取最近抓取的
        from src.ai_write_x.tools.spider_manager import spider_data_manager
        
        # V18 Fix: 直接获取所有文章，不限制source，避免source名称不匹配问题
        all_articles = spider_data_manager.get_articles(limit=limit*3, min_time=min_time)
        
        # 从权威源获取的文章优先
        authority_sources = ["BBC中文网", "纽约时报中文网", "华尔街日报中文网", "联合早报", 
                            "新华网", "美国之音", "8视界", "中国日报", "新浪国际", "澎湃新闻"]
        
        for article in all_articles:
            source = article.get('source', '')
            if any(auth in source for auth in authority_sources):
                all_authority_news.append(article['title'])
            else:
                # 非权威源也加入，但后面会去重
                all_authority_news.append(article['title'])
        
        # 去重
        all_authority_news = list(dict.fromkeys(all_authority_news))

        filtered = [t for t in all_authority_news if t not in exclude_topics]
        # 去重
        seen = set()
        unique_filtered = [x for x in filtered if not (x in seen or seen.add(x))]
        return unique_filtered[:limit]
    except Exception as e:
        log.print_log(f"获取权威源话题失败: {e}", "warning")
        return []


def select_platform_topic(
    platform: Any, 
    cnt: int = 10, 
    exclude_topics: List[str] = None, 
    authority_priority: bool = False,
    min_time: float = None
) -> str:
    """
    获取话题，支持权威源优先和时间过滤
    """
    topics = []
    if authority_priority:
        topics = get_authority_topics(limit=cnt, exclude_topics=exclude_topics, min_time=min_time)
        if topics:
            log.print_log(f"已从中外权威媒体（BBC/新华社等）选取高质量话题", "success")
    
    if not topics:
        topics = get_platform_news(platform, cnt, exclude_topics)
        
    if not topics:
        if exclude_topics:
            topics = get_platform_news(platform, cnt)
        if not topics:
            topics = ["历史上的今天"]
            log.print_log(f"所有源均不可用，将使用默认话题。")

    # 加权随机选择
    weights = [1 / (i + 1) ** 1.5 for i in range(len(topics))]
    selected_topic = random.choices(topics, weights=weights, k=1)[0]
    selected_topic = selected_topic.replace("|", "——")

    return selected_topic
