from django.db import migrations

SITES = [
    {
        "name": "쿠팡",
        "domain": "coupang.com",
        "icon_url": "https://www.coupang.com/favicon.ico",
        "sort_order": 1,
        "product_url_patterns": ["/vp/products/"],
        "search_url_patterns": ["/np/search", "/np/supercat"],
    },
    {
        "name": "올리브영",
        "domain": "oliveyoung.co.kr",
        "icon_url": "https://www.oliveyoung.co.kr/favicon.ico",
        "sort_order": 2,
        "product_url_patterns": ["/store/goods/getGoodsDetail"],
        "search_url_patterns": ["/store/search/getSearchMain", "/store/goods/getGoodsList"],
    },
    {
        "name": "무신사",
        "domain": "musinsa.com",
        "icon_url": "https://www.musinsa.com/favicon.ico",
        "sort_order": 3,
        "product_url_patterns": ["/products/", "/app/goods/"],
        "search_url_patterns": ["/search/goods", "/search/"],
    },
    {
        "name": "네이버 스마트스토어",
        "domain": "smartstore.naver.com",
        "icon_url": "https://smartstore.naver.com/favicon.ico",
        "sort_order": 4,
        "product_url_patterns": ["/products/"],
        "search_url_patterns": [],
    },
    {
        "name": "G마켓",
        "domain": "gmarket.co.kr",
        "icon_url": "https://www.gmarket.co.kr/favicon.ico",
        "sort_order": 5,
        "product_url_patterns": ["/Item/", "/item/"],
        "search_url_patterns": ["/Search/", "/search/"],
    },
    {
        "name": "11번가",
        "domain": "11st.co.kr",
        "icon_url": "https://www.11st.co.kr/favicon.ico",
        "sort_order": 6,
        "product_url_patterns": ["/product/"],
        "search_url_patterns": ["/search/"],
    },
    {
        "name": "마켓컬리",
        "domain": "kurly.com",
        "icon_url": "https://www.kurly.com/favicon.ico",
        "sort_order": 7,
        "product_url_patterns": ["/goods/"],
        "search_url_patterns": ["/search"],
    },
    {
        "name": "위메프",
        "domain": "wemakeprice.com",
        "icon_url": "https://www.wemakeprice.com/favicon.ico",
        "sort_order": 8,
        "product_url_patterns": ["/deal/"],
        "search_url_patterns": ["/search/"],
    },
]


def insert_sites(apps, schema_editor):
    SupportedSite = apps.get_model('sites', 'SupportedSite')
    for s in SITES:
        SupportedSite.objects.get_or_create(domain=s['domain'], defaults=s)


def remove_sites(apps, schema_editor):
    SupportedSite = apps.get_model('sites', 'SupportedSite')
    SupportedSite.objects.filter(domain__in=[s['domain'] for s in SITES]).delete()


class Migration(migrations.Migration):
    dependencies = [('sites', '0001_initial')]
    operations = [migrations.RunPython(insert_sites, remove_sites)]
