import streamlit as st
import asyncio
import aiohttp
import feedparser
from datetime import datetime, timedelta
import requests
from bs4 import BeautifulSoup
import json
st.set_page_config(layout="wide", page_title="财经新闻聚合")

# from stock_chart import render_cn_flow_fx_gauges  as stock_flow 

# 缓存
# @st.cache_data(ttl=60)
def get_feed_data(url):
    feed = feedparser.parse(url)
    articles = []
    for entry in feed.entries:
        published_str = entry.get("published", "")
        try:
            # feedparser 会解析出 published_parsed（time.struct_time）
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                published_dt = datetime(*entry.published_parsed[:6])
            else:
                published_dt = datetime.min
        except Exception:
            published_dt = datetime.min

        articles.append({
            "title": entry.title,
            "link": entry.link,
            "published": published_dt.strftime("%Y-%m-%d %H:%M"),
            "published_dt": published_dt  # 用于排序
        })

    # 按时间倒序（最新在前）
    articles.sort(key=lambda x: x["published_dt"], reverse=True)

    # 返回时去掉辅助字段
    for art in articles:
        del art["published_dt"]

    return articles
# 异步获取多个RSS
async def fetch_all_feeds(urls):
    loop = asyncio.get_event_loop()
    tasks = [loop.run_in_executor(None, get_feed_data, url) for url in urls]
    results = await asyncio.gather(*tasks)
    return results



# X API 获取逻辑
BEARER_TOKEN = "AAAAAAAAAAAAAAAAAAAAAD4T3gEAAAAAv2ZtGy8cwAentw7CDqneAt5fp08%3DQXayh52v8I3MTZ1A3B5pxDaDIZLdDB8pkDmuq9bazFk8IkiVVq"

def get_user_id(username):
    """根据用户名获取用户ID"""
    url = f"https://api.twitter.com/2/users/by/username/{username}"
    headers = {"Authorization": f"Bearer {BEARER_TOKEN}"}
    r = requests.get(url, headers=headers)
    if r.status_code == 200:
        return r.json().get("data", {}).get("id")
    else:
        st.error(f"❌ 获取用户ID失败: {r.text}")
        return None

def get_latest_tweets(user_id, count=10):
    """根据用户ID获取最新推文"""
    url = f"https://api.twitter.com/2/users/{user_id}/tweets"
    params = {
        "max_results": count,
        "tweet.fields": "created_at,text"
    }
    headers = {"Authorization": f"Bearer {BEARER_TOKEN}"}
    r = requests.get(url, headers=headers, params=params)
    if r.status_code == 200:
        return r.json().get("data", [])
    else:
        st.error(f"❌ 获取推文失败: {r.text}")
        return []


def json_cookie_to_text(json_path: str) -> str:
    """
    从 Playwright storage_state.json 生成形如：
    name=value; name2=value2;
    """
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    cookies = data.get("cookies", [])
    parts = [f"{c['name']}={c['value']}" for c in cookies]

    # 末尾添加分号
    return "; ".join(parts) + ";"
