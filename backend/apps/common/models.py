from django.db import models
from django.core.cache import cache


class SiteConfig(models.Model):
    GROUP_CHOICES = [
        ('pricing', '구매대행 가격 정책'),
        ('shipping', '배송비 상수'),
        ('tariff', '관세 설정'),
        ('exchange', '환율 설정'),
        ('delivery', '배송 소요일'),
    ]

    key = models.CharField(max_length=100, unique=True, db_index=True, verbose_name='키')
    value = models.CharField(max_length=500, verbose_name='값')
    group = models.CharField(max_length=20, choices=GROUP_CHOICES, default='pricing', db_index=True, verbose_name='그룹')
    description = models.TextField(blank=True, default='', verbose_name='설명')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='수정일')

    class Meta:
        ordering = ['group', 'key']
        verbose_name = '설정값'
        verbose_name_plural = '설정값'

    def __str__(self):
        return f'{self.key} = {self.value}'

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        cache.delete(f'siteconfig_{self.key}')
        cache.delete(f'siteconfig_group_{self.group}')
        cache.delete('siteconfig_all')

    @classmethod
    def get(cls, key, default=None):
        cached = cache.get(f'siteconfig_{key}')
        if cached is not None:
            return cached
        try:
            val = cls.objects.get(key=key).value
            cache.set(f'siteconfig_{key}', val, timeout=300)
            return val
        except cls.DoesNotExist:
            return default

    @classmethod
    def get_float(cls, key, default=0.0):
        val = cls.get(key)
        if val is None:
            return default
        try:
            return float(val)
        except (ValueError, TypeError):
            return default

    @classmethod
    def get_int(cls, key, default=0):
        val = cls.get(key)
        if val is None:
            return default
        try:
            return int(float(val))
        except (ValueError, TypeError):
            return default

    @classmethod
    def get_delivery_days(cls) -> dict:
        """배송 단계별 소요일. 없으면 기본값 사용."""
        defaults = {
            'DELIVERY_DAYS_RECEIVE': 3,
            'DELIVERY_DAYS_INSPECT': 1,
            'DELIVERY_DAYS_KR_SHIP': 1,
            'DELIVERY_DAYS_INTL_SHIP': 5,
            'DELIVERY_DAYS_JP_SHIP': 3,
        }
        result = {}
        for key, default in defaults.items():
            result[key] = cls.get_int(key, default)
        return result

    @classmethod
    def get_group(cls, group) -> dict:
        """그룹의 모든 설정을 숫자/문자열로 변환해 dict 반환 (5분 캐시)."""
        cache_key = f'siteconfig_group_{group}'
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        result = {}
        for obj in cls.objects.filter(group=group):
            try:
                result[obj.key] = int(obj.value) if '.' not in obj.value else float(obj.value)
            except (ValueError, TypeError):
                result[obj.key] = obj.value

        cache.set(cache_key, result, timeout=300)
        return result


class PaymentMethod(models.Model):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=50, unique=True)
    icon_url = models.URLField(blank=True, default='')
    is_active = models.BooleanField(default=True, db_index=True)
    display_order = models.IntegerField(default=0)

    class Meta:
        ordering = ['display_order', 'name']

    def __str__(self):
        return self.name


class OrderNotice(models.Model):
    content = models.TextField()
    display_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ['display_order']

    def __str__(self):
        return self.content[:60]
