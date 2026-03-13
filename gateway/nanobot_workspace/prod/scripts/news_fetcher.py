#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
无 API Key 新闻抓取器
使用 xml.etree.ElementTree 解析 RSS
"""

import requests
import json
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
import os

# ==================== 配置区域 ====================

# RSS 源配置（国内 + 国外）
RSS_SOURCES = [
    # 国外源
    {
        "name": "BBC News (国际)",
        "url": "https://feeds.bbci.co.uk/news/rss.xml?edition=int",
        "language": "en"
    },
    {
        "name": "NYT Top Stories",
        "url": "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml",
        "language": "en"
    },
    {
        "name": "Al Jazeera",
        "url": "https://www.aljazeera.com/xml/rss/all.xml",
        "language": "ar"
    },
    # 国内源（部分可用，部分需要代理）
    {
        "name": "中国新闻网 - 即时新闻",
        "url": "https://www.chinanews.com.cn/rss/scroll-news.xml",
        "language": "zh"
    },
    {
        "name": "中国新闻网 - 时政",
        "url": "https://www.chinanews.com.cn/rss/china.xml",
        "language": "zh"
    },
    {
        "name": "中国新闻网 - 国际",
        "url": "https://www.chinanews.com.cn/rss/world.xml",
        "language": "zh"
    },
    {
        "name": "中国新闻网 - 财经",
        "url": "https://www.chinanews.com.cn/rss/finance.xml",
        "language": "zh"
    },
    {
        "name": "人民网 - 全部新闻",
        "url": "http://www.people.com.cn/rss/ywkx.xml",
        "language": "zh"
    },
    {
        "name": "新华网 - 全部",
        "url": "http://www.xinhuanet.com/politics/news_politics.xml",
        "language": "zh"
    },
]

# Telegram 配置
TELEGRAM_CONFIG = {
    "chat_id": "7566115125",
    "bot_token": "YOUR_BOT_TOKEN_HERE",  # 需要配置你的 Bot Token
}

# 抓取配置
FETCH_CONFIG = {
    "timeout": 10,
    "retry_count": 3,
    "delay_between_fetches": 5,  # 源之间延迟（秒）
}

# 过滤配置
FILTER_CONFIG = {
    "keywords": ["科技", "国际", "财经", "政治", "社会"],  # 关键词过滤
    "exclude_keywords": ["广告", "推广"],  # 排除关键词
}

# 输出配置
OUTPUT_CONFIG = {
    "log_file": "news_fetcher.log",
    "data_file": "news_data.json",
    "max_items_per_source": 10,  # 每个源最多抓取 10 条
}

# ==================== 工具函数 ====================

def log(message):
    """记录日志"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] {message}\n"
    
    # 写入日志文件
    with open(OUTPUT_CONFIG["log_file"], "a", encoding="utf-8") as f:
        f.write(log_entry)
    
    # 打印到控制台
    print(log_entry.strip())


def parse_rss_xml(xml_content):
    """解析 RSS XML 内容"""
    try:
        root = ET.fromstring(xml_content)
        
        # 查找 RSS 命名空间
        ns = {'rss': 'http://www.w3.org/2005/Atom'}
        
        # 获取频道信息
        channel = root.find('channel', ns)
        if channel is None:
            channel = root.find('channel')
        
        title_elem = channel.find('title', ns) if channel is not None else channel.find('title')
        language_elem = channel.find('language', ns) if channel is not None else channel.find('language')
        
        # 获取条目
        items = []
        for item in channel.findall('item', ns) if channel is not None else channel.findall('item'):
            title_elem = item.find('title', ns) if item is not None else item.find('title')
            link_elem = item.find('link', ns) if item is not None else item.find('link')
            description_elem = item.find('description', ns) if item is not None else item.find('description')
            pub_date_elem = item.find('pubDate', ns) if item is not None else item.find('pubDate')
            
            title = title_elem.text.strip() if title_elem is not None and title_elem.text else ''
            link = link_elem.text.strip() if link_elem is not None and link_elem.text else ''
            description = description_elem.text.strip() if description_elem is not None and description_elem.text else ''
            
            # 解析日期
            pub_date = ''
            if pub_date_elem is not None and pub_date_elem.text:
                date_str = pub_date_elem.text.strip()
                try:
                    # 处理不同日期格式
                    if 'GMT' in date_str:
                        date_str = date_str.replace('GMT', '+0000')
                    elif 'UTC' in date_str:
                        date_str = date_str.replace('UTC', '+0000')
                    
                    # 尝试解析
                    pub_date = datetime.strptime(date_str, "%a, %d %b %Y %H:%M:%S %Z")
                except:
                    pass
            
            items.append({
                "title": title,
                "link": link,
                "description": description,
                "pub_date": pub_date.isoformat() if isinstance(pub_date, datetime) else pub_date,
                "source": RSS_SOURCES[0]["name"],  # 临时源名
                "language": language_elem.text.strip() if language_elem is not None and language_elem.text else 'zh',
            })
        
        return items
    except Exception as e:
        log(f"解析 XML 失败：{str(e)}")
        return []


