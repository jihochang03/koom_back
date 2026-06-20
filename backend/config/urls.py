from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/scraping/', include('apps.scraping.urls')),
    path('api/templates/', include('apps.scrape_template.urls')),
    path('api/tariff/', include('apps.tariff.urls')),
    path('api/shipping/', include('apps.shipping.urls')),
    path('api/pricing/', include('apps.pricing.urls')),
    path('api/products/', include('apps.products.urls')),
    path('api/cart/', include('apps.cart.urls')),
    path('api/sites/', include('apps.sites.urls')),
    path('api/orders/', include('apps.orders.urls')),
    path('api/wishlist/', include('apps.wishlist.urls')),
    path('api/cs/', include('apps.cs.urls')),
    path('api/mypage/', include('apps.mypage.urls')),
    path('api/content/', include('apps.content.urls')),
    path('api/logistics/', include('apps.logistics.urls')),
    path('api/operations/', include('apps.operations.urls')),
    path('api/stats/', include('apps.stats.urls')),
    path('api/prohibited/', include('apps.prohibited.urls')),
    path('api/malls/',    include('apps.malls.urls')),
    path('api/payment/',  include('apps.payment.urls')),
    path('api/utils/',    include('apps.utils.urls')),
    path('api/translate/', include('apps.translate.urls')),
    path('api/notify/',   include('apps.notify.urls')),
    path('api/tracking/', include('apps.tracking.urls')),
    path('api/storage/',  include('apps.storage.urls')),
    path('api/auth/',     include('apps.auth_social.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
