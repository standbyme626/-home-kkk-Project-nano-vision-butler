#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试新闻抓取脚本
"""

import requests
import json
import time
import xml.etree.ElementTree as ET
from datetime import datetime

# 测试配置
TEST_CONFIG = {
    "url": "https://feeds.bbci.co.uk/news/rss.xml?edition=int",
    "max_items": 5,
}

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
                "source": "BBC News",
                "language": language_elem.text.strip() if language_elem is not None and language_elem.text else 'zh',
            })
        
        return items
    except Exception as e:
        print(f"解析 XML 失败：{str(e)}")
        return []


def format_news_message(news_items):
    """格式化新闻消息"""
    if not news_items:
        return "暂无新闻"
    
    # 生成消息
    message = "📰 **今日新闻汇总**\n\n"
    
    for i, item in enumerate(news_items, 1):
        message += f"{i}. **{item['title']}**\n"
        message += f"   📅 {item['pub_date']}\n"
        message += f"   🔗 [{item['link']}]({item['link']})\n"
        if item['description']:
            message += f"   📝 {item['description'][:100]}...\n\n"
        
        message += "\n"
    
    return message


def main():
    """主函数"""
    print("=" * 50)
    print("开始测试新闻抓取")
    print("=" * 50)
    
    # 抓取 RSS
    url = TEST_CONFIG["url"]
    print(f"正在抓取：{url}")
    
    response = requests.get(url, timeout=10)
    print(f"请求成功，状态码：{response.status_code}")
    
    # 解析 XML
    items = parse_rss_xml(response.text)
    
    # 限制数量
    items = items[:TEST_CONFIG["max_items"]]
    
    print(f"成功抓取 {len(items)} 条新闻")
    
    # 格式化消息
    message = format_news_message(items)
    
    # 打印消息
    print("\n" + "=" * 50)
    print("格式化后的消息：")
    print("=" * 50)
    print(message)
    
    # 保存数据
    data = {
        "timestamp": datetime.now().isoformat(),
        "news": items,
    }
    
    with open("test_news_data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print("\n数据已保存到 test_news_data.json")
    print("=" * 50)
    print("测试完成")
    print("=" * 50)


if __name__ == "__main__":
    main()
