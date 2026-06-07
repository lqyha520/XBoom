#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
全网热榜聚合爬虫 V17 - 最强热点抓取
整合：知乎、微博、头条、百度、V2EX、GitHub、HackerNews、抖音等
"""
import asyncio
import aiohttp
import json
from datetime import datetime
from typing import List, Dict, Optional
from lxml import etree

from base import BaseSpider
from logger_utils import logger


class HotRankAggregator(BaseSpider):
    """
    全网热榜聚合爬虫
    基于各种公开API和RSS，无需登录即可获取热榜数据
    """
    source_name = "全网热榜聚合"
    category = "热点"
    
    # V18: 热榜API配置 (基于开源项目和网络公开API)
    HOT_APIS = {
        # ===== 统一聚合源（优先级最高）=====
        "viki_weibo": {
            "url": "https://60s.viki.moe/v2/weibo",
            "headers": {},
            "is_viki": True,
            "weight": 2.0,
        },
        "viki_douyin": {
            "url": "https://60s.viki.moe/v2/douyin",
            "headers": {},
            "is_viki": True,
            "weight": 2.0,
        },
        "viki_bili": {
            "url": "https://60s.viki.moe/v2/bili",
            "headers": {},
            "is_viki": True,
            "weight": 1.8,
        },
        "viki_zhihu": {
            "url": "https://60s.viki.moe/v2/zhihu",
            "headers": {},
            "is_viki": True,
            "weight": 2.0,
        },
        "viki_baidu": {
            "url": "https://60s.viki.moe/v2/baidu",
            "headers": {},
            "is_viki": True,
            "weight": 1.8,
        },
        "viki_toutiao": {
            "url": "https://60s.viki.moe/v2/toutiao",
            "headers": {},
            "is_viki": True,
            "weight": 1.6,
        },

        # ===== 平台官方API直连（数据最新最准）=====
        "bili_official": {
            "url": "https://api.bilibili.com/x/web-interface/popular",
            "headers": {"User-Agent": "Mozilla/5.0"},
            "is_json_path": "data.list",
            "title_key": "title",
            "url_key": "bvid",
            "url_prefix": "https://www.bilibili.com/video/",
            "weight": 1.7,
        },
        "douyin_official": {
            "url": "https://www.douyin.com/aweme/v1/web/hot/search/list/",
            "headers": {"User-Agent": "Mozilla/5.0", "Referer": "https://www.douyin.com/"},
            "is_json_path": "word_list",
            "title_key": "word_info.word",
            "url_key": "word_info.scheme_url",
            "weight": 1.9,
        },
        "baidu_official": {
            "url": "https://top.baidu.com/api/board?platform=wise&tab=realtime",
            "headers": {"User-Agent": "Mozilla/5.0"},
            "is_json_path": "data.cards[].content",
            "title_key": "query",
            "url_key": "url",
            "weight": 1.8,
        },
        "toutiao_official": {
            "url": "https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc",
            "headers": {"User-Agent": "Mozilla/5.0"},
            "is_json_path": "data",
            "title_key": "Title",
            "url_key": "Url",
            "weight": 1.6,
        },
        "weibo_official": {
            "url": "https://weibo.com/ajax/side/hotSearch",
            "headers": {"User-Agent": "Mozilla/5.0", "Referer": "https://weibo.com"},
            "is_json_path": "data.realtime",
            "title_key": "note",
            "url_key": "url",
            "weight": 2.0,
        },
        "zhihu_new_api": {
            "url": "https://www.zhihu.com/api/v3/feed/topstory/hot-list-web",
            "headers": {"User-Agent": "Mozilla/5.0"},
            "is_json_path": "data",
            "title_key": "target.title",
            "url_key": "target.url",
            "weight": 2.0,
        },

        # ===== 垂直领域源 =====
        "douban_movie": {
            "url": "https://movie.douban.com/j/chart/top_list?type=24&interval_id=100%3A90&action=&start=0&limit=20",
            "headers": {"User-Agent": "Mozilla/5.0"},
            "is_json_array": True,
            "title_key": "title",
            "url_key": "url",
            "weight": 1.3,
        },
        "36kr_newsflash": {
            "url": "https://36kr.com/api/newsflash",
            "headers": {"User-Agent": "Mozilla/5.0"},
            "is_json_path": "data.items",
            "title_key": "title",
            "url_prefix": "https://36kr.com/newsflashes/",
            "url_key": "id",
            "weight": 1.4,
        },

        # ===== 国际/技术源 =====
        "v2ex": {
            "url": "https://www.v2ex.com/api/topics/hot.json",
            "headers": {},
            "weight": 1.5
        },
        "github": {
            "url": "https://api.github.com/search/repositories",
            "params": {"q": "created:>2024-01-01", "sort": "stars", "order": "desc", "per_page": 30},
            "headers": {},
            "is_json_path": "items",
            "title_key": "full_name",
            "url_key": "html_url",
            "weight": 1.8
        },
        "hackernews": {
            "url": "https://hacker-news.firebaseio.com/v0/topstories.json",
            "headers": {},
            "weight": 2.0
        },

        # ===== 其他社区源 =====
        "sspai": {
            "url": "https://sspai.com/api/v1/article/tag/feed",
            "headers": {},
            "weight": 1.2
        },
        "juejin": {
            "url": "https://api.juejin.cn/recommend_api/v1/article/recommend_all_feed",
            "params": {"page_type": 0, "cursor": "0", "sort_type": 200, "limit": 30},
            "headers": {},
            "weight": 1.3
        }
    }

    async def get_news_list(self, category: dict = None) -> List[Dict]:
        """
        获取全网热榜聚合
        并发获取所有热榜API，合并去重后返回
        """
        all_items = []
        semaphore = asyncio.Semaphore(10)  # 限制并发
        
        async def fetch_single(source_id: str, config: dict):
            async with semaphore:
                try:
                    items = await self._fetch_api(source_id, config)
                    logger.info(f"[{source_id}] 获取到 {len(items)} 条热榜")
                    return items
                except Exception as e:
                    logger.warning(f"[{source_id}] 获取失败: {e}")
                    return []
        
        # 并发获取所有热榜
        tasks = [
            fetch_single(source_id, config) 
            for source_id, config in self.HOT_APIS.items()
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 合并结果
        for items in results:
            if isinstance(items, list):
                all_items.extend(items)
        
        # 按热度权重排序
        all_items.sort(key=lambda x: x.get("hot_score", 0), reverse=True)
        
        logger.success(f"全网热榜聚合完成，共 {len(all_items)} 条")
        return all_items[:50]  # 返回前50条

    async def _fetch_api(self, source_id: str, config: dict) -> List[Dict]:
        """获取单个热榜API"""
        url = config["url"]
        headers = config.get("headers", {})
        params = config.get("params", {})
        weight = config.get("weight", 1.0)
        is_viki = config.get("is_viki", False)
        is_rss = config.get("is_rss", False)
        is_html = config.get("is_html", False)

        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                headers=headers,
                params=params,
                timeout=aiohttp.ClientTimeout(total=15)
            ) as response:
                if response.status != 200:
                    return []

                data = await response.text()

                if is_viki:
                    return self._parse_viki(data, source_id, weight)
                elif is_html:
                    return self._parse_tophub_html(data, source_id, weight)
                elif is_rss:
                    return self._parse_rss(data, source_id, weight)
                else:
                    json_data = json.loads(data)
                    return self._parse_json(source_id, json_data, weight, config)

    def _parse_viki(self, raw: str, source_id: str, weight: float) -> List[Dict]:
        """解析 60s.viki.moe 统一API响应"""
        items = []
        try:
            data = json.loads(raw)
            if data.get("code") != 200 or not isinstance(data.get("data"), list):
                return items
            source_name_map = {
                "viki_weibo": "微博热搜", "viki_douyin": "抖音热点",
                "viki_bili": "B站热门", "viki_zhihu": "知乎热榜",
                "viki_baidu": "百度热点", "viki_toutiao": "今日头条热榜",
            }
            for idx, item in enumerate(data["data"][:30]):
                title = item.get("title", "")
                if not title:
                    continue
                items.append({
                    "title": title,
                    "article_url": item.get("link", ""),
                    "hot_score": (30 - idx) * 100 * weight,
                    "source": source_name_map.get(source_id, source_id),
                    "date_str": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                })
        except Exception as e:
            logger.error(f"解析 {source_id} viki数据失败: {e}")
        return items

    def _get_nested(self, obj, path: str):
        """按路径获取嵌套值，支持 a.b.c 和 array[].field 格式"""
        parts = path.split(".")
        current = obj
        for part in parts:
            if part.endswith("]") and "[" in part:
                # 数组展开: cards[].content -> 遍历cards取每个的content
                key = part.split("[")[0]
                sub_key = part.split("].")[1] if "]." in part else None
                arr = current.get(key, [])
                if sub_key and isinstance(arr, list):
                    return [item.get(sub_key, {}) for item in arr if isinstance(item, dict)]
                return arr
            elif isinstance(current, dict):
                current = current.get(part)
            else:
                return None
            if current is None:
                return None
        return current

    def _parse_json(self, source_id: str, data: dict, weight: float, config: dict = None) -> List[Dict]:
        """解析JSON格式热榜 - 支持通用配置驱动"""
        items = []
        try:
            # V18: 通用JSON路径解析（优先）
            if config and config.get("is_json_path") or config and config.get("is_json_array"):
                title_key = config.get("title_key", "title")
                url_key = config.get("url_key", "url")
                url_prefix = config.get("url_prefix", "")
                source_display = {
                    "bili_official": "B站热门", "douyin_official": "抖音热点",
                    "baidu_official": "百度热搜", "toutiao_official": "今日头条",
                    "weibo_official": "微博热搜", "zhihu_new_api": "知乎热榜",
                    "douban_movie": "豆瓣电影", "36kr_newsflash": "36氪快讯",
                    "github": "GitHub Trending",
                }.get(source_id, source_id)

                # 获取列表数据
                if config.get("is_json_array"):
                    item_list = data if isinstance(data, list) else []
                else:
                    item_list = self._get_nested(data, config.get("is_json_path", "")) or []

                if not isinstance(item_list, list):
                    item_list = [item_list]

                for idx, item in enumerate(item_list[:25]):
                    title = self._get_nested(item, title_key) or ""
                    if not title:
                        continue
                    raw_url = self._get_nested(item, url_key) or ""
                    article_url = f"{url_prefix}{raw_url}" if url_prefix else (raw_url or "")

                    items.append({
                        "title": str(title),
                        "article_url": article_url,
                        "hot_score": (25 - idx) * 100 * weight,
                        "source": source_display,
                        "date_str": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    })

            # 兼容旧版特殊格式解析
            elif source_id == "v2ex":
                for idx, item in enumerate(data[:20]):
                    title = item.get("title", "")
                    if title:
                        items.append({
                            "title": title,
                            "article_url": item.get("url", ""),
                            "hot_score": (20 - idx) * 50 * weight,
                            "source": "V2EX",
                            "date_str": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        })

            elif source_id == "hackernews":
                story_ids = data[:20] if isinstance(data, list) else []
                for idx, story_id in enumerate(story_ids):
                    items.append({
                        "title": f"[HN] Story {story_id}",
                        "article_url": f"https://news.ycombinator.com/item?id={story_id}",
                        "hot_score": (30 - idx) * 100 * weight,
                        "source": "Hacker News",
                        "date_str": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    })

            elif source_id == "juejin":
                for idx, item in enumerate(data.get("data", [])[:20]):
                    article_info = item.get("item_info", {}).get("article_info", {})
                    title = article_info.get("title", "")
                    if title:
                        items.append({
                            "title": title,
                            "article_url": f"https://juejin.cn/post/{article_info.get('article_id', '')}",
                            "hot_score": article_info.get("view_count", 0) * weight,
                            "source": "掘金热门",
                            "date_str": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        })

            elif source_id == "sspai":
                for idx, item in enumerate(data.get("data", [])[:15]):
                    title = item.get("title", "")
                    if title:
                        items.append({
                            "title": title,
                            "article_url": item.get("web_url", ""),
                            "hot_score": (15 - idx) * 50 * weight,
                            "source": "少数派",
                            "date_str": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        })

        except Exception as e:
            logger.error(f"解析 {source_id} 失败: {e}")

        return items

    def _parse_rss(self, data: str, source_id: str, weight: float) -> List[Dict]:
        """解析RSS格式热榜"""
        items = []
        try:
            root = etree.fromstring(data.encode('utf-8'))
            rss_items = root.xpath('//item')[:20]
            
            for idx, item in enumerate(rss_items):
                title = ''.join(item.xpath('./title/text()')).strip()
                link = ''.join(item.xpath('./link/text()')).strip()
                
                if title:
                    items.append({
                        "title": title,
                        "article_url": link,
                        "hot_score": (20 - idx) * 50 * weight,
                        "source": source_id.upper(),
                        "date_str": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    })
        except Exception as e:
            logger.error(f"解析RSS失败: {e}")
        
        return items

    async def get_news_info(self, item: dict, category: str = "热点") -> Optional[Dict]:
        """获取热榜详情"""
        try:
            url = item.get("article_url", "")
            title = item.get("title", "")
            source = item.get("source", "热榜聚合")
            
            # 如果是Hacker News需要获取详情
            if item.get("need_detail") and item.get("story_id"):
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(
                            f"https://hacker-news.firebaseio.com/v0/item/{item['story_id']}.json",
                            timeout=aiohttp.ClientTimeout(total=10)
                        ) as response:
                            if response.status == 200:
                                story_data = await response.json()
                                title = story_data.get("title", title)
                                url = story_data.get("url", url)
                except:
                    pass
            
            # 清理标题前缀
            for prefix in ["[GitHub]", "[HN]"]:
                if title.startswith(prefix):
                    title = title[len(prefix):].strip()
            
            return {
                "title": title,
                "article_info": f"# {title}\n\n**来源**: {source}\n**热度**: {item.get('hot_score', 0):.0f}\n**链接**: {url}\n\n---\n*本文由 AIWriteX 热榜聚合系统自动采集*",
                "source": source,
                "category": category,
                "url": url,
                "article_url": url,
                "date_str": item.get("date_str", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            }
        except Exception as e:
            logger.error(f"获取热榜详情失败: {e}")
            return None


# 兼容旧版
class HotRankSpider(HotRankAggregator):
    pass


if __name__ == "__main__":
    # 测试运行
    async def test():
        spider = HotRankAggregator()
        news_list = await spider.get_news_list()
        print(f"获取到 {len(news_list)} 条热榜")
        for item in news_list[:5]:
            print(f"- [{item['source']}] {item['title']} (热度: {item['hot_score']:.0f})")
    
    asyncio.run(test())