#bloomberg 获取最新文章
def get_bloomberg_latest():
    cookie_string = json_cookie_to_text("playwright_storage_state.json")
    url = "https://www.bloomberg.com/lineup-next/api/stories?types=ARTICLE%2CFEATURE%2CINTERACTIVE%2CLETTER%2CEXPLAINERS&pageNumber=1&limit=25"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
        "Referer": "https://www.bloomberg.com/",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Connection": "keep-alive",
        # "cookies":cookie_string
        "Cookie":"session_id=019887bb-a015-73e7-be9f-a6756b95d787; _session_id_backup=019887bb-a015-73e7-be9f-a6756b95d787; agent_id=019887bb-a015-7a0b-bee7-66d7fa7095d3; session_key=b533826c88b5152dd8a99fbd536ae3c7dec899f9; gatehouse_id=019887bb-a76c-709c-9e8e-ff0a1a7bd15e; geo_info=%7B%22countryCode%22%3A%22JP%22%2C%22country%22%3A%22JP%22%2C%22field_n%22%3A%22cp%22%2C%22trackingRegion%22%3A%22Asia%22%2C%22cacheExpiredTime%22%3A1755228679038%2C%22region%22%3A%22Asia%22%2C%22fieldN%22%3A%22cp%22%7D%7C1755228679038; geo_info={%22country%22:%22JP%22%2C%22region%22:%22Asia%22%2C%22fieldN%22:%22cp%22}|1755228678917; _sp_krux=true; bbgconsentstring=req1fun1pad1; bdfpc=004.8021744310.1754623914407; usnatUUID=a66c4ed7-8654-47d2-beea-899041f93d9c; _fbp=fb.1.1754623917370.613590466726000588; __spdt=59a61687f11f46ce855ff5a2534ad7da; _scor_uid=c652d9c3932c45b58b0bd552787beef8; _pxvid=24a035c9-7408-11f0-ac93-733c93ad27b2; _cc_id=beab171fb5e3f8d39e6ba63aacbaf576; afUserId=875afee5-88ec-468b-bde3-a2fc165e65cc-p; _tt_enable_cookie=1; _ttp=01K23VS8GB2JCYPJ3TB6391XTE_.tt.1; _ga=GA1.1.513283790.1754623914; _scid=76_6qEmF0da6uPuY_TYtbse0tijdcDY-; __stripe_mid=1faa8875-93d0-482a-9afd-84c2f3269f9dfb7bb2; AMP_MKTG_4c214fdb8b=JTdCJTIydXRtX2NhbXBhaWduJTIyJTNBJTIybGF0ZXN0JTIyJTJDJTIydXRtX21lZGl1bSUyMiUzQSUyMndlYiUyMiUyQyUyMnV0bV9zb3VyY2UlMjIlM0ElMjJob21lcGFnZSUyMiU3RA==; AMP_4c214fdb8b=JTdCJTIyZGV2aWNlSWQlMjIlM0ElMjJmOTFiMjNjZi0zMTI4LTQ1MzUtODJkMS00NGNjY2Y3NjQ1ZGElMjIlMkMlMjJzZXNzaW9uSWQlMjIlM0ExNzU0ODE4OTY1Mzg1JTJDJTIyb3B0T3V0JTIyJTNBZmFsc2UlMkMlMjJsYXN0RXZlbnRUaW1lJTIyJTNBMTc1NDgxODk2NTM5NiUyQyUyMmxhc3RFdmVudElkJTIyJTNBOTAlMkMlMjJwYWdlQ291bnRlciUyMiUzQTAlN0Q=; professional-cookieConsent=new-relic|perimeterx-bot-detection|perimeterx-pixel|google-tag-manager|google-analytics; _ga_GQ1PBLXZCT=GS2.1.s1761201113$o22$g1$t1761201131$j42$l0$h0; consentUUID=f36f4552-777c-4cb3-a381-63a45c2cd9b8_46_47_49; consentDate=2025-10-27T01:14:23.644Z; _ga_NNP7N7T2TG=GS2.1.s1762226185$o2$g1$t1762226204$j59$l0$h0; _ga_RPDTQSMHH5=GS2.1.s1762226184$o3$g1$t1762226205$j58$l0$h0; pxcts=0c7bcbf7-c362-11f0-9da1-9130cab9eb09; exp_pref=APAC; country_code=JP; _gcl_au=1.1.1747961265.1763349002; _pxhd=tKlOC2YAyY8HDsL26KzfvvFGw3RtDngWRh46tsEvKjdAGwZ6Wsvv5chPWWV6g7jwPlBiZIfnsLOx2626YrMr1A==:s6tBcVZkil-YIWjoFZOqZQ9ikodrhltPSDsPa7wG/OPyxJpS5u6cwh8xrj-Wkkp1Y8w6iAHzfZ0kinHZt8fG1kRBrJkKavd7g-zrprz802k=; __gads=ID=41987ba3fadd156b:T=1754623935:RT=1763349001:S=ALNI_MYnKPSpywthWsvrwN87Z7kibmGK2g; __eoi=ID=23ab67fa164e4f03:T=1754623935:RT=1763349001:S=AA-AfjavQuDZq-2uYd7Ie1CL4u7A; panoramaId=4d1783b7b58dd3f65d93f64ad3bd16d5393800bc92f3ce1f44b75a5696894fb7; panoramaIdType=panoIndiv; AF_SYNC=1763349008906; _parsely_visitor={%22id%22:%22pid=4c609996-6b03-43f9-918c-8e834528be90%22%2C%22session_count%22:25%2C%22last_session_ts%22:1763349012290}; _reg-csrf=s%3APXkVk6dGpKCAB1E_UJ1Nj3hw.YafRjy0%2FGZBUIpGnTaJnWYSO1HYlKNoFrJamys4V1uM; _rdt_uuid=1761201110094.1c6e6d69-fe7e-485e-9d01-cfe02be5620d; panoramaId_expiry=1763953888431; _uetsid=ec1d03a0c36211f0a1135d5db4f755ae; _uetvid=3c9e0a50740811f08009893ff04069d0; ttcsid_CSN3O6BC77UF5CI6702G=1763349016051::DMdJiRB9YC0YXkpsW4UG.19.1763349101717.0; ttcsid=1763349016052::uGr_XOU31quf_Vg-JMlr.19.1763349101717.0; _scid_r=_S_6qEmF0da6uPuY_TYtbse0tijdcDY-uC46wA; _sctr=1%7C1763308800000; _reg-csrf-token=4zbG7h49-FRuvdwSIPbnjinObwISx1Dx6y_M; _ga_GQ1PBLXZCT=GS2.1.s1763366420$o25$g1$t1763366474$j6$l0$h0"
    }
    resp = requests.get(url, headers=headers, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    articles = []
    for item in data:
        title = item.get("headline", "").strip()
        link = "https://www.bloomberg.com" + item.get("url", "")
        published_str = item.get("publishedAt", "")
        try:
            published_dt = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
        except Exception:
            published_dt = datetime.min

        articles.append({
            "title": title,
            "link": link,
            "published": published_dt.strftime("%Y-%m-%d %H:%M"),
            "published_dt": published_dt
        })


    print(articles.count)
    # 按时间倒序
    articles.sort(key=lambda x: x["published_dt"], reverse=True)

    # 去掉辅助字段
    for art in articles:
        del art["published_dt"]

    return articles



#获得wsj的最新文章
def get_wsj_latest_from_html(url,i):
    # url = "https://www.wsj.com/news/latest-headlines"  # 或其他栏目

    headers = {
        "method": "GET",
        # "path": "/news/latest-headlines",
        "scheme": "https",
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "accept-encoding": "gzip, deflate, br, zstd",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,zh-TW;q=0.7,en-US;q=0.6",
        "cache-control": "no-cache",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0 Safari/537.36",
        "cookie": "ab_uuid=639551db-feb8-486b-bebd-504aec299d68; _pubcid=0a265af4-a2c5-4441-821a-3e4e737ac565; _pubcid_cst=DCwOLBEsaQ%3D%3D; _sp_su=false; pbjs-unifiedid_cst=CyzZLLwsaQ%3D%3D; _pcid=%7B%22browserId%22%3A%22me29xvhahqc7eduz%22%7D; _ncg_domain_id_=43ce4080-9485-4f96-8e1a-e7601ec64e29.1.1754624192.1786160192; ajs_anonymous_id=52c7486f-978c-4130-96b7-024a44d60720; _fbp=fb.1.1754624192910.1660515809; _ga=GA1.1.907225457.1754624193; _meta_cross_domain_id=4a9f3cd9-2840-436a-8f1e-6d8ec465d70b; _scor_uid=8ca5835df9124751949db1699a6d05f7; _ncg_g_id_=c93c3a04-0dd6-4772-a939-b9513da230a9.3.1754624193.1786160192; _dj_sp_id=cfe417ad-65bc-4be3-a9b0-906cb860405d; _fbp=fb.1.1754624192910.1660515809; _pin_unauth=dWlkPU1XTXlaRFppTlRndE16TTNNeTAwTnpZekxXRmxaamd0WVRBek16TTFZVEZtTW1VMw; permutive-id=905a37d0-b2b1-47b4-a584-e2adc66cdf00; cX_P=me29xvhahqc7eduz; xbc=%7Bkpcd%7DChBtZTI5eHZoYWhxYzdlZHV6EgpLS2JncXBCbHB1Gjx1dG1ZaU5vbWVFWDFyMkprNHNvQ29HbU9hamJJMGoycXhEMldLMEJjOUhHaVNkZmdybXpvcDRKYWZ3UHogAA; LANG=en_US; cX_G=cx%3A2mv5t0efzpsx6yqcboo4purnp%3A3ht5osbxkl4n7; __tbc=%7Bkpcd%7DChBtZTI5eHZoYWhxYzdlZHV6EgpLS2JncXBCbHB1Gjx1dG1ZaU5vbWVFWDFyMkprNHNvQ29HbU9hamJJMGoycXhEMldLMEJjOUhHaVNkZmdybXpvcDRKYWZ3UHogAA; _pcus=eyJ1c2VyU2VnbWVudHMiOnsiQ09NUE9TRVIxWCI6eyJzZWdtZW50cyI6WyJhYTlxNmU0czFuazgiLCJhYTlxNmU0czFua2IiLCJhYXZ3ZGdycW02d3EiLCJhYXcwbGJyb3dzdWwiLCJDU2NvcmU6Mzk5ODk5NGRiMDcyYWMwMzhlYmI2NWU2YjhjOWRkYWMyNWJkYjU5Mjpub19zY29yZSIsIkxUcmV0dXJuOmUwNGM5OGJmM2JmYzRjMTg2NjBjZDgzNzQ5NTEzZjlhMmExMDQwMjA6MCIsIkNTY29yZTpkZDM4ODU2ZTkzOTRmMjEzZjUxYWRkY2MxYWY5M2I0NzBlODQ3NzkzOm5vX3Njb3JlIiwiTFRzOjkxYjE4YTc2MDBmMmI5MjZiNjdiMmU2MDZiMGE3MDY3MWU5NGRiNzA6NiJdfX19; dnsDisplayed=undefined; signedLspa=undefined; utag_main_v_id=019887c06e7f007458d88dd292c00506f001406700bd0; utag_main_vapi_domain=wsj.com; utag_main__sn=2; djcs_route=479932e8-512e-4092-9213-1f97d6d7024a; asia,cn=undefined; _pctx=%7Bu%7DN4IgrgzgpgThIC4B2YA2qA05owMoBcBDfSREQpAeyRCwgEt8oBJAEzIE4AmHgZgEYAHADZ%2BvQQFYuAFhEcADPJABfIA; optimizelySession=0; _meta_facebookTag_sync=1763349044033; _gcl_au=1.1.638361322.1763349046; _lr_env_src_ats=false; _meta_googleAdsSegments_library_loaded=1765155682609; connect.sid=s%3ASZ4P0uWs_qHd8_1DMVJIIoREdy_GmjHp.PcFWFrxMAjd83YgkOgk4wUnws4XH0jm35v2jydsKaUw; _lr_geo_location=JP; pbjs-unifiedid=%7B%22TDID%22%3A%228bd1d470-b434-4546-8ac3-2394bbc29d1e%22%2C%22TDID_LOOKUP%22%3A%22TRUE%22%2C%22TDID_CREATED_AT%22%3A%222025-11-25T06%3A16%3A19%22%7D; ca_r=_; AMCVS_CB68E4BA55144CAA0A4C98A5%40AdobeOrg=1; AMCV_CB68E4BA55144CAA0A4C98A5%40AdobeOrg=1585540135%7CMCIDTS%7C20410%7CMCMID%7C63849427253715503872873078523528107193%7CMCAAMLH-1767248596%7C11%7CMCAAMB-1767248596%7CRKhpRz8krg2tLO6pguXWp5olkAcUniQYPHaMWWgdJ3xzPWQmdj0y%7CMCOPTOUT-1766650996s%7CNONE%7CMCAID%7CNONE%7CvVersion%7C4.4.0; s_cc=true; _meta_cross_domain_recheck=1766643797181; __gads=ID=e855b6c6762f5c93:T=1754798348:RT=1766646316:S=ALNI_MZSvcaX1l7Gc2GgBMibXIE9eNiXFQ; __eoi=ID=ad4275b07b32ad78:T=1754798348:RT=1766646316:S=AA-AfjZsaRQgagbz2etyoJrZfADe; ab.storage.deviceId.98db0c4e-b9ba-4dfc-a2c3-bcee21a936ca=g%3A077d9204-51fc-0d8e-2a44-6cf9f398a710%7Ce%3Aundefined%7Cc%3A1763349044492%7Cl%3A1766646316549; _lr_sampling_rate=100; utag_main=v_id:01988904bac6000a92dcb937a2e20506f001406700bd0$_sn:26$_se:2$_ss:0$_st:1766648140075$vapi_domain:wsj.com$_prevpage:WSJ_Summaries_Collection_Latest%20Headlines%3Bexp-1766649940161$ses_id:1766646316023%3Bexp-session$_pn:2%3Bexp-session; _dj_id.9183=.1766643797.2.1766646340.1766643813.6673ec75-a098-41cd-b401-e061bacde513.01b94212-951c-4774-90d5-98dc2624b84d.83e9c260-a94d-4d90-ad25-4d68a4636883.1766646316516.2; _rdt_uuid=1754624193014.d60a0c66-1729-4174-8ea1-bc3960d934fb; ab.storage.sessionId.98db0c4e-b9ba-4dfc-a2c3-bcee21a936ca=g%3A3ac74bcb-9e3b-52f1-14bd-7160ffebb0ea%7Ce%3A1766648140575%7Cc%3A1766646316547%7Cl%3A1766646340575; _ga_K2H7B9JRSS=GS2.1.s1766643796$o26$g1$t1766646340$j37$l0$h1819479603; _uetsid=33d2d580e15a11f08d570546a46734de; _uetvid=e17dffa0740811f0aa5d9ff2788a99aa; _awl=2.1766646342.5-65781ee06e5031f5a470c047ce72ea0b-6763652d617369612d6561737431-0; datadome=x3nfm9ioydFoHjmPUT8yK2Aoamzd3btqAq0wmW08sqJIqCmA_k4PL2peC66qFxfNyvjTlcIR4o7VHLi3BraGk3E4W_ad1ubWW5O3xb~xRkARStPcUU254XawweAHQvnp; s_ppv=%5B%5BB%5D%5D; s_tp=12068"  # 替换成你自己真实cookie
    }


    response = requests.get(url, headers=headers)
    html = response.text
    print(html)
    # html = requests.get(url, headers=headers).text
    soup = BeautifulSoup(html, "html.parser")
    
    script_tag = soup.find("script", {"id": "__NEXT_DATA__", "type": "application/json"})
    if script_tag:
        data = json.loads(script_tag.string)
        articles = []
        itemlist=data.get("props").get("pageProps")
        if i!=0:
            articleitem=itemlist.get("articlesByL2")
            for itemlabel in articleitem:
                for item in itemlabel.get("articles", []):
                # article = item.get("item", {})
                    title = item.get("headline")
                    link = item.get("articleUrl")
                    published = item.get("timestamp", "")
                    summary=item.get("summary")
                    label=itemlabel.get("name")
                    try:
                         published_dt=datetime.strptime(published, "%Y-%m-%dT%H:%M:%SZ")
                    except Exception:
                        published_dt = datetime.min
                    articles.append({
                        "title": title,
                        "link": link,
                        "published": published_dt.strftime("%Y-%m-%d %H:%M"),
                        "summary":summary,
                        "label":label,
                    })
        else:
            # itemlist=data.get("props").get("pageProps")
            for item in itemlist.get("latestHeadlines", []):
            # article = item.get("item", {})
                title = item.get("headline")
                link = item.get("articleUrl")
                published = item.get("timestamp", "")
                try:
                    published_dt=datetime.strptime(published, "%Y-%m-%dT%H:%M:%SZ")
                except Exception:
                    published_dt = datetime.min
                summary=item.get("summary")
                articles.append({
                    "title": title,
                    "link": link,
                    "published": published_dt.strftime("%Y-%m-%d %H:%M"),
                    "summary":summary
                })
      
        
        return articles
    return []
# WSJ 和 Bloomberg 的分类 RSS（示例链接需替换成你能访问的）
WSJ = {
    "最新": "https://www.wsj.com/news/latest-headlines",
    "商业": "https://www.wsj.com/business",
    "金融": "https://www.wsj.com/finance",
    "政治": "https://www.wsj.com/politics",
    "经济": "https://www.wsj.com/economy",
    "科技": "https://www.wsj.com/tech"
}

BLOOMBERG= {
    "最新": "https://feeds.bloomberg.com/markets/news.rss",
    "商业": "https://feeds.bloomberg.com/business/news.rss",
    "市场": "https://feeds.bloomberg.com/markets/news.rss",
    "加密货币": "https://feeds.bloomberg.com/crypto/news.rss",
    "政治": "https://feeds.bloomberg.com/politics/news.rss",
    "科技": "https://feeds.bloomberg.com/technology/news.rss",
    "行业": "https://feeds.bloomberg.com/industries/news.rss"
}
# WSJ_SECTIONS = {
#     "最新": "https://www.wsj.com/news/latest",
#     "商业": "https://www.wsj.com/news/business",
#     "市场": "https://www.wsj.com/news/markets",
#     "金融": "https://www.wsj.com/news/finance",
#     "政治": "https://www.wsj.com/news/politics",
#     "科技": "https://www.wsj.com/news/technology",
#     "观点": "https://www.wsj.com/news/opinion"
# }

# BLOOMBERG_SECTIONS = {
#     "Markets": "https://www.bloomberg.com/markets",
#     "Economics": "https://www.bloomberg.com/economics",
#     "Technology": "https://www.bloomberg.com/technology",
#     "Politics": "https://www.bloomberg.com/politics",
#     "Business": "https://www.bloomberg.com/business",
#     "Opinion": "https://www.bloomberg.com/opinion"
# }


# 获取 RSSHub / TwitRSS 的 RSS URL
def build_rss_url(username):
    # 使用 TwitRSS.me
    return f"https://twitrss.me/twitter_user_to_rss/?user={username}&tor=true"
    # 或者使用 RSSHub
    # return f"https://rsshub.app/twitter/user/{username}?count=10&showTimestampInDescription=1"

def get_latest_tweets_via_rss(username):
    rss_url = build_rss_url(username)
    feed = feedparser.parse(rss_url)
    if feed.bozo:
        st.error(f"无法解析 RSS：{feed.bozo_exception}")
        return []
    tweets = []
    for entry in feed.entries[:10]:
        tweets.append({
            "title": entry.title,
            "link": entry.link,
            "published": entry.get("published", ""),
            "summary": entry.get("description", "")
        })
    return tweets
######################################################################################################################






# col1, col2, col4 = st.columns(3)

# with col1:
#     st.subheader("📈 华尔街见闻 / WSJ")
#     wsj_tab = st.tabs(list(WSJ.keys()))
#     for i, category in enumerate(WSJ):
#         with wsj_tab[i]:
#             # if i==0:
#             #     articles=get_wsj_latest_from_html(WSJ[category])
#             # else:
#             #     articles = get_feed_data(WSJ[category])
#             articles=get_wsj_latest_from_html(WSJ[category],i)
#             for art in articles:
#                 content = f"""
#                 <div style="margin-bottom:0.8em;">
#                     🔹 <a href="{art['link']}" target="_blank" style="text-decoration:none;font-weight:bold;color:#1a73e8;">{art['title']}</a> </br>  
#                     <span style="color:gray;font-size:0.85em;">🕒 {art.get('published', '无时间')}</span>  
#                     <span style="color:blue;font-size:0.85em;">{art.get('label', '')}</span><br>
#                     <span style="color:gray;font-size:0.75em;line-height:1.2;">{art.get('summary', '')}</span>
#                 </div>
#                 """
#                 st.markdown(content, unsafe_allow_html=True)


# with col2:
#     st.subheader("💹 Bloomberg")
#     bb_tab = st.tabs(list(BLOOMBERG.keys()))
#     for i, category in enumerate(BLOOMBERG):
#         with bb_tab[i]:
#             if i!=0:
#                 articles = get_feed_data(BLOOMBERG[category]) 
#             else:
#                 articles=get_bloomberg_latest()
#             for art in articles:
#                 st.markdown(
#                     f"🔹 [{art['title']}]({art['link']})  \n"
#                     f"<span style='color:gray;font-size:0.85em;'>🕒 {art.get('published', '无时间')}</span>",
#                     unsafe_allow_html=True
#                 )

# X 订阅 Tab
# with col3:
#     st.header("🐦 订阅 X 用户推文")
#     username = st.text_input("输入推特用户名（不带 @）")
#     if st.button("获取最新 10 条推文"):
#         if username:
#             user_id = get_user_id(username)
#             if user_id:
#                 tweets = get_latest_tweets(user_id)
#                 if tweets:
#                     for t in tweets:
#                         tweet_html = f"""
#                         🐦 <span style="color:blue;">{username}</span>  
#                         <span style="color:gray;font-size:0.85em;">🕒 {t['created_at']}</span>  
#                         <p style="margin-top:-6px;">{t['text']}</p>
#                         """
#                         st.markdown(tweet_html, unsafe_allow_html=True)
#                 else:
#                     st.warning("没有找到推文")
#         else:
#             st.warning("请输入用户名")

# Streamlit 界面
# with col4:
#     st.header("🐦 订阅 X 用户推文（使用 RSS）")
#     username = st.text_input("输入推特用户名（不带 @）")
#     if st.button("获取最新 10 条推文"):
#         if username:
#             tweets = get_latest_tweets_via_rss(username)
#             if tweets:
#                 for t in tweets:
#                     content = f"""
#                     🐦 <span style="color:blue;">{username}</span>  
#                     <span style="color:gray;font-size:0.85em;">🕒 {t['published']}</span>  
#                     <p style="margin-top:-6px;">{t['title']}</p>
#                     """
#                     st.markdown(content, unsafe_allow_html=True)
#             else:
#                 st.warning("没有获取到推文")
#         else:
#             st.warning("请输入用户名")

#########################################################################################################################




# 2. 缓存异步数据加载，避免重复请求
# @st.cache_data(show_spinner=False)
def load_wsj_articles(category, i):
    # 模拟异步加载
    return get_wsj_latest_from_html(WSJ[category], i)

# @st.cache_data(show_spinner=False)
def load_bb_articles(category, i):
    if i != 0:
        return get_feed_data(BLOOMBERG[category])
    else:
        return get_bloomberg_latest()

# @st.cache_data(show_spinner=False)
def load_tweets(username):
    return get_latest_tweets_via_rss(username)


# 1. 先初始化 session_state，保存每个模块的tab和数据
if "wsj_active_tab" not in st.session_state:
    st.session_state.wsj_active_tab = list(WSJ.keys())[0]
    
if "wsj_data" not in st.session_state:
    st.session_state.wsj_data = {}

if "bb_active_tab" not in st.session_state:
    st.session_state.bb_active_tab = list(BLOOMBERG.keys())[0]
if "bb_data" not in st.session_state:
    st.session_state.bb_data = {}

if "tweets_data" not in st.session_state:
    st.session_state.tweets_data = []

# 3. 渲染三个模块


    # 切换 tab 时刷新当前模块的 active tab
    # new_tab = st.selectbox("切换 WSJ Tab", list(WSJ.keys()), index=list(WSJ.keys()).index(st.session_state.wsj_active_tab))
    # if new_tab != st.session_state.wsj_active_tab:
    #     st.session_state.wsj_active_tab = new_tab
        # st.experimental  # 只重新运行刷新页面，但 session_state 保存状态，实现“局部刷新”效果


    # new_tab = st.selectbox("切换 Bloomberg Tab", list(BLOOMBERG.keys()), index=list(BLOOMBERG.keys()).index(st.session_state.bb_active_tab))
    # if new_tab != st.session_state.bb_active_tab:
    #     st.session_state.bb_active_tab = new_tab
    #     st.experimental_rerun()

# with col4:
#     st.header("🐦 订阅 X 用户推文（使用 RSS）")
#     username = st.text_input("输入推特用户名（不带 @）", key="username_input")
#     if st.button("获取最新 10 条推文", key="btn_fetch_tweets"):
#         if username:
#             tweets = load_tweets(username)
#             if tweets:
#                 st.session_state.tweets_data = tweets
#             else:
#                 st.warning("没有获取到推文")
#         else:
#             st.warning("请输入用户名")
#         st.experimental_rerun()

#     if st.session_state.tweets_data:
#         for t in st.session_state.tweets_data:
#             content = f"""
#             🐦 <span style="color:blue;">{username}</span>  
#             <span style="color:gray;font-size:0.85em;">🕒 {t['published']}</span>  
#             <p style="margin-top:-6px;">{t['title']}</p>
#             """
#             st.markdown(content, unsafe_allow_html=True)


# with col5:
#     stock_flow()       
# import streamlit as st

# 在使用任何 st.* 之前先设置 page config
# st.set_page_config(page_title="财经新闻聚合", layout="wide")


# def page():
    # 初始化 session_state（避免首次访问时 KeyError）
if "wsj_data" not in st.session_state:
    st.session_state.wsj_data = {}
if "bb_data" not in st.session_state:
    st.session_state.bb_data = {}

st.title("财经新闻聚合")

# 在 page() 内创建列 —— 避免模块导入时就调用 st.columns 导致问题
col1, col2 = st.columns(2)

with col1:
    st.subheader("📈 华尔街见闻 / WSJ")
    tabs = st.tabs(list(WSJ.keys()))
    for i, category in enumerate(WSJ):
        with tabs[i]:
            # 加载并缓存数据
            articles = load_wsj_articles(category, i)
            st.session_state.wsj_data[category] = articles
            for art in articles:
                content = f"""
                <div style="margin-bottom:0.8em;">
                    🔹 <a href="{art['link']}" target="_blank" style="text-decoration:none;font-weight:bold;color:#1a73e8;">{art['title']}</a> </br>  
                    <span style="color:gray;font-size:0.85em;">🕒 {art.get('published', '无时间')}</span>  
                    <span style="color:blue;font-size:0.85em;">{art.get('label', '')}</span><br>
                    <span style="color:gray;font-size:0.75em;line-height:1.2;">{art.get('summary', '')}</span>
                </div>
                """
                st.markdown(content, unsafe_allow_html=True)

with col2:
    st.subheader("💹 Bloomberg")
    tabs = st.tabs(list(BLOOMBERG.keys()))
    for i, category in enumerate(BLOOMBERG):
        with tabs[i]:
            articles = load_bb_articles(category, i)
            st.session_state.bb_data[category] = articles
            for art in articles:
                st.markdown(
                    f"🔹 [{art['title']}]({art['link']})  \n"
                    f"<span style='color:gray;font-size:0.85em;'>🕒 {art.get('published', '无时间')}</span>",
                    unsafe_allow_html=True
                )


# import subprocess
# import sys

# def run_streamlit():
#     # 自动从 Python 启动 Streamlit
#     subprocess.run([sys.executable, "-m", "streamlit", "run", __file__])



