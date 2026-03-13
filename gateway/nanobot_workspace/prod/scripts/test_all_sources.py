#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试所有 RSS 源是否可用
"""

import requests
import xml.etree.ElementTree as ET
from datetime import datetime

# RSS 源配置
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

    # 国内源
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

# 测试配置
TEST_CONFIG = {
    "timeout": 10,
    "retry_count": 3,
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
                "source": RSS_SOURCES[0]["name"],
                "language": language_elem.text.strip() if language_elem is not None and language_elem.text else 'zh',
            })
        
        return items
    except Exception as e:
        return []


def check_source(source):
    """测试单个 RSS 源"""
    print(f"\n测试：{source['name']}")
    print(f"URL: {source['url']}")
    
    try:
        response = requests.get(source['url'], timeout=TEST_CONFIG["timeout"])
        response.raise_for_status()
        
        # 解析 XML
        items = parse_rss_xml(response.text)
        
        if items:
            print(f"✅ 成功！抓取到 {len(items)} 条新闻")
            if items:
                print(f"   第一条：{items[0]['title'][:50]}")
            return True
        else:
            print(f"⚠️  请求成功，但解析到 0 条新闻")
            return False
        
    except requests.exceptions.Timeout:
        print(f"⏱️  请求超时")
        return False
    except requests.exceptions.ConnectionError:
        print(f"❌ 连接错误")
        return False
    except requests.exceptions.HTTPError as e:
        print(f"❌ HTTP 错误：{e}")
        return False
    except Exception as e:
        print(f"❌ 未知错误：{str(e)}")
        return False


def main():
    """主函数"""
    print("=" * 60)
    print("RSS 源可用性测试")
    print(f"时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S CST')}")
    print("=" * 60)
    
    results = []
    
    # 测试所有 RSS 源
    for source in RSS_SOURCES:
        success = check_source(source)
        results.append((source['name'], success))
    
    # 统计结果
    print("\n" + "=" * 60)
    print("测试结果统计")
    print("=" * 60)
    
    success_count = sum(1 for _, success in results if success)
    total_count = len(results)
    
    print(f"成功：{success_count}/{total_count}")
    
    # 显示详细结果
    print("\n详细结果：")
    for name, success in results:
        status = "✅" if success else "❌"
        print(f"{status} {name}")
    
    # 保存结果
    with open("rss_test_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f"\n结果已保存到 rss_test_results.json")
    print("=" * 60)


if __name__ == "__main__":
    import json
    main()
