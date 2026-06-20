from django import forms
from django.contrib import admin, messages
from django.shortcuts import redirect, render
from django.urls import path, reverse
from django.utils.html import format_html

from apps.utils import extract_domain
from .models import SiteTemplate, TemplateBuildLog
from .services import build_template, ScraperAgentError, list_templates_by_domain


# ── Build form ────────────────────────────────────────────────────────────────

CATEGORY_CHOICES = [
    ('shopping', '쇼핑'),
    ('news', '뉴스/블로그'),
    ('real_estate', '부동산'),
    ('jobs', '채용/구인'),
    ('general', '일반'),
]

PAGE_TYPE_CHOICES = [
    ('detail', '상세 페이지'),
    ('list', '목록 페이지'),
    ('both', '목록 + 상세'),
]


class TemplateBuildForm(forms.Form):
    url = forms.URLField(
        label='URL',
        widget=forms.URLInput(attrs={'style': 'width:480px'}),
        help_text='템플릿을 생성할 페이지 URL',
    )
    category = forms.ChoiceField(
        label='카테고리',
        choices=CATEGORY_CHOICES,
        initial='shopping',
    )
    page_type = forms.ChoiceField(
        label='페이지 유형',
        choices=PAGE_TYPE_CHOICES,
        initial='detail',
    )
    message = forms.CharField(
        label='추가 지시사항',
        required=False,
        widget=forms.Textarea(attrs={'rows': 3, 'style': 'width:480px'}),
        help_text='(선택) 에이전트에게 전달할 보충 설명',
    )


# ── SiteTemplate admin ────────────────────────────────────────────────────────

@admin.register(SiteTemplate)
class SiteTemplateAdmin(admin.ModelAdmin):
    list_display = ['domain', 'category', 'page_type', 'updated_at', 'build_action']
    list_filter = ['category', 'page_type']
    search_fields = ['domain']
    readonly_fields = ['created_at', 'updated_at']
    fields = ['domain', 'filename', 'category', 'page_type', 'code', 'created_at', 'updated_at']

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path('build/', self.admin_site.admin_view(self.build_view), name='scrape_template_build'),
        ]
        return custom + urls

    def build_action(self, obj):
        url = reverse('admin:scrape_template_build') + f'?domain={obj.domain}&category={obj.category}&page_type={obj.page_type}'
        return format_html('<a href="{}">재빌드</a>', url)
    build_action.short_description = '빌드'

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['build_url'] = reverse('admin:scrape_template_build')
        return super().changelist_view(request, extra_context=extra_context)

    def build_view(self, request):
        if request.method == 'POST':
            form = TemplateBuildForm(request.POST)
            if form.is_valid():
                url = form.cleaned_data['url']
                category = form.cleaned_data['category']
                page_type = form.cleaned_data['page_type']
                message = form.cleaned_data.get('message', '')
                domain = extract_domain(url)

                existing = list_templates_by_domain(domain)
                log = TemplateBuildLog.objects.create(
                    url=url,
                    domain=domain,
                    category=category,
                    merged_from=','.join(t['filename'] for t in existing),
                )

                try:
                    result = build_template(
                        url=url,
                        category=category,
                        page_type=page_type,
                        message=message,
                        existing_templates=existing or None,
                    )
                    log.success = True
                    log.filename = result.get('filename', result.get('template', ''))
                    log.save(update_fields=['success', 'filename'])
                    messages.success(request, f'템플릿 빌드 완료: {domain} ({page_type})')
                except ScraperAgentError as e:
                    log.error_message = str(e)
                    log.save(update_fields=['error_message'])
                    messages.error(request, f'빌드 실패: {e}')

                return redirect(reverse('admin:scrape_template_sitetemplate_changelist'))
        else:
            initial = {
                'category': request.GET.get('category', 'shopping'),
                'page_type': request.GET.get('page_type', 'detail'),
            }
            domain = request.GET.get('domain')
            if domain:
                try:
                    t = SiteTemplate.objects.get(domain=domain)
                    initial['url'] = f'https://{domain}'
                    initial['category'] = t.category
                    initial['page_type'] = t.page_type
                except SiteTemplate.DoesNotExist:
                    pass
            form = TemplateBuildForm(initial=initial)

        context = {
            **self.admin_site.each_context(request),
            'title': '템플릿 빌드',
            'form': form,
            'opts': self.model._meta,
        }
        return render(request, 'admin/scrape_template/build_form.html', context)


# ── TemplateBuildLog admin ────────────────────────────────────────────────────

@admin.register(TemplateBuildLog)
class TemplateBuildLogAdmin(admin.ModelAdmin):
    list_display = ['id', 'domain', 'category', 'filename', 'success', 'created_at']
    list_filter = ['success', 'category']
    search_fields = ['url', 'domain', 'filename']
    readonly_fields = ['created_at']
