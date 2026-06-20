from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status

from .services import translate, translate_bulk


class TranslateView(APIView):
    """
    POST /api/translate/

    한국어 → 일본어 번역 (DeepL). DB 캐시 적용.

    Request:
      단건: { "text": "...", "source_lang": "KO", "target_lang": "JA" }
      다건: { "texts": ["...", "..."] }

    Response:
      단건: { "translated": "..." }
      다건: { "translated": ["...", "..."] }
    """

    def post(self, request):
        data = request.data
        source_lang = data.get('source_lang', 'KO').upper()
        target_lang = data.get('target_lang', 'JA').upper()

        if 'texts' in data:
            texts = data['texts']
            if not isinstance(texts, list):
                return Response({'error': 'texts must be a list'}, status=status.HTTP_400_BAD_REQUEST)
            result = translate_bulk(texts, source_lang=source_lang, target_lang=target_lang)
            return Response({'translated': result})

        text = data.get('text', '')
        if not text:
            return Response({'error': 'text or texts required'}, status=status.HTTP_400_BAD_REQUEST)

        return Response({'translated': translate(text, source_lang=source_lang, target_lang=target_lang)})
