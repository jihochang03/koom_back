from django.db import models


class ProductDetailStatus(models.TextChoices):
    PENDING = 'pending', '대기'
    PREFETCHING = 'prefetching', '수집중'
    READY = 'ready', '완료'
    FAILED = 'failed', '실패'


class ArrivalStatus(models.TextChoices):
    ORDERED    = 'ordered',    '주문완료'
    IN_TRANSIT = 'in_transit', '배송중'
    ARRIVED    = 'arrived',    '도착'
    INSPECTED  = 'inspected',  '검수완료'


class Product(models.Model):
    source_url = models.URLField(max_length=2048, blank=True, default='')
    url = models.URLField(max_length=2048, db_index=True)
    product_id = models.CharField(max_length=255, blank=True, default='')

    title = models.CharField(max_length=1024, blank=True, default='')
    price_original = models.FloatField(null=True, blank=True)
    price_discounted = models.FloatField(null=True, blank=True)
    currency = models.CharField(max_length=10, default='KRW')
    images = models.JSONField(default=list)
    brand = models.CharField(max_length=255, blank=True, default='')
    rating = models.FloatField(null=True, blank=True)
    review_count = models.IntegerField(null=True, blank=True)
    availability = models.CharField(max_length=50, blank=True, default='')

    category = models.CharField(max_length=100, blank=True, default='', db_index=True)

    mall = models.ForeignKey(
        'malls.KoreanMall',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='products',
        db_index=True,
    )

    # 뱃지
    is_prima = models.BooleanField(default=False, db_index=True)    # 현지 판매자 확인 필요
    is_limited = models.BooleanField(default=False, db_index=True)  # 한정판
    is_recommended = models.BooleanField(default=False, db_index=True)

    detail_data = models.JSONField(default=dict)
    detail_status = models.CharField(
        max_length=20,
        choices=ProductDetailStatus.choices,
        default=ProductDetailStatus.PENDING,
        db_index=True,
    )
    detail_crawled_at = models.DateTimeField(null=True, blank=True)

    # ── 입고 / 도착 상태 ─────────────────────────────────────────────────────
    inbound_order_number    = models.CharField(
        max_length=100, blank=True, default='', db_index=True,
        verbose_name='구매 오더번호', help_text='이메일 수신 후 입력'
    )
    inbound_tracking_number = models.CharField(
        max_length=100, blank=True, default='', db_index=True,
        verbose_name='송장번호'
    )
    inbound_courier         = models.CharField(
        max_length=50, blank=True, default='',
        verbose_name='택배사', help_text='예: CJ대한통운, 우체국, 롯데택배'
    )
    arrival_status          = models.CharField(
        max_length=15,
        choices=ArrivalStatus.choices,
        default=ArrivalStatus.ORDERED,
        db_index=True,
        verbose_name='도착 상태',
    )
    inspection_required     = models.BooleanField(
        default=False, verbose_name='검수 서비스',
        help_text='사진 촬영·검수 서비스 신청 여부'
    )
    arrived_at              = models.DateTimeField(
        null=True, blank=True, verbose_name='도착 확인 시각'
    )
    inspected_at            = models.DateTimeField(
        null=True, blank=True, verbose_name='검수 완료 시각'
    )
    inbound_note            = models.TextField(
        blank=True, default='', verbose_name='입고 메모'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.category or '미분류'}] {self.title[:60]}"


class ProductArrivalPhoto(models.Model):
    """
    상품 도착 시 촬영/첨부한 사진.
    Admin에서 웹캠 촬영 또는 파일 업로드로 저장.
    사진이 등록되면 상품의 arrival_status가 자동으로 'arrived'로 갱신된다.
    """

    product     = models.ForeignKey(
        Product, on_delete=models.CASCADE,
        related_name='arrival_photos', verbose_name='상품'
    )
    photo       = models.FileField(
        upload_to='arrival_photos/%Y/%m/', verbose_name='도착 사진'
    )
    note        = models.CharField(
        max_length=255, blank=True, default='', verbose_name='메모'
    )
    captured_at = models.DateTimeField(auto_now_add=True, verbose_name='촬영/업로드 시각')

    class Meta:
        ordering = ['-captured_at']
        verbose_name = '도착 사진'
        verbose_name_plural = '도착 사진'

    def __str__(self):
        return f'{self.product.title[:30]} — {self.captured_at:%Y-%m-%d %H:%M}'

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        from django.utils import timezone
        product = self.product
        if product.arrival_status not in (ArrivalStatus.ARRIVED, ArrivalStatus.INSPECTED):
            product.arrival_status = ArrivalStatus.ARRIVED
            product.arrived_at = timezone.now()
            product.save(update_fields=['arrival_status', 'arrived_at', 'updated_at'])
