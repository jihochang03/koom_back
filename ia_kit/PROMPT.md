# 복붙용 프롬프트

`ia_kit` 폴더를 대상 프로젝트에 둔 뒤, 그 프로젝트의 Claude에게 아래를 그대로 붙여넣으세요.
(관련 자료 — 요구사항/화면목록/API문서/Figma/프로토타입 등 — 도 함께 첨부/언급)

---

ia_kit/INSTRUCTIONS.md 를 먼저 읽어줘. 그 방식대로 우리 프로젝트의 IA를 만들어줘.

진행:
1. 내가 준 자료(요구사항·화면·API·DB·디자인)를 분석해서 화면/API/데이터모델/액터/규칙/검증/권한/상태/컨텍스트를 뽑아줘.
2. ia_kit/build_ia.py 의 데모 예시를 우리 프로젝트 내용으로 전부 교체해줘.
   - 데이터 모델은 필드마다 타입·필수·예시값·enum(코드→한글 라벨)을 반드시 채울 것.
   - 예시값은 하나의 일관된 시나리오로 채워서 화면마다 자연스럽게 이어지게.
   - 고객용 화면 표면은 device="phone", 운영/어드민은 device="desktop".
   - 권한은 permission 노드로 만들지 말 것. API 호출 권한은 api(actors=[...]),
     화면의 역할별 노출/비활성/마스킹은 screen(access=[R(effect, roles, targets)]) 로.
3. `python ia_kit/build_ia.py` 실행 — 무결성 WARNING이 0이 될 때까지 보완.
4. `python ia_kit/build_docs.py` 실행 — 생성된 *_ia_docs.html 알려줘.
5. ia_engine.py 와 build_docs.py 는 수정하지 말 것(범용 렌더러). IA에 없는 정보가
   화면에 새로 생기지 않도록, 모든 라벨/예시/타입은 build_ia.py(IA)에만 적을 것.

자료가 부족하면 추측하지 말고 어떤 정보가 더 필요한지 먼저 물어봐.

---