def fetch_rss(url, source_name, max_items=10):
    """抓取 RSS 源"""
    log(f"正在抓取：{source_name} ({url})")
    
    try:
        response = requests.get(url, timeout=FETCH_CONFIG["timeout"])
        response.raise_for_status()
        
        # 解析 XML
        items = parse_rss_xml(response.text)
        
        # 检查解析结果
        if items:
            log(f"成功抓取 {len(items)} 条新闻")
            
            # 限制数量
            items = items[:max_items]
            
            return items
        else:
            log(f"成功抓取 0 条新闻")
            return []
        
    except Exception as e:
        log(f"抓取失败：{source_name} - {str(e)}")
        import traceback
        traceback.print_exc()
        return []


def send_to_telegram(message, chat_id):
    """发送到 Telegram"""
    # TODO: 这里需要配置 Telegram Bot API
    # 使用 requests 发送 POST 请求到 Telegram Bot API
    # 需要安装 python-telegram-bot 或使用 requests + bot API
    
    log(f"发送消息到 Telegram: {chat_id}")
    log(f"消息内容：{message[:200]}...")
    
    # 实际发送代码（需要配置 token）
    # import requests
    # url = f"https://api.telegram.org/bot{TELEGRAM_CONFIG['bot_token']}/sendMessage"
    # payload = {
    #     "chat_id": chat_id,
    #     "text": message,
    #     "parse_mode": "HTML",
    #     "disable_web_page_proxy": True
    # }
    # response = requests.post(url, json=payload, timeout=10)
    # if response.status_code == 200:
    #     log("Telegram 发送成功")
    # else:
    #     log(f"Telegram 发送失败：{response.status_code}")


def format_news_message(news_items):
    """格式化新闻消息"""
    if not news_items:
        return "暂无新闻"
    
    # 按语言分组
    by_language = {}
    for item in news_items:
        lang = item.get("language", "zh")
        if lang not in by_language:
            by_language[lang] = []
        by_language[lang].append(item)
    
    # 生成消息
    message = "📰 **今日新闻汇总**\n\n"
    
    for lang, items in by_language.items():
        lang_name = "中文" if lang == "zh" else "英文"
        message += f"🌍 **{lang_name}新闻** ({len(items)}条)\n\n"
        
        for i, item in enumerate(items, 1):
            message += f"{i}. **{item['title']}**\n"
            message += f"   📅 {item['pub_date']}\n"
            message += f"   🔗 [{item['link']}]({item['link']})\n"
            if item['description']:
                message += f"   📝 {item['description'][:100]}...\n\n"
        
        message += "\n"
    
    return message


def save_news_data(news_items):
    """保存新闻数据到文件"""
    data = {
        "timestamp": datetime.now().isoformat(),
        "news": news_items,
    }
    
    with open(OUTPUT_CONFIG["data_file"], "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    log(f"新闻数据已保存到：{OUTPUT_CONFIG['data_file']}")


# ==================== 主程序 ====================

def main():
    """主函数"""
    log("=" * 50)
    log("开始新闻抓取任务")
    log(f"时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S CST')}")
    log("=" * 50)
    
    all_news = []
    
    # 抓取所有 RSS 源
    for source in RSS_SOURCES:
        items = fetch_rss(
            source["url"],
            source["name"],
            max_items=OUTPUT_CONFIG["max_items_per_source"]
        )
        all_news.extend(items)
        
        # 源之间延迟
        time.sleep(FETCH_CONFIG["delay_between_fetches"])
    
    # 去重（基于标题 + 链接）
    seen = set()
    unique_news = []
    for item in all_news:
        key = (item["title"].lower(), item["link"])
        if key not in seen:
            seen.add(key)
            unique_news.append(item)
    
    log(f"去重后剩余：{len(unique_news)} 条新闻")
    
    # 保存数据
    save_news_data(unique_news)
    
    # 发送 Telegram
    message = format_news_message(unique_news)
    send_to_telegram(message, TELEGRAM_CONFIG["chat_id"])
    
    log("=" * 50)
    log("新闻抓取任务完成")
    log("=" * 50)


if __name__ == "__main__":
    main()
