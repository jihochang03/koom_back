from django.db import models


class WishlistItem(models.Model):
    customer_id = models.CharField(max_length=255, db_index=True)
    product_url = models.URLField(max_length=2048)
    site_domain = models.CharField(max_length=255, blank=True, db_index=True)
    title       = models.CharField(max_length=1024, blank=True)
    images      = models.JSONField(default=list)
    price_snapshot = models.FloatField(null=True, blank=True)
    currency    = models.CharField(max_length=10, default='KRW')
    options     = models.JSONField(default=list)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = [('customer_id', 'product_url')]

    def __str__(self):
        return f"{self.customer_id} — {self.title or self.product_url}"
