"""Step 3 — Interview. One spec file per automation. Every `TODO(ask)` is a question the agent
must ask the user and replace with the answer. Building starts only when none are left."""
from __future__ import annotations

import json

from . import config as C

TEMPLATE = """# {auto_id} — 자동화 명세 (spec)

관련 작업: {tasks}
주당 소요 (관찰): {weekly}

<!-- 에이전트 규칙: 아래 TODO(ask) 마다 사용자에게 묻고, 답으로 바꾸세요. 추측해서 채우지 마세요.
     답이 모호하면 다시 물으세요. TODO(ask) 가 0개가 될 때까지 빌드하지 않습니다. -->

## 1. 목적 — 이 일을 왜 하나요?
TODO(ask): 이 작업의 결과물은 누가, 어디에 쓰나요?

## 2. 언제 시작하나요? (트리거)
TODO(ask): 정해진 시간 / 메일이 오면 / 파일이 생기면 / 직접 실행 중 무엇인가요?

## 3. 입력 — 무엇을 보고 시작하나요?
TODO(ask): 어떤 파일·메일·화면·시스템에서 데이터를 가져오나요? 위치/형식은?

## 4. 단계 — 지금 손으로 하는 순서
TODO(ask): 관찰된 순서({flow})가 맞나요? 단계마다 무엇을 보고 무엇을 판단하나요?

## 5. 완료 기준 — '끝났다'는 어떻게 아나요?
TODO(ask): 끝났을 때 무엇이 어디에 어떻게 있어야 하나요? (예: 파일이 폴더에, ERP에 상태 '등록완료')

## 6. 예외 상황
TODO(ask): 데이터가 비었을 때 / 형식이 다를 때 / 중복일 때 / 시스템이 느리거나 로그아웃됐을 때 어떻게 하나요?

## 7. 사람 판단이 필요한 지점
TODO(ask): 어느 단계에서 사람이 봐야 하나요? (그 단계만 AI 보조 또는 확인 요청으로 남깁니다)

## 8. 승인이 필요한 동작 (하나씩 명시)
- 메시지/메일 보내기: TODO(ask) 예/아니오 — 누구에게, 무슨 내용?
- 결제·구매: TODO(ask) 예/아니오 (기본: 자동화하지 않음)
- 삭제: TODO(ask) 예/아니오 — 무엇을?
- 외부 시스템에 제출/확정: TODO(ask) 예/아니오
→ '예' 인 동작도 사용자가 `wa approve <id> <동작>` 으로 직접 승인해야 실제로 실행됩니다.

## 9. 로그인·계정
TODO(ask): 어떤 시스템에 로그인돼 있어야 하나요? (비밀번호는 저장/입력하지 않습니다 — 이미 로그인된 브라우저 세션을 씁니다)

## 10. 실패하면
TODO(ask): 실패를 어떻게 알려드릴까요? (기본: 로그 + 대시보드 표시. 메시지 알림은 8번 승인이 필요)

## 11. 도구 선택 (에이전트가 채움)
- 방식: (script / browser-cdp / browser-mcp / app-api / ai-step)
- 이유:
- 예약: (예: 평일 13:30)
- 회당 절약 시간(분):
"""


def create(auto_id: str, task_ids: list[str]) -> int:
    C.SPEC_DIR.mkdir(parents=True, exist_ok=True)
    path = C.SPEC_DIR / f"{auto_id}.md"
    if path.exists():
        print(f"이미 있습니다: {path}")
        return 0
    tasks, weekly, flow = ", ".join(task_ids) or "(직접 입력)", "?", "?"
    a = C.REPORT_DIR / "analysis.json"
    if a.exists():
        r = json.loads(a.read_text(encoding="utf-8"))
        sel = [t for t in r["tasks"] if t["id"] in task_ids]
        if sel:
            tasks = "; ".join(f"{t['id']} {t['name']}" for t in sel)
            weekly = f"{sum(t['minutes_per_week'] for t in sel)/60:.1f}시간"
        for w in r.get("workflows", []):
            if set(task_ids) & set(w["steps"]):
                flow = " → ".join(w["steps"])
                break
    path.write_text(TEMPLATE.format(auto_id=auto_id, tasks=tasks, weekly=weekly, flow=flow), encoding="utf-8")
    print(f"인터뷰 시트 생성: {path}\n에이전트가 TODO(ask) 항목을 하나씩 물어봅니다.")
    return 0


def check(auto_id: str) -> int:
    path = C.SPEC_DIR / f"{auto_id}.md"
    if not path.exists():
        print(f"spec 없음: {path}")
        return 2
    lines = [l.strip() for l in path.read_text(encoding="utf-8").splitlines() if "TODO(ask)" in l]
    if lines:
        print(f"아직 답이 필요한 질문 {len(lines)}개:")
        for l in lines:
            print("  -", l)
        return 1
    print("spec 완료 — 모호한 항목 없음. 빌드해도 됩니다.")
    return 0
