from django.utils import timezone

from apps.scraping.services import analyze_url, ScraperAgentError
from apps.products.models import Product, ProductDetailStatus
from .models import MallCrawlJob, MallCrawlJobStatus, KoreanMall


def _extract_items(data) -> list:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ('items', 'products', 'results', 'data'):
            if isinstance(data.get(key), list):
                return data[key]
    return []


def run_crawl_job(job: MallCrawlJob) -> None:
    job.status = MallCrawlJobStatus.PROCESSING
    job.error_message = ''
    job.save(update_fields=['status', 'error_message', 'updated_at'])

    try:
        result = analyze_url(
            url=job.category_url,
            category='shopping',
            page_type='list',
            collect_detail=False,
        )
    except ScraperAgentError as e:
        job.status = MallCrawlJobStatus.FAILED
        job.error_message = str(e)
        job.save(update_fields=['status', 'error_message', 'updated_at'])
        return

    items = _extract_items(result['data'])
    saved = 0
    for item in items:
        url = item.get('url') or item.get('link') or item.get('href')
        if not url:
            continue
        defaults = {
            'product_id': item.get('product_id') or item.get('id', ''),
            'title': item.get('title') or item.get('name', ''),
            'price_original': item.get('price_original') or item.get('price') or item.get('originalPrice'),
            'price_discounted': item.get('price_discounted') or item.get('discountedPrice') or item.get('salePrice'),
            'currency': item.get('currency', 'KRW'),
            'images': item.get('images') or ([item['image']] if item.get('image') else []),
            'brand': item.get('brand', ''),
            'rating': item.get('rating'),
            'review_count': item.get('review_count') or item.get('reviewCount'),
            'availability': item.get('availability', ''),
            'category': job.category_name,
            'source_url': job.category_url,
            'mall': job.mall,
            'detail_status': ProductDetailStatus.PENDING,
        }
        Product.objects.update_or_create(url=url, defaults=defaults)
        saved += 1

    job.status = MallCrawlJobStatus.COMPLETED
    job.products_count = saved
    job.last_crawled_at = timezone.now()
    job.save(update_fields=['status', 'products_count', 'last_crawled_at', 'updated_at'])
