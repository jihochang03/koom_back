import re
import requests
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status


class ZipcodeView(APIView):
    """
    GET /api/utils/zipcode/<code>/

    일본 우편번호 7자리 → 도도부현/시구정촌/정명 변환.
    zipcloud.ibsnet.co.jp 무료 API 프록시.

    Response:
      { "zipcode": "1060032", "prefecture": "東京都",
        "city": "港区", "town": "六本木" }
    """

    def get(self, request, code):
        code = re.sub(r'\D', '', code)
        if len(code) != 7:
            return Response(
                {'error': '우편번호는 숫자 7자리여야 합니다.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            resp = requests.get(
                'https://zipcloud.ibsnet.co.jp/api/search',
                params={'zipcode': code},
                timeout=5,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            return Response({'error': f'zipcloud 조회 실패: {e}'}, status=status.HTTP_502_BAD_GATEWAY)

        if data.get('status') != 200 or not data.get('results'):
            return Response({'error': '해당 우편번호를 찾을 수 없습니다.'}, status=status.HTTP_404_NOT_FOUND)

        r = data['results'][0]
        return Response({
            'zipcode':    r.get('zipcode', ''),
            'prefecture': r.get('address1', ''),  # 都道府県
            'city':       r.get('address2', ''),  # 市区町村
            'town':       r.get('address3', ''),  # 町域
            'kana': {
                'prefecture': r.get('kana1', ''),
                'city':       r.get('kana2', ''),
                'town':       r.get('kana3', ''),
            },
        })
